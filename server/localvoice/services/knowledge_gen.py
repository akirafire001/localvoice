"""A. Runtime knowledge generation per geohash cell (realtime-llm-design §3).

/context only enqueues jobs; the worker (`flask --app localvoice worker`) runs them.
"""
import hashlib
import logging
import re
from datetime import timedelta
from difflib import SequenceMatcher

from flask import current_app
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from ..models import (
    ApiUsageLog,
    AreaCoverage,
    KnowledgeClaim,
    KnowledgeGenerationJob,
    KnowledgeItem,
    KnowledgeSource,
)
from ..util import now
from . import geo
from .llm import LOCAL_HISTORY_PROMPT_VERSION, LOCAL_RESEARCH_THEMES, VISUAL_PATTERNS, LLMError, get_llm, llm_provider
from .sources import collect_materials, town_materials

log = logging.getLogger(__name__)

CURATED_ENOUGH = 5           # cells already covered by this many curated stories nearby are skipped
MAX_ATTEMPTS = 3
EXCLUDED_KINDS = {"institution_history", "practical"}
SOURCE_RELIABILITY = {"wikipedia_ja": 0.6, "wikipedia_en": 0.6, "wikidata": 0.6, "osm": 0.5, "web": 0.4}


def _cfg():
    return current_app.config["LV"]


def cells_for(lat, lon, course, tclass, nearby=False):
    """Cells to generate: the current one, the look-ahead ones and, with `nearby`, the 8 around it."""
    p = _cfg().GEOHASH_PRECISION
    here = geo.geohash_encode(lat, lon, p)
    cells = [(here, 10)]
    look = geo.LOOKAHEAD_M.get(tclass, 0)
    if course is not None and look:
        for frac, prio in ((0.5, 6), (1.0, 5)):
            alat, alon = geo.destination(lat, lon, course, look * frac)
            cells.append((geo.geohash_encode(alat, alon, p), prio))
    if nearby:
        cells += [(c, 3) for c in geo.geohash_neighbors(here)]
    seen, out = set(), []
    for c, prio in cells:
        if c not in seen:
            seen.add(c)
            out.append((c, prio))
    return out


def enqueue_for_position(db, lat, lon, course, tclass, nearby=False):
    t = now()
    for cell, prio in cells_for(lat, lon, course, tclass, nearby):
        db.execute(insert(AreaCoverage).values(area_cell=cell, status="none", item_count=0).on_conflict_do_nothing())
        cov = db.execute(select(AreaCoverage).where(AreaCoverage.area_cell == cell).with_for_update(skip_locked=True)).scalar_one_or_none()
        if cov is None:
            continue  # another request is handling it
        expired = cov.status in ("done", "partial") and cov.expires_at is not None and cov.expires_at <= t
        if cov.status in ("queued", "generating") or (cov.status == "done" and not expired):
            continue
        # "partial": its towns still have research themes left; dig deeper once the traveller here runs low
        if cov.status == "partial" and not expired and not (nearby and prio == 10):
            continue
        if cov.status == "failed" and cov.generated_at and t - cov.generated_at < timedelta(hours=6):
            continue
        clat, clon = geo.geohash_center(cell)
        curated = db.execute(
            text(
                """SELECT count(*) FROM knowledge_items
                   WHERE origin = 'curated' AND review_status <> 'suspended'
                     AND ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 1000)"""
            ),
            {"lat": clat, "lon": clon},
        ).scalar_one()
        if curated >= CURATED_ENOUGH:
            cov.status, cov.item_count, cov.generated_at = "done", curated, t
            cov.expires_at = t + timedelta(days=_cfg().COVERAGE_TTL_DAYS)
            continue
        cov.status = "queued"
        db.add(KnowledgeGenerationJob(area_cell=cell, priority=prio))


def claim_job(db):
    job = db.execute(
        select(KnowledgeGenerationJob)
        .where(KnowledgeGenerationJob.status == "queued")
        .order_by(KnowledgeGenerationJob.priority.desc(), KnowledgeGenerationJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "generating"
    job.started_at = now()
    job.attempts += 1
    cov = db.get(AreaCoverage, job.area_cell)
    if cov:
        cov.status = "generating"
    db.commit()
    return job


def run_job(db, job):
    """Generate items for one cell. Commits its own result."""
    cell = job.area_cell
    cov = db.get(AreaCoverage, cell)
    t = now()
    try:
        created, more = _generate(db, cell)
        job.status, job.finished_at, job.error = "done", now(), None
        if cov:
            cov.status = "partial" if more else "done"
            cov.item_count, cov.generated_at = (cov.item_count or 0) + created, t
            cov.expires_at = t + timedelta(days=_cfg().COVERAGE_TTL_DAYS)
    except Exception as e:  # noqa: BLE001
        log.exception("generation failed for %s", cell)
        db.rollback()
        job = db.get(KnowledgeGenerationJob, job.id)
        cov = db.get(AreaCoverage, cell)
        job.error = str(e)[:500]
        job.finished_at = now()
        retry = job.attempts < MAX_ATTEMPTS
        job.status = "queued" if retry else "failed"
        if cov:
            cov.status = "queued" if retry else "failed"
            cov.generated_at = now()
    db.commit()


def generate_cell(db, cell):
    return _generate(db, cell)[0]


def _generate(db, cell):
    """Returns (stories created, whether the cell's towns still have research themes left)."""
    llm = get_llm()
    if llm is None or not hasattr(llm, "generate_items"):
        raise LLMError("llm_disabled")
    center = geo.geohash_center(cell)
    s, w, n, e = geo.geohash_bbox(cell)
    materials = collect_materials(center[0], center[1], (s, w, n, e))
    more = False
    if _cfg().LOCAL_HISTORY_RESEARCH_ENABLED:
        towns = town_materials(center[0], center[1], (s, w, n, e))
        materials += towns
        todo = _themes_todo(db, towns)
        batch = todo[: _cfg().LOCAL_RESEARCH_THEMES_PER_JOB]
        more = len(todo) > len(batch)
        if batch and hasattr(llm, "research_local_history"):
            need = [t for t in towns if set(batch) - _researched_themes(db).get(_town_key(t), set())]
            try:
                extra, meta = llm.research_local_history(cell, center, need, batch)
                _usage(db, "local_history_research", {**meta, "towns": [_town_key(t) for t in need]}, llm)
                materials += extra
            except LLMError as err:
                log.warning("local history research failed for %s: %s", cell, err)
    if len([m for m in materials if m["kind"] != "osm"]) < 2 and hasattr(llm, "research_with_web_search"):
        names = [m["title"] for m in materials if m.get("title")]
        try:
            extra, meta = llm.research_with_web_search(cell, center, names)
            _usage(db, "web_research", meta, llm)
            materials += extra
        except LLMError as err:
            log.warning("web research failed for %s: %s", cell, err)
    if not materials:
        return 0, more
    for i, m in enumerate(materials, 1):
        m["id"] = f"m{i}"
    # One call writes a dozen stories at most, so keep asking for stories not told yet until the materials
    # run dry (a round adds nothing) or GENERATION_MAX_ROUNDS is reached.
    created = 0
    for rnd in range(_cfg().GENERATION_MAX_ROUNDS):
        told = _told_near(db, center)
        try:
            items, meta = llm.generate_items(cell, center, materials, **({"already_told": told} if told else {}))
        except LLMError:
            if rnd == 0:
                raise
            log.warning("generation round %d failed for %s; keeping earlier rounds", rnd + 1, cell)
            break
        _usage(db, "generate_knowledge", {**meta, "round": rnd + 1}, llm)
        added = store_generated(db, cell, center, materials, items, meta)
        created += added
        if not added:
            break
    return created, more


# Wikipedia materials are gathered within 3 km, so neighbouring cells share articles (ミューザ川崎 reached both
# 尻手 and 江ケ崎). Look that far for stories already told, so one cell does not retell its neighbour's story.
TOLD_RADIUS_M = 3500


def _told_near(db, center, radius_m=TOLD_RADIUS_M, limit=150):
    """Stories already stored around the cell, nearest first, so a generation round does not retell them."""
    rows = db.execute(
        text(
            """SELECT title, short_ja FROM knowledge_items
               WHERE review_status <> 'suspended'
                 AND ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)
               ORDER BY position <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, created_at, id
               LIMIT :limit"""
        ),
        {"lat": center[0], "lon": center[1], "r": radius_m, "limit": limit},
    ).all()
    return [{"title": t, "summary": s} for t, s in rows]


def _town_key(t):
    return f"{t['municipality']}{t['town']}"


def _researched_themes(db):
    """town key -> theme keys researched within COVERAGE_TTL_DAYS with the current research prompt."""
    since = now() - timedelta(days=_cfg().COVERAGE_TTL_DAYS)
    done = {}
    for (d,) in db.execute(
        select(ApiUsageLog.details_json).where(
            ApiUsageLog.operation == "local_history_research", ApiUsageLog.created_at >= since,
            ApiUsageLog.details_json["prompt_version"].astext == LOCAL_HISTORY_PROMPT_VERSION,
        )
    ):
        for town in (d or {}).get("towns") or []:
            done.setdefault(town, set()).update((d or {}).get("themes") or [])
    return done


def _themes_todo(db, towns):
    """Theme keys, in LOCAL_RESEARCH_THEMES order, that at least one of the towns has not been researched for.
    A town often spans several cells; its stories are area-wide, so each theme is researched once per town."""
    if not towns:
        return []
    done = _researched_themes(db)
    return [k for k, _ in LOCAL_RESEARCH_THEMES if any(k not in done.get(_town_key(t), set()) for t in towns)]


def _usage(db, operation, meta, llm):
    db.add(ApiUsageLog(
        trip_session_id=None, provider=llm_provider(llm), operation=operation, request_units=1,
        estimated_cost=meta.get("cost_usd") or 0, details_json={k: v for k, v in meta.items() if k != "cost_usd"},
    ))


def _quality_check(it):
    """Machine check of the content-quality policy for generated items (realtime-llm-design §3.5)."""
    kind = it.get("content_kind")
    if kind in EXCLUDED_KINDS:
        return False, "chronology_only" if kind == "institution_history" else "practical_only"
    if kind == "past_news" and not (it.get("present_connection") or "").strip():
        return False, "unrelated_old_news"
    if not (it.get("why_here") or "").strip() or not (it.get("interest_hook") or "").strip():
        return False, "generic_description"
    if len(it.get("body_ja") or "") < 40 or len(it.get("short_ja") or "") < 15:
        return False, "generic_description"
    blob = " ".join(str(it.get(k) or "") for k in ("title", "short_ja", "body_ja", "short_en", "body_en"))
    if any(p.lower() in blob.lower() for p in VISUAL_PATTERNS):
        return False, "visual_expression"
    return True, None


def _norm_title(t):
    return re.sub(r"[\s「」『』（）()、。・？！?!:：,.\-]", "", t or "").lower()


def _ratio(a, b):
    a, b = _norm_title(a), _norm_title(b)
    return 1.0 if a == b else (SequenceMatcher(None, a, b).ratio() if a and b else 0.0)


def _same_story(title, short, other_title, other_short):
    """The same story regenerated under a slightly different title (〜の合言葉 / 〜の組み合わせ). Titles alone
    are too short to compare (尻手の地名の由来 / 堤根の地名の由来), so the short texts must match too."""
    if _norm_title(title) == _norm_title(other_title):
        return True
    return _ratio(title, other_title) >= 0.7 and _ratio(short, other_short) >= 0.5


def _confidence(source_kinds, publishers):
    # Never auto-assign "high": that needs public/primary sources reviewed by a person (mvp-technical-design §16).
    return "medium" if len(publishers) >= 2 else "low"


def store_generated(db, cell, center, materials, items, meta):
    by_id = {m["id"]: m for m in materials}
    created = 0
    for it in items:
        claims = []
        for cl in it.get("claims") or []:
            sids = [sid for sid in cl.get("source_ids") or [] if sid in by_id]
            if sids and (cl.get("text_ja") or cl.get("text_en")):
                claims.append((cl, sids))
        if not claims:
            continue  # unattributed items are not stored
        try:
            lat, lon = float(it["lat"]), float(it["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if geo.haversine_m(lat, lon, center[0], center[1]) > 5000:
            lat, lon = center  # keep the story anchored near the cell it was generated for
        title = (it.get("title") or "").strip()[:300]
        if not title:
            continue
        key = f"gen:{cell}:{hashlib.sha256(title.encode()).hexdigest()[:12]}"
        if db.execute(select(KnowledgeItem.id).where(KnowledgeItem.canonical_key == key)).first():
            continue
        nearby = db.execute(
            text(
                """SELECT title, short_ja FROM knowledge_items
                   WHERE ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)"""
            ),
            {"lat": lat, "lon": lon, "r": TOLD_RADIUS_M},
        ).all()
        if any(_same_story(title, it.get("short_ja"), t, s) for t, s in nearby):
            continue
        ok, hold = _quality_check(it)
        used = sorted({sid for _, sids in claims for sid in sids})
        publishers = {by_id[s].get("publisher") or by_id[s]["kind"] for s in used}
        fact_type = it.get("fact_type") if it.get("fact_type") in ("verified_fact", "likely", "tradition", "legend") else "likely"
        item = KnowledgeItem(
            canonical_key=key,
            title=title,
            title_en=(it.get("title_en") or "")[:300] or None,
            category=it.get("category") or "history",
            short_ja=it.get("short_ja"), body_ja=it.get("body_ja"),
            short_en=it.get("short_en"), body_en=it.get("body_en"),
            position=f"SRID=4326;POINT({lon} {lat})",
            radius_m=max(50, min(5000, int(it.get("radius_m") or 200))),
            interestingness=0.6, novelty=0.6,
            confidence_level=_confidence({by_id[s]["kind"] for s in used}, publishers),
            fact_type=fact_type,
            origin="generated", review_status="unreviewed", area_cell=cell,
            generated_by={"model": meta.get("model"), "prompt_version": meta.get("prompt_version"),
                          "generated_at": now().isoformat()},
            metadata_json={
                "scope": "area" if int(it.get("radius_m") or 0) >= 800 else "point",
                "story_quality": {
                    "content_kind": it.get("content_kind"), "why_here": it.get("why_here"),
                    "interest_hook": it.get("interest_hook"), "present_connection": it.get("present_connection"),
                    "auto_eligible": ok, "hold_reason": hold, "reviewer": "auto",
                    "reviewed_at": now().isoformat(), "review_version": "auto-v1",
                },
            },
        )
        db.add(item)
        db.flush()
        src_rows, url_rows = {}, {}
        for sid in used:
            m = by_id[sid]
            if m.get("url") and m["url"] in url_rows:  # several facts from one page → one source row
                src_rows[sid] = url_rows[m["url"]]
                continue
            row = KnowledgeSource(
                knowledge_item_id=item.id, url=m.get("url"), publisher=m.get("publisher"), title=m.get("title"),
                retrieved_at=now(), source_type=m["kind"], reliability_score=SOURCE_RELIABILITY.get(m["kind"], 0.4),
                license_info=m.get("license"),
            )
            db.add(row)
            db.flush()
            src_rows[sid] = row.id
            if m.get("url"):
                url_rows[m["url"]] = row.id
        for cl, sids in claims:
            db.add(KnowledgeClaim(
                knowledge_item_id=item.id, claim_text_ja=cl.get("text_ja"), claim_text_en=cl.get("text_en"),
                source_ids=list(dict.fromkeys(src_rows[s] for s in sids)),
            ))
        created += 1
    return created
