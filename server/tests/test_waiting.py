"""What is told while the stories of a place are not ready yet, and how a new place gets its first stories fast."""
import uuid

from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.services.llm import LOCAL_HISTORY_PROMPT_VERSION
from localvoice.models import AudioAsset, AreaCoverage, KnowledgeGenerationJob, KnowledgeItem, User

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx
from .test_llm_and_generation import SPEECH, _send, _trip

LAT, LON = MIYAJIMA
PV = LOCAL_HISTORY_PROMPT_VERSION


def _continue(client, t, guide):
    r = client.post(f"/api/v1/guides/{guide['history_id']}/feedback", headers=auth(t), json={"action": "continue"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _searching(monkeypatch, value=True):
    from localvoice.services import engine

    monkeypatch.setattr(engine, "_generation_running", lambda *a: value)


def test_tutorial_fills_the_first_wait_once(app, client):
    t = register(client)
    trip = _trip(client, t, notification_level="continuous")
    first = _send(client, t, trip, ctx(LAT, LON))
    g = first["guide"]
    assert g is not None and g["waiting"] == "tutorial" and g["origin"] == "system"
    assert g["title"] == "LocalVoiceへようこそ" and g["location"] is None
    assert first["decision"]["waiting"] == "tutorial"
    titles = [g["title"]]
    for _ in range(2):
        g = _continue(client, t, g)["guide"]
        assert g["waiting"] == "tutorial"
        titles.append(g["title"])
    assert titles == ["LocalVoiceへようこそ", "はじめての場所では", "ボタンの使い方"]
    # all told: nothing else is ready, so the guide waits
    r = _continue(client, t, g)
    assert r["guide"] is None
    # a later trip never repeats it
    trip2 = _trip(client, t)
    assert _send(client, t, trip2, ctx(LAT, LON))["guide"] is None


def test_tutorial_is_not_for_returning_users(app, client):
    t = register(client)
    add_item(app, "前に聞いた話", LAT, LON)
    trip = _trip(client, t)
    assert _send(client, t, trip, ctx(LAT, LON))["guide"]["waiting"] is None
    client.post(f"/api/v1/trips/{trip}/finish", headers=auth(t))
    trip2 = _trip(client, t)
    assert _send(client, t, trip2, ctx(LAT + 0.2, LON))["guide"] is None  # far from any story; not a first trip


def test_tutorial_wrong_info_does_not_suspend_it(app, client):
    t = register(client)
    trip = _trip(client, t)
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    r = client.post(f"/api/v1/guides/{g['history_id']}/feedback", headers=auth(t), json={"action": "wrong_info"})
    assert r.status_code == 200
    with session_scope(app) as db:
        assert db.get(KnowledgeItem, uuid.UUID(g["knowledge_id"])).review_status == "reviewed"


def test_nearby_story_fills_the_wait_while_searching(app, client, monkeypatch):
    app.config["LV"].TUTORIAL_ENABLED = False
    far = add_item(app, "少し先の話", LAT + 0.018, LON)  # about 2 km north, outside the usual search radius
    add_item(app, "遠すぎる話", LAT + 0.2, LON)
    t = register(client)
    trip = _trip(client, t)
    _searching(monkeypatch, False)
    assert _send(client, t, trip, ctx(LAT, LON))["guide"] is None  # nothing being written here: no filler
    _searching(monkeypatch, True)
    res = _send(client, t, trip, ctx(LAT, LON))
    g = res["guide"]
    assert g["knowledge_id"] == far and g["waiting"] == "nearby"
    assert 1900 < g["location"]["distance_m"] < 2100
    assert g["speech"]["intro"] == "この辺りの話を準備している間に、ここから2キロほど離れた場所の話をひとつ。"
    assert res["decision"]["searching"] is True


def _global_item(app, title):
    with session_scope(app) as db:
        item = KnowledgeItem(
            canonical_key=f"gen:global:{uuid.uuid4().hex[:8]}", title=title, title_en=title, category="nature",
            short_ja=f"{title}の話", body_ja=f"{title}の詳しい話", short_en="s", body_en="b", position=None,
            radius_m=5000, origin="generated", review_status="unreviewed",
            metadata_json={"scope": "global", "story_quality": {"auto_eligible": True}},
        )
        db.add(item)
        db.flush()
        return str(item.id)


def test_global_story_fills_the_wait_when_nothing_is_near(app, client, monkeypatch):
    app.config["LV"].TUTORIAL_ENABLED = False
    gid = _global_item(app, "虹はなぜ丸い")
    t = register(client)
    trip = _trip(client, t)
    _searching(monkeypatch, True)
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    assert g["knowledge_id"] == gid and g["waiting"] == "global" and g["location"] is None
    assert g["speech"]["intro"].startswith("この辺りの話を準備している間に")
    # told once only
    trip2 = _trip(client, t)
    assert _send(client, t, trip2, ctx(LAT, LON))["guide"] is None
    # a global story is never offered by the usual ranking
    app.config["LV"].TUTORIAL_ENABLED = False
    _searching(monkeypatch, False)
    t2 = register(client, "bob")
    trip3 = _trip(client, t2)
    assert _send(client, t2, trip3, ctx(LAT, LON))["guide"] is None


def test_waiting_story_audio_plays(app, client, monkeypatch):
    """The tutorial is voiced like any story (shared body audio)."""
    t = register(client)
    trip = _trip(client, t)
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t),
                    json={"voice_profile_id": "ja-default", "language": "ja"})
    assert r.status_code == 200, r.get_json()


class FastFake:
    """Writes one story per call; records the calls."""

    def __init__(self):
        self.calls = []

    def generate_items(self, cell, center, materials, already_told=None, country=None, scope=None):
        self.calls.append(("generate", scope))
        n = len([c for c in self.calls if c[0] == "generate"])
        lat, lon = center
        return [{
            "title": ["昔の池と魚とり", "坂の名前のわけ", "橋が二つある理由", "寺の鐘の行方"][(n - 1) % 4],
            "title_en": f"Story {n}", "category": "history",
            "short_ja": "この辺りには昔、大きな池があったそうです。", "body_ja": "この辺りには昔、大きな池があり、村の人が魚をとって暮らしていました。いまは埋め立てられて住宅地になっています。",
            "short_en": "s", "body_en": "b",
            "lat": lat, "lon": lon, "radius_m": 300, "fact_type": "verified_fact", "content_kind": "local_trivia",
            "why_here": "ここ", "interest_hook": "意外", "present_connection": None,
            "claims": [{"text_ja": "事実", "text_en": "fact", "source_ids": ["m1"]}],
            **SPEECH, "speech_ja": f"話{n}です。" + SPEECH["speech_ja"],
        }], {"model": "fake", "latency_ms": 1, "cost_usd": 0.0, "prompt_version": "generate-v6"}

    def research_local_history(self, cell, center, towns, themes=None, known=None):
        self.calls.append(("research", tuple(themes or ())))
        return [], {"model": "fake", "themes": list(themes or []), "found": {}, "prompt_version": PV}

    def research_global(self, themes=None, known=None):
        self.calls.append(("research_global", tuple(themes or ())))
        mats = [{"kind": "web", "title": "rainbow", "url": "https://example.org/rainbow", "text": "..."}]
        return mats, {"model": "fake", "themes": list(themes or []), "found": {k: 3 for k in themes or []},
                      "prompt_version": PV}


def test_new_place_gets_a_fast_round_then_deep_research(app, client, monkeypatch):
    app.config["LV"].NEARBY_GENERATION_MIN_STORIES = 0
    app.config["LV"].GENERATION_MAX_ROUNDS = 1
    app.config["LV"].TUTORIAL_ENABLED = False
    fake = FastFake()
    app.extensions["lv_llm"] = fake
    mats = [{"id": "m1", "kind": "wikipedia_ja", "title": "x", "url": "https://ja.wikipedia.org/wiki/x", "text": "t"},
            {"id": "m2", "kind": "wikipedia_ja", "title": "y", "url": "https://ja.wikipedia.org/wiki/y", "text": "t"}]
    monkeypatch.setattr("localvoice.services.knowledge_gen.collect_materials", lambda *a, **k: [dict(m) for m in mats])
    t = register(client)
    trip = _trip(client, t, selection_mode="rule")
    assert _send(client, t, trip, ctx(LAT, LON, speed=0, course=None, mode="stationary"))["guide"] is None
    from localvoice.services import knowledge_gen
    from localvoice.worker import process_generation

    with app.app_context():
        assert process_generation(app, stages=("fast",)) == 1
        assert process_generation(app, stages=("fast",)) == 0  # the deep job is not for a fast-only thread
    with session_scope(app) as db:
        jobs = db.execute(select(KnowledgeGenerationJob).order_by(KnowledgeGenerationJob.created_at)).scalars().all()
        assert [(j.stage, j.status) for j in jobs] == [("fast", "done"), ("full", "queued")]
        assert jobs[1].priority == jobs[0].priority - knowledge_gen.DEEP_PRIORITY_DROP
        cov = db.get(AreaCoverage, jobs[0].area_cell)
        assert cov.status == "queued" and cov.item_count == 1
        # its story is already voiced for the waiting traveller
        item = db.execute(select(KnowledgeItem).where(KnowledgeItem.origin == "generated")).scalars().one()
        asset = db.execute(select(AudioAsset).where(AudioAsset.knowledge_item_id == item.id)).scalars().one()
        assert asset.status == "ready" and asset.scope == "shared" and asset.voice_profile_id == "ja-default"
    # the story is told right away, and its audio is the one voiced ahead
    g = _send(client, t, trip, ctx(LAT, LON, speed=0, course=None, mode="stationary"))["guide"]
    assert g is not None and g["origin"] == "generated"
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t),
                    json={"voice_profile_id": "ja-default", "language": "ja"}).get_json()
    assert r["asset_id"] == str(asset.id)
    with app.app_context():
        assert process_generation(app) == 1
    assert [c[0] for c in fake.calls] == ["generate", "generate"]  # the deep job wrote its own round
    with session_scope(app) as db:
        cov = db.get(AreaCoverage, jobs[0].area_cell)
        assert cov.status in ("partial", "done") and cov.item_count == 2


def test_rounds_are_saved_as_they_are_written(app, monkeypatch):
    """A failure in a later step keeps the stories already written."""
    from localvoice.services import knowledge_gen

    class Flaky(FastFake):
        def generate_items(self, *a, **k):
            if len([c for c in self.calls if c[0] == "generate"]) >= 1:
                raise RuntimeError("boom")
            return super().generate_items(*a, **k)

    app.extensions["lv_llm"] = Flaky()
    app.config["LV"].GENERATION_MAX_ROUNDS = 3
    mats = [{"id": "m1", "kind": "wikipedia_ja", "title": "x", "url": "https://ja.wikipedia.org/wiki/x", "text": "t"}]
    monkeypatch.setattr("localvoice.services.knowledge_gen.collect_materials", lambda *a, **k: [dict(m) for m in mats])
    with app.app_context(), session_scope(app) as db:
        db.add(AreaCoverage(area_cell="wy7b1g", status="queued", item_count=0))
        db.add(KnowledgeGenerationJob(area_cell="wy7b1g", priority=10, stage="full", attempts=2))
    with app.app_context():
        db = app.extensions["lv_sessionmaker"]()
        job = knowledge_gen.claim_job(db)
        knowledge_gen.run_job(db, job)
        db.close()
    with session_scope(app) as db:
        assert len(db.execute(select(KnowledgeItem)).scalars().all()) == 1
        cov = db.get(AreaCoverage, "wy7b1g")
        assert cov.status == "partial" and cov.item_count == 1


def test_generate_global_stories(app):
    from localvoice.services import knowledge_gen

    fake = FastFake()
    with app.app_context(), session_scope(app) as db:
        created, more = knowledge_gen.generate_global(db, themes=2, llm=fake, echo=lambda *_: None)
    assert created == 4 and more is True  # rounds go on until GENERATION_MAX_ROUNDS (4)
    assert fake.calls[0] == ("research_global", ("sky", "maps_time"))
    assert ("generate", "global") in fake.calls
    with session_scope(app) as db:
        item = db.execute(select(KnowledgeItem)).scalars().first()
        assert item.position is None and item.metadata_json["scope"] == "global" and item.area_cell is None
        assert item.canonical_key.startswith("gen:global:")
    # the next run takes the next themes
    with app.app_context(), session_scope(app) as db:
        knowledge_gen.generate_global(db, themes=2, llm=fake, echo=lambda *_: None)
    assert ("research_global", ("place_names", "roads")) in fake.calls


def test_research_themes_run_in_parallel_in_order(app):
    import threading
    import time

    from localvoice.services.llm import ClaudeLLM

    llm = ClaudeLLM.__new__(ClaudeLLM)
    llm.cfg = app.config["LV"]
    active, peak = [0], [0]
    lock = threading.Lock()

    def fake_search(prompt, max_uses):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        key = prompt.split("|")[0]
        return [{"kind": "web", "title": key, "url": f"https://example.org/{key}", "text": key}], {"model": "m"}

    llm._web_research = fake_search
    mats, meta = llm._research_themes([(k, f"{k}|prompt") for k in ("a", "b", "c", "d")])
    assert [m["title"] for m in mats] == ["a", "b", "c", "d"] and meta["themes"] == ["a", "b", "c", "d"]
    assert peak[0] > 1


def test_low_accuracy_asks_again_soon(app, client):
    t = register(client)
    trip = _trip(client, t)
    d = _send(client, t, trip, ctx(LAT, LON, acc=500))["decision"]
    assert d["reason"] == "low_accuracy" and d["next_check_after_sec"] == 5


def test_home_country_from_os_region(app, client):
    register(client, "us_user", device_language="en-US")
    register(client, "tw_user", device_language="zh-Hant-TW")
    register(client, "plain", device_language="ja")
    with session_scope(app) as db:
        users = {u.display_name: u for u in db.execute(select(User)).scalars()}
        assert users["us_user"].home_country == "us" and users["us_user"].locale == "en"
        assert users["tw_user"].home_country == "tw"
        assert users["plain"].home_country == "jp"  # no region: the default stays
