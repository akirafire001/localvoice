"""Stories written by the owner's AI subscriptions through the external generation API."""
from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import ApiUsageLog, AreaCoverage, ExternalGenTask, KnowledgeItem
from localvoice.services import external_gen, geo
from localvoice.services.llm import GENERATE_SYSTEM, LOCAL_RESEARCH_THEMES

from .test_llm_and_generation import SPEECH

H = {"Authorization": "Bearer tok"}
SPOT = ("尻手", 35.527, 139.684)
TOWN = {"kind": "osm", "title": "尻手（神奈川県横浜市鶴見区）", "url": "https://www.openstreetmap.org/node/1",
        "publisher": "OpenStreetMap", "lat": 35.527, "lon": 139.684, "text": "町名: 尻手",
        "town": "尻手", "municipality": "神奈川県横浜市鶴見区", "country_code": "jp", "country": "日本"}
WIKI = {"kind": "wikipedia_ja", "title": "尻手駅", "url": "https://ja.wikipedia.org/wiki/尻手駅", "text": "尻手駅は…"}


def _setup(app, monkeypatch, spots=(SPOT,)):
    app.config["LV"].EXTERNAL_GEN_TOKEN = "tok"
    monkeypatch.setattr(external_gen, "HOTSPOTS", list(spots))
    fetched = []
    monkeypatch.setattr(external_gen, "town_materials", lambda *a, **k: fetched.append("towns") or [dict(TOWN)])
    monkeypatch.setattr(external_gen, "collect_materials", lambda *a, **k: fetched.append("wiki") or [dict(WIKI)])
    return fetched


def _story(material_id, n=1):
    return {
        "title": f"尻手の地名の由来{n}", "title_en": "Shitte", "category": "history",
        "short_ja": "尻手という地名は、川の下流にあたることから付いたという説があります。",
        "body_ja": "尻手という地名は、川の下流（尻）にあたることから付いたという説があります。昔はこのあたりを川が流れていました。",
        "short_en": "The name Shitte.", "body_en": "The name Shitte may come from the lower river.",
        "lat": 35.527, "lon": 139.684, "radius_m": 1000, "fact_type": "likely", "content_kind": "origin",
        "why_here": "この町の名前の話", "interest_hook": "変わった地名", "present_connection": "今も町名に残る",
        "time_sensitive": False,
        "claims": [{"text_ja": "下流に由来する説", "text_en": "lower river", "source_ids": [material_id]}],
        **SPEECH,
    }


def _answer(client, task_id, answers):
    r = client.post(f"/api/v1/external-gen/tasks/{task_id}/answers", json={"answers": answers}, headers=H)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_needs_the_token(app, client):
    assert client.post("/api/v1/external-gen/tasks", json={"agent": "codex"}, headers=H).status_code == 404
    app.config["LV"].EXTERNAL_GEN_TOKEN = "tok"
    assert client.post("/api/v1/external-gen/tasks", json={"agent": "codex"}).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.post("/api/v1/external-gen/tasks", json={"agent": "codex"}, headers=bad).status_code == 401


def test_agent_runs_the_usual_pipeline_step_by_step(app, client, monkeypatch):
    fetched = _setup(app, monkeypatch)
    batch = app.config["LV"].LOCAL_RESEARCH_THEMES_PER_JOB
    cell = geo.geohash_encode(SPOT[1], SPOT[2], app.config["LV"].GEOHASH_PRECISION)

    r = client.post("/api/v1/external-gen/tasks", json={"agent": "codex", "model": "gpt-x"}, headers=H)
    body = r.get_json()
    assert r.status_code == 200 and body["cell"] == cell and body["place"] == "尻手"
    task_id = body["task_id"]
    # the first research themes, all at once, with the server's own prompt
    calls = body["calls"]
    assert [c["kind"] for c in calls] == ["web_research"] * batch
    assert "神奈川県横浜市鶴見区尻手" in calls[0]["prompt"] and "該当なし" in calls[0]["prompt"]
    with session_scope(app) as db:
        assert db.get(AreaCoverage, cell).status == "generating"  # the worker leaves the cell alone

    facts = [{"fact": "尻手は川の下流（尻）にあたることに由来するという説がある。", "url": "https://example.org/shitte",
              "title": "尻手の地名"},
             {"fact": "尻手村は江戸時代に川崎領に属した。", "url": "https://example.org/mura", "title": "尻手村"}]
    body = _answer(client, task_id, [{"index": c["index"], "result": facts if i == 0 else []}
                                     for i, c in enumerate(calls)])
    (gen,) = body["calls"]
    assert gen["kind"] == "json" and gen["system"] == GENERATE_SYSTEM and gen["schema"]["required"] == ["items"]
    mats = gen["input"]["materials"]
    assert [m["kind"] for m in mats] == ["wikipedia_ja", "osm", "web", "web"]
    web_id = mats[2]["id"]

    body = _answer(client, task_id, [{"index": gen["index"], "result": {"items": [_story(web_id)]}}])
    (round2,) = body["calls"]
    assert round2["kind"] == "json" and round2["input"]["already_told"][0]["title"] == "尻手の地名の由来1"
    with session_scope(app) as db:  # nothing is saved until the cell has run through
        assert db.execute(select(KnowledgeItem)).first() is None

    body = _answer(client, task_id, [{"index": round2["index"], "result": {"items": []}}])
    # then the country-wide manners of Japan, as the worker does
    assert [c["kind"] for c in body["calls"]] == ["web_research"] * app.config["LV"].COUNTRY_RESEARCH_THEMES_PER_JOB
    assert "日本について" in body["calls"][0]["prompt"]
    body = _answer(client, task_id, [{"index": c["index"], "result": []} for c in body["calls"]])

    assert body["status"] == "done" and body["created"] == 1
    assert fetched == ["towns", "wiki"]  # sources fetched once, replays use the stored ones
    with session_scope(app) as db:
        (item,) = db.execute(select(KnowledgeItem)).scalars().all()
        assert item.area_cell == cell and item.generated_by["model"] == "codex:gpt-x"
        assert item.metadata_json["speech"]["ja"] == SPEECH["speech_ja"]
        assert [s.url for s in item.sources] == ["https://example.org/shitte"]
        assert db.get(AreaCoverage, cell).status == "partial"  # themes left for later tasks
        logs = db.execute(select(ApiUsageLog).where(ApiUsageLog.operation == "local_history_research")
                          .order_by(ApiUsageLog.id)).scalars().all()
        assert logs[0].provider == "external:codex"
        assert logs[0].details_json["themes"] == [k for k, _ in LOCAL_RESEARCH_THEMES[:batch]]
        assert db.execute(select(ExternalGenTask)).scalar_one().status == "done"

    # the cell is still short of stories: the next task researches the next themes there
    body = client.post("/api/v1/external-gen/tasks", json={"agent": "claude"}, headers=H).get_json()
    assert body["cell"] == cell
    nxt = LOCAL_RESEARCH_THEMES[batch][1].split("、")[0][:6]
    assert nxt in body["calls"][0]["prompt"]


def test_bad_answers_are_refused(app, client, monkeypatch):
    _setup(app, monkeypatch)
    body = client.post("/api/v1/external-gen/tasks", json={"agent": "codex"}, headers=H).get_json()
    i = body["calls"][0]["index"]
    url = f"/api/v1/external-gen/tasks/{body['task_id']}/answers"
    for answers in ([{"index": i, "result": [{"fact": "x", "url": "ftp://x"}]}],
                    [{"index": 999, "result": []}],
                    [{"index": i, "result": "該当なし"}]):
        r = client.post(url, json={"answers": answers}, headers=H)
        assert r.status_code == 400 and r.get_json()["code"] == "invalid_answer"


def test_spots_first_then_the_cells_around_them(app, client, monkeypatch):
    other = ("渋谷", 35.6595, 139.7005)
    _setup(app, monkeypatch, spots=(SPOT, other))
    p = app.config["LV"].GEOHASH_PRECISION
    spot, spot2 = geo.geohash_encode(SPOT[1], SPOT[2], p), geo.geohash_encode(other[1], other[2], p)
    with session_scope(app) as db:  # the first spot's themes are used up
        db.add(AreaCoverage(area_cell=spot, status="done", item_count=3))
    first = client.post("/api/v1/external-gen/tasks", json={"agent": "a"}, headers=H).get_json()
    assert first["cell"] == spot2
    # the second spot is taken by that task: next come the cells around the spots, nearest spot first
    second = client.post("/api/v1/external-gen/tasks", json={"agent": "b"}, headers=H).get_json()
    assert second["cell"] in geo.geohash_neighbors(spot)


def test_abandoned_and_expired_tasks_free_the_cell(app, client, monkeypatch):
    _setup(app, monkeypatch)
    body = client.post("/api/v1/external-gen/tasks", json={"agent": "a"}, headers=H).get_json()
    r = client.post(f"/api/v1/external-gen/tasks/{body['task_id']}/abandon", headers=H)
    assert r.get_json()["status"] == "abandoned"
    with session_scope(app) as db:
        assert db.get(AreaCoverage, body["cell"]).status == "none"
    again = client.post("/api/v1/external-gen/tasks", json={"agent": "a"}, headers=H).get_json()
    assert again["cell"] == body["cell"]
    from datetime import timedelta

    from localvoice.util import now

    with session_scope(app) as db:
        db.get(ExternalGenTask, __import__("uuid").UUID(again["task_id"])).lease_until = now() - timedelta(minutes=1)
    third = client.post("/api/v1/external-gen/tasks", json={"agent": "b"}, headers=H).get_json()
    assert third["cell"] == body["cell"]
    with session_scope(app) as db:
        statuses = sorted(t.status for t in db.execute(select(ExternalGenTask)).scalars())
        assert statuses == ["abandoned", "abandoned", "active"]
