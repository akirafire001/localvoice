"""Trial: research towns with the Gemini API free tier (Grounding with Google Search) and compare it with the
current OpenAI web research, before deciding whether to move part of the research there.

It reuses the production prompt, themes and town lookup (llm.research_local_history, sources.town_materials),
writes nothing to any database and never talks to the production server.

  compare  Research the same cells and themes with both providers, check every source URL, write a report.
  volume   Research with Gemini only until the free tier's daily quota runs out (or --max calls), to see how
           many searches a day the free tier really gives.

Keys come from the environment: LOCALVOICE_GEMINI_API_KEY (or GEMINI_API_KEY) and, for compare,
LOCALVOICE_OPENAI_API_KEY (or OPENAI_API_KEY). Output goes to <repo>/.research_trial/.

Run with the server's virtualenv, e.g. on Windows:
  C:\\work\\git\\localvoice\\server\\.venv\\Scripts\\python C:\\work\\git\\localvoice\\tools\\research_trial\\research_trial.py compare
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from localvoice import create_app  # noqa: E402
from localvoice.config import Config  # noqa: E402
from localvoice.services import geo, llm as llm_mod  # noqa: E402
from localvoice.services.llm import ClaudeLLM, LLMError, OpenAILLM, web_publisher  # noqa: E402

OUT_DIR = ROOT / ".research_trial"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Free tier Grounding with Google Search: gemini-2.5-flash and -flash-lite, 500 grounded requests a day shared
# between them (pricing page, checked 2026-10-10). Gemini 3.x models have no free grounding.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
UA = "LocalVoice-research-trial/0.1 (+https://localvoice.ideaworks.tech)"

# Cells to research: 尻手 and its neighbour 矢向 (towns the PC DB already has stories for), and one town abroad
DEFAULT_PLACES = [
    ("尻手", 35.5208, 139.6830),
    ("矢向", 35.5290, 139.6770),
    ("パリ・マレ地区", 48.8590, 2.3600),
]
# Themes of different kinds: history, land, lore, food, people, insider tips, local manners
DEFAULT_THEMES = ["origin", "water_land", "shrines_lore", "food", "people_historical", "hidden_spots",
                  "locals_view", "local_etiquette"]


class QuotaExceeded(Exception):
    """The free tier's daily quota is used up. Not an LLMError, so research_local_history lets it through."""


class GeminiLLM(ClaudeLLM):
    """Only the web research step, over the Gemini API with Grounding with Google Search."""

    provider = "gemini"

    def __init__(self, cfg, api_key, model):
        self.cfg = cfg
        self.api_key = api_key
        self.model = model
        self.calls = 0
        self.rate_limited = 0
        self.last_error = None

    @property
    def background_model(self):
        return self.model

    def _post(self, prompt):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
        while True:
            self.calls += 1
            r = requests.post(GEMINI_URL.format(model=self.model), json=body,
                              headers={"x-goog-api-key": self.api_key}, timeout=self.cfg.LLM_GENERATE_TIMEOUT_SEC)
            if r.status_code != 429:
                return r
            self.rate_limited += 1
            quota, delay = _quota_info(r)
            self.last_error = {"status": 429, "quota": quota, "retry_after_s": delay}
            if "PerDay" in (quota or "") or delay is None:
                raise QuotaExceeded(f"quota_exceeded:{quota}")
            print(f"  per-minute limit ({quota}); waiting {delay:.0f}s", flush=True)
            time.sleep(delay + 1)

    def _web_research(self, prompt, max_uses):
        t0 = time.monotonic()
        self.last_meta = None
        try:
            r = self._post(prompt)
        except requests.RequestException as e:
            raise LLMError(f"web_search_failed:{type(e).__name__}")
        if r.status_code != 200:
            self.last_error = {"status": r.status_code, "body": r.text[:500]}
            raise LLMError(f"web_search_failed:api_error_{r.status_code}")
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        gm = cand.get("groundingMetadata") or {}
        chunks = gm.get("groundingChunks") or []
        materials = []
        for sup in gm.get("groundingSupports") or []:
            fact = re.sub(r"^\s*(\d+\.|[-*])\s+", "", (sup.get("segment") or {}).get("text") or "")
            fact = fact.replace("**", "").strip()
            if not fact:
                continue
            for i in sup.get("groundingChunkIndices") or []:
                web = (chunks[i] if i < len(chunks) else {}).get("web") or {}
                if not web.get("uri"):
                    continue
                materials.append({
                    "kind": "web",
                    # The uri is a Google redirect that expires; check_sources resolves it to the page
                    "title": web.get("title") or web["uri"],
                    "url": web["uri"],
                    "publisher": web.get("title"),
                    "text": fact[:1500],
                })
        usage = data.get("usageMetadata") or {}
        meta = {"latency_ms": int((time.monotonic() - t0) * 1000), "cost_usd": 0.0, "model": self.model,
                "queries": gm.get("webSearchQueries") or [],
                "answer": "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or []),
                "input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")}
        self.last_meta = meta
        return materials, meta


def _quota_info(r):
    """(quota id, retry delay in seconds) from a 429 response of the Gemini API."""
    try:
        details = r.json().get("error", {}).get("details") or []
    except ValueError:
        return None, None
    quota, delay = None, None
    for d in details:
        t = d.get("@type", "")
        if t.endswith("QuotaFailure"):
            quota = ",".join(v.get("quotaId", "") for v in d.get("violations") or [])
        elif t.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", d.get("retryDelay", ""))
            delay = float(m.group(1)) if m else None
    return quota, delay


# ------------------------------------------------------------ source checks

_page_cache = {}


def fetch_page(url):
    """(final url, http status, page text) after redirects; text is crudely stripped of tags."""
    if url in _page_cache:
        return _page_cache[url]
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
        if r.encoding is None or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        text = r.text if "html" in r.headers.get("content-type", "html") or "text" in r.headers.get("content-type", "") else ""
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", " ", text))
        res = (r.url, r.status_code, re.sub(r"\s+", " ", text))
    except requests.RequestException as e:
        res = (url, None, f"ERROR {type(e).__name__}")
    _page_cache[url] = res
    return res


def _numbers(text):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*\d|\d", unicodedata.normalize("NFKC", text))
            if len(n.replace(",", "")) >= 2}


def check_material(m, towns):
    final_url, status, page = fetch_page(m["url"])
    nums = _numbers(m["text"])
    found_nums = {n for n in nums if n in page.replace(",", "")}
    names = {t["town"] for t in towns} | {t["municipality"].split("、")[0] for t in towns}
    return {
        "final_url": final_url,
        "status": status,
        "alive": bool(status and status < 400),
        "publisher": web_publisher(final_url),
        # Rough checks, a hint for the human review: years and figures of the fact appear on the page; the town
        # (or its municipality) is named on the page. Kanji numerals and PDFs count as misses.
        "numbers": sorted(nums),
        "numbers_on_page": sorted(found_nums),
        "town_on_page": any(n and n in page for n in names),
    }


# ------------------------------------------------------------ runs


def towns_of(app, name, lat, lon):
    from localvoice.services.sources import town_materials

    cell = geo.geohash_encode(lat, lon)
    center = geo.geohash_center(cell)
    with app.app_context():
        towns = town_materials(center[0], center[1], geo.geohash_bbox(cell))
    print(f"{name}: cell {cell}, towns {[t['town'] for t in towns]}", flush=True)
    return cell, center, towns


def research_one(provider, llm, cell, center, towns, theme):
    t0 = time.monotonic()
    try:
        materials, meta = llm.research_local_history(cell, center, towns, themes=[theme])
        err = (meta.get("errors") or [None])[0]
    except LLMError as e:
        materials, meta, err = [], {}, str(e)
    if isinstance(llm, GeminiLLM) and getattr(llm, "last_meta", None):
        meta = {**meta, "queries": llm.last_meta.get("queries"), "answer": llm.last_meta.get("answer")}
    return {"provider": provider, "theme": theme, "materials": materials, "error": err,
            "latency_ms": int((time.monotonic() - t0) * 1000), "cost_usd": meta.get("cost_usd") or 0.0,
            "model": meta.get("model"), "queries": meta.get("queries"), "answer": meta.get("answer")}


def summarize(results):
    out = {}
    for r in results:
        s = out.setdefault(r["provider"], {"calls": 0, "errors": 0, "facts": 0, "sources": 0, "alive": 0,
                                           "with_numbers": 0, "numbers_match": 0, "town_on_page": 0,
                                           "cost_usd": 0.0, "latency_ms": 0, "publishers": set()})
        s["calls"] += 1
        s["errors"] += bool(r["error"])
        s["cost_usd"] += r["cost_usd"]
        s["latency_ms"] += r["latency_ms"]
        s["facts"] += len({m["text"] for m in r["materials"]})
        for m in r["materials"]:
            c = m["check"]
            s["sources"] += 1
            s["alive"] += c["alive"]
            s["town_on_page"] += c["town_on_page"]
            if c["numbers"]:
                s["with_numbers"] += 1
                s["numbers_match"] += set(c["numbers"]) == set(c["numbers_on_page"])
            if c["publisher"]:
                s["publishers"].add(c["publisher"])
    for s in out.values():
        s["publishers"] = len(s["publishers"])
    return out


def pct(a, b):
    return f"{a / b * 100:.0f}%" if b else "-"


def write_report(path, places, results, summary, extra=""):
    lines = [f"# Web調査の比較（{datetime.now().strftime('%Y-%m-%d %H:%M')}）", ""]
    lines += ["| | 調査回数 | 失敗 | 事実の数 | 出典 | 出典が開ける | 町名が載っている | 数字が出典と一致 | 出典サイト数 | 費用 | 平均所要 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p, s in summary.items():
        lines.append(f"| {p} | {s['calls']} | {s['errors']} | {s['facts']} | {s['sources']} | "
                     f"{pct(s['alive'], s['sources'])} | {pct(s['town_on_page'], s['sources'])} | "
                     f"{pct(s['numbers_match'], s['with_numbers'])} | {s['publishers']} | ${s['cost_usd']:.3f} | "
                     f"{s['latency_ms'] / max(s['calls'], 1) / 1000:.0f}s |")
    lines += ["", "「町名が載っている」「数字が出典と一致」は機械的な目安です（漢数字やPDFは不一致に数えます）。"
              "正確さは下の一覧を出典と読み比べて確かめてください。", extra, ""]
    for name, cell, towns in places:
        lines += [f"## {name}（{cell}: {'、'.join(t['town'] for t in towns)}）", ""]
        for r in [r for r in results if r["cell"] == cell]:
            lines += [f"### {r['theme']} / {r['provider']}" + (f"（エラー: {r['error']}）" if r["error"] else ""), ""]
            if r.get("queries"):
                lines.append(f"検索語: {' / '.join(r['queries'])}")
                lines.append("")
            if not r["materials"]:
                lines += ["（事実なし）", ""]
                continue
            for m in r["materials"]:
                c = m["check"]
                flags = ("" if c["alive"] else " ❌開けない") + ("" if c["town_on_page"] else " ⚠町名なし") + (
                    " ⚠数字不一致" if set(c["numbers"]) - set(c["numbers_on_page"]) else "")
                lines.append(f"- {m['text']}  \n  [{c['publisher'] or m['publisher']}]({c['final_url']}){flags}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _setup(args):
    cfg = Config()
    app = create_app(cfg)
    gem_key = os.environ.get("LOCALVOICE_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_key:
        sys.exit("Set LOCALVOICE_GEMINI_API_KEY (or GEMINI_API_KEY) to a key from Google AI Studio first.")
    places = DEFAULT_PLACES if not args.place else [
        (p.split(",")[0], float(p.split(",")[1]), float(p.split(",")[2])) for p in args.place]
    return cfg, app, GeminiLLM(cfg, gem_key, args.gemini_model), places


def cmd_compare(args):
    cfg, app, gemini, places = _setup(args)
    providers = [("gemini", gemini)]
    if not args.gemini_only:
        if not cfg.OPENAI_API_KEY:
            sys.exit("Set LOCALVOICE_OPENAI_API_KEY (or use --gemini-only).")
        providers.insert(0, ("openai", OpenAILLM(cfg)))
    themes = [k for k, _ in llm_mod.LOCAL_RESEARCH_THEMES] if args.themes == "all" else args.themes.split(",")
    results, done_places = [], []
    with app.app_context():
        for name, lat, lon in places:
            cell, center, towns = towns_of(app, name, lat, lon)
            if not towns:
                print(f"  no towns found for {name}; skipped", flush=True)
                continue
            done_places.append((name, cell, towns))
            for theme in themes:
                for pname, llm in providers:
                    print(f"  {theme} / {pname} ...", end=" ", flush=True)
                    try:
                        r = research_one(pname, llm, cell, center, towns, theme)
                    except QuotaExceeded as e:
                        r = {"provider": pname, "theme": theme, "materials": [], "error": str(e), "latency_ms": 0,
                             "cost_usd": 0.0}
                    for m in r["materials"]:
                        m["check"] = check_material(m, towns)
                    r["cell"] = cell
                    results.append(r)
                    print(f"{len(r['materials'])} sources" + (f" ({r['error']})" if r["error"] else ""), flush=True)
    summary = summarize(results)
    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    (OUT_DIR / f"compare-{stamp}.json").write_text(
        json.dumps({"places": done_places, "results": results, "summary": summary}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    report = OUT_DIR / f"compare-{stamp}.md"
    extra = f"Gemini: {gemini.model}、API呼び出し {gemini.calls} 回、うち回数制限 {gemini.rate_limited} 回。"
    write_report(report, done_places, results, summary, extra)
    print(f"\nreport: {report}")


def cmd_volume(args):
    """Search with Gemini, cycling themes over the places, until the daily quota (or --max calls) is reached."""
    cfg, app, gemini, places = _setup(args)
    themes = [k for k, _ in llm_mod.LOCAL_RESEARCH_THEMES]
    log, started = [], datetime.now(timezone.utc)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"volume-{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    with app.app_context():
        cells = [(n, *towns_of(app, n, la, lo)) for n, la, lo in places]
        cells = [c for c in cells if c[3]]
        stop = None
        for i in range(args.max):
            name, cell, center, towns = cells[i % len(cells)]
            theme = themes[(i // len(cells)) % len(themes)]
            try:
                r = research_one("gemini", gemini, cell, center, towns, theme)
            except QuotaExceeded as e:
                stop = str(e)
                break
            n_ok = sum(1 for x in log if not x["error"])
            log.append({"i": i, "at": datetime.now(timezone.utc).isoformat(), "place": name, "theme": theme,
                        "sources": len(r["materials"]), "facts": len({m["text"] for m in r["materials"]}),
                        "error": r["error"], "latency_ms": r["latency_ms"]})
            print(f"{i + 1}: {name} / {theme}: {len(r['materials'])} sources"
                  + (f" ({r['error']})" if r["error"] else "") + f"  [ok so far {n_ok + (not r['error'])}]", flush=True)
            if len(log) >= 5 and all(x["error"] for x in log[-5:]):
                stop = f"5 errors in a row: {gemini.last_error}"
                break
            out.write_text(json.dumps({"started": started.isoformat(), "log": log}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    ok = [x for x in log if not x["error"]]
    result = {"started": started.isoformat(), "ended": datetime.now(timezone.utc).isoformat(), "stopped_by": stop,
              "model": gemini.model, "api_calls": gemini.calls, "rate_limited": gemini.rate_limited,
              "searches_ok": len(ok), "facts": sum(x["facts"] for x in ok),
              "empty_searches": sum(1 for x in ok if not x["sources"]), "last_error": gemini.last_error, "log": log}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    per_job = cfg.LOCAL_RESEARCH_THEMES_PER_JOB
    print(f"\nsearches ok: {len(ok)}, facts: {result['facts']}, stopped by: {stop}")
    print(f"= about {len(ok) // per_job} generation jobs a day ({per_job} themes each); "
          f"a cell needs {len(themes)} searches to cover every theme once")
    print(f"log: {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    ap.add_argument("--place", action="append", help='"name,lat,lon"; repeat for several (default: 尻手, 矢向, Paris)')
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare", help="research the same cells with OpenAI and Gemini and write a report")
    c.add_argument("--themes", default=",".join(DEFAULT_THEMES), help='comma separated theme keys, or "all"')
    c.add_argument("--gemini-only", action="store_true")
    c.set_defaults(func=cmd_compare)
    v = sub.add_parser("volume", help="search with Gemini until the free daily quota runs out")
    v.add_argument("--max", type=int, default=600, help="stop after this many searches")
    v.set_defaults(func=cmd_volume)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
