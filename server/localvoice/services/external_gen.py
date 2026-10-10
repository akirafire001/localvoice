"""Stories written by the owner's AI subscriptions (ChatGPT/Codex, Claude Code, Gemini/Antigravity, Cursor).

The server runs the usual generation pipeline (knowledge_gen._generate: the same towns, research themes, prompts,
rounds, quality checks and dedupe) with an LLM whose web searches and JSON calls are answered by an outside agent.
A task is replayed from the start on every answer: calls already answered are fed their stored answers, and the
first unanswered calls are handed to the agent. Nothing is saved until the whole cell has run through, so a replay
that stops at an unanswered call is rolled back.

The agent side is tools/subgen (docs/external-generation.md).
"""
import copy
import hashlib
import ipaddress
import json
import logging
import socket
from datetime import timedelta
from urllib.parse import urlparse

import requests
from flask import current_app
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from ..models import AreaCoverage, ExternalGenTask
from ..seed.hotspots import HOTSPOTS
from ..util import now
from . import geo, knowledge_gen
from .llm import ClaudeLLM, web_publisher
from .sources import collect_materials, town_materials

log = logging.getLogger(__name__)

MAX_FACTS_PER_SEARCH = 15

WEB_INSTRUCTIONS = (
    "Do this research with your web search tool, following the prompt (written in Japanese) exactly. "
    "Return each fact as {fact, url, title}: fact is 1-2 Japanese sentences as the prompt asks, url is the page "
    "you actually read that states it, title is that page's title. Only facts that page states; never guess or "
    "fill gaps. If the prompt's answer would be 「該当なし」, return an empty list."
)
JSON_INSTRUCTIONS = (
    "Act as the model for this call: `system` is your instructions and `input` is the user message (JSON). "
    "Return one JSON object that matches `schema` exactly (every required key, no extra keys). Use only what "
    "`input` contains; do not search the web for this step."
)


class NeedAnswer(Exception):
    """The replay reached calls the agent has not answered yet (not an LLMError: nothing may swallow it)."""


class ExternalLLM(ClaudeLLM):
    """ClaudeLLM's prompts and parsing, with the two model calls answered from the task's stored answers."""

    parallel_research = False  # the replay matches stored answers to calls in order

    def __init__(self, cfg, task):
        self.cfg = cfg
        self.provider = f"external:{task.agent}"
        self.model_name = f"{task.agent}:{task.model}" if task.model else task.agent
        self.calls = copy.deepcopy(task.calls_json or [])
        self.pos = 0
        self.pending = []

    def _call(self, kind, key, request):
        """The answer stored for the next call, or None after recording it as pending."""
        i = self.pos
        self.pos += 1
        if i < len(self.calls):
            c = self.calls[i]
            if c["kind"] == kind and c["key"] == key:
                if c.get("answer") is not None:
                    return c["answer"]
                c["request"] = request  # same call; its input may have moved on (already_told)
                self.pending.append(i)
                return None
            del self.calls[i:]  # the run took another path: later answers no longer apply
        self.calls.append({"kind": kind, "key": key, "request": request, "answer": None})
        self.pending.append(i)
        return None

    def _meta(self):
        return {"model": self.model_name, "cost_usd": 0, "latency_ms": 0}

    def _web_research(self, prompt, max_uses):
        answer = self._call("web_research", _digest(prompt), {"prompt": prompt})
        if answer is None:
            return [], self._meta()  # collect the batch's other searches before asking
        return [dict(m) for m in answer], self._meta()

    def research_with_web_search(self, cell, center, place_names):
        if self.pending:
            raise NeedAnswer()  # the fallback depends on what the pending searches find
        return super().research_with_web_search(cell, center, place_names)

    def _json_call(self, system, user_content, schema, effort, timeout, max_tokens=4000, tools=None, *, model):
        if self.pending:
            raise NeedAnswer()
        answer = self._call("json", _digest(system), {"system": system, "input": json.loads(user_content),
                                                       "schema": schema})
        if answer is None:
            raise NeedAnswer()
        return copy.deepcopy(answer), {**self._meta(), "input_tokens": 0, "output_tokens": 0}


def _digest(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]


class _CachedSources:
    """The towns and materials fetched when the task started, so every replay sees the same ones."""

    def __init__(self, task):
        self.task = task

    def _get(self, name, fetch):
        cache = self.task.sources_json or {}
        if name not in cache:
            cache = {**cache, name: fetch()}
            self.task.sources_json = cache
        return copy.deepcopy(cache[name])

    def town_materials(self, lat, lon, bbox):
        return self._get("towns", lambda: town_materials(lat, lon, bbox))

    def collect_materials(self, lat, lon, bbox, country_code=None):
        return self._get("materials", lambda: collect_materials(lat, lon, bbox, country_code=country_code))


def _cfg():
    return current_app.config["LV"]


# ------------------------------------------------------------------ which cell next


def _rings(max_ring):
    """Cells by distance from the tourist spots: ring 0 is the spots themselves, in HOTSPOTS order."""
    p = _cfg().GEOHASH_PRECISION
    seen, ring, out = set(), [], []
    for _, lat, lon in HOTSPOTS:
        c = geo.geohash_encode(lat, lon, p)
        if c not in seen:
            seen.add(c)
            ring.append(c)
    out.append(ring)
    for _ in range(max_ring):
        nxt = []
        for c in ring:
            for n in geo.geohash_neighbors(c):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
        out.append(nxt)
        ring = nxt
    return out


def _story_counts(db, cells):
    rows = db.execute(
        text("""SELECT area_cell, count(*) FROM knowledge_items
                WHERE area_cell = ANY(:cells) AND review_status <> 'suspended'
                  AND COALESCE(metadata_json->>'scope', '') <> 'country'
                GROUP BY area_cell"""),
        {"cells": cells},
    ).all()
    return dict(rows)


def _open_cell(db, cells, busy):
    """First cell still short of stories that neither the worker nor another agent is working on and whose
    research themes are not used up."""
    t = now()
    cov = {c.area_cell: c for c in db.execute(select(AreaCoverage).where(AreaCoverage.area_cell.in_(cells))).scalars()}
    counts = _story_counts(db, cells)
    target = _cfg().EXTERNAL_GEN_TARGET_PER_CELL
    for cell in cells:
        if cell in busy or counts.get(cell, 0) >= target:
            continue
        c = cov.get(cell)
        if c is not None:
            live = c.expires_at is None or c.expires_at > t
            if c.status in ("queued", "generating"):
                continue
            if c.status == "done" and live:
                continue  # every theme of its towns is used up
            if c.status == "failed" and c.generated_at and t - c.generated_at < timedelta(hours=6):
                continue
        return cell
    return None


def _release_expired(db):
    t = now()
    for task in db.execute(
        select(ExternalGenTask).where(ExternalGenTask.status == "active", ExternalGenTask.lease_until <= t)
        .with_for_update(skip_locked=True)
    ).scalars():
        task.status, task.updated_at = "abandoned", t
        cov = db.get(AreaCoverage, task.area_cell)
        if cov is not None and cov.status == "generating":
            cov.status = task.prior_coverage or "none"


def claim(db, agent, model=None):
    """Start a task on the next cell. Returns (task, pending requests) or (None, None) when nothing is left."""
    _release_expired(db)
    db.commit()
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('external_gen_claim'))"))
    busy = {c for (c,) in db.execute(select(ExternalGenTask.area_cell).where(ExternalGenTask.status == "active"))}
    cell = None
    for ring in _rings(_cfg().EXTERNAL_GEN_MAX_RING):
        cell = _open_cell(db, ring, busy)
        if cell:
            break
    if cell is None:
        db.commit()
        return None, None
    db.execute(insert(AreaCoverage).values(area_cell=cell, status="none", item_count=0).on_conflict_do_nothing())
    cov = db.get(AreaCoverage, cell)
    t = now()
    task = ExternalGenTask(
        area_cell=cell, agent=agent, model=model, status="active", calls_json=[], sources_json={},
        prior_coverage=cov.status, created_at=t, updated_at=t,
        lease_until=t + timedelta(minutes=_cfg().EXTERNAL_GEN_LEASE_MIN),
    )
    cov.status = "generating"  # keeps the worker off this cell (enqueue_for_position skips it)
    db.add(task)
    db.commit()
    return task, advance(db, task)


# ------------------------------------------------------------------ running and answering


def advance(db, task):
    """Replay the pipeline with the answers so far. Returns the calls waiting for answers, or [] when the cell is
    done (its stories are saved)."""
    task_id = task.id
    sources = _CachedSources(task)
    llm = ExternalLLM(_cfg(), task)
    try:
        created, more = knowledge_gen._generate(db, task.area_cell, llm=llm, sources=sources)
        if llm.pending:
            raise NeedAnswer()
    except NeedAnswer:
        fetched = task.sources_json
        db.rollback()  # stories and logs of this replay are written again once everything is answered
        task = db.get(ExternalGenTask, task_id)
        task.sources_json, task.calls_json = fetched, llm.calls
        task.updated_at = now()
        db.commit()
        return pending_requests(task)
    except Exception as e:  # noqa: BLE001
        log.exception("external generation failed for %s", task.area_cell)
        db.rollback()
        task = db.get(ExternalGenTask, task_id)
        _finish(db, task, "failed", error=str(e)[:500])
        db.commit()
        return []
    task.calls_json = llm.calls
    task.created_count = created
    _finish(db, task, "done", more=more, created=created)
    db.commit()
    return []


def _finish(db, task, status, *, more=False, created=0, error=None):
    t = now()
    task.status, task.error, task.updated_at = status, error, t
    cov = db.get(AreaCoverage, task.area_cell)
    if cov is None:
        return
    if status == "done":
        cov.status = "partial" if more else "done"
        cov.item_count, cov.generated_at = (cov.item_count or 0) + created, t
        cov.expires_at = t + timedelta(days=_cfg().COVERAGE_TTL_DAYS)
    else:
        cov.status = task.prior_coverage or "none"


def pending_requests(task):
    out = []
    for i, c in enumerate(task.calls_json or []):
        if c.get("answer") is None and c.get("request") is not None:
            out.append({"index": i, "kind": c["kind"],
                        "instructions": WEB_INSTRUCTIONS if c["kind"] == "web_research" else JSON_INSTRUCTIONS,
                        **c["request"]})
    return out


class AnswerError(ValueError):
    pass


def answer(db, task, answers):
    """Store the agent's answers ({index, result}) and run on. Returns the next pending calls ([] when done)."""
    calls = copy.deepcopy(task.calls_json or [])
    if not isinstance(answers, list) or not answers:
        raise AnswerError("answers must be a non-empty list of {index, result}")
    for a in answers:
        i = a.get("index") if isinstance(a, dict) else None
        if not isinstance(i, int) or not 0 <= i < len(calls) or calls[i].get("answer") is not None:
            raise AnswerError(f"index {i} is not a pending call")
        result = a.get("result")
        if calls[i]["kind"] == "web_research":
            calls[i]["answer"] = _web_materials(result)
        else:
            if not isinstance(result, dict):
                raise AnswerError(f"call {i}: result must be a JSON object matching the schema")
            calls[i]["answer"] = result
        calls[i].pop("request", None)
    task.calls_json = calls
    task.lease_until = now() + timedelta(minutes=_cfg().EXTERNAL_GEN_LEASE_MIN)
    db.commit()
    return advance(db, task)


def _web_materials(result):
    """The agent's facts as web materials, the shape the API research returns."""
    if not isinstance(result, list):
        raise AnswerError("web_research result must be a list of {fact, url, title} (empty when nothing found)")
    out = []
    for f in result[:MAX_FACTS_PER_SEARCH]:
        if not isinstance(f, dict):
            raise AnswerError("each fact must be an object {fact, url, title}")
        fact, url = (f.get("fact") or "").strip(), (f.get("url") or "").strip()
        if not fact or urlparse(url).scheme not in ("http", "https") or not urlparse(url).hostname:
            raise AnswerError(f"each fact needs text and an http(s) url: {fact[:40]!r} {url!r}")
        if not _page_exists(url):
            log.info("dropped a fact whose page does not exist: %s", url)
            continue
        out.append({"kind": "web", "title": (f.get("title") or "").strip() or url, "url": url,
                    "publisher": web_publisher(url), "text": fact[:1500]})
    return out


def _public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def _page_exists(url):
    """False for pages that are certainly not there (unknown or private host, 404/410). Sites that block robots
    (403, 429) or time out get the benefit of the doubt."""
    if not _cfg().EXTERNAL_GEN_VERIFY_URLS:
        return True
    if not _public_host(urlparse(url).hostname):
        return False
    try:
        r = requests.get(url, timeout=8, stream=True, allow_redirects=True,
                         headers={"User-Agent": _cfg().HTTP_USER_AGENT})
        r.close()
        return r.status_code not in (404, 410)
    except requests.exceptions.ConnectionError:
        return False
    except requests.RequestException:
        return True


def abandon(db, task):
    _finish(db, task, "abandoned")
    db.commit()


def progress(db):
    """Stories per tourist spot cell, for the agent's report."""
    rings = _rings(0)[0]
    counts = _story_counts(db, rings)
    target = _cfg().EXTERNAL_GEN_TARGET_PER_CELL
    full = sum(1 for c in rings if counts.get(c, 0) >= target)
    active = db.execute(select(func.count()).select_from(ExternalGenTask)
                        .where(ExternalGenTask.status == "active")).scalar_one()
    return {"hotspots": len(rings), "hotspots_at_target": full, "target_per_cell": target, "active_tasks": active}


def place_name(cell):
    for name, lat, lon in HOTSPOTS:
        if geo.geohash_encode(lat, lon, _cfg().GEOHASH_PRECISION) == cell:
            return name
    return None

