import uuid

from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import (
    AreaCoverage,
    GuideDecision,
    KnowledgeClaim,
    KnowledgeGenerationJob,
    KnowledgeItem,
    NotificationHistory,
)
from localvoice.services.selector import Selection

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx

LAT, LON = MIYAJIMA


class FakeLLM:
    def __init__(self, behaviour="second"):
        self.behaviour = behaviour
        self.calls = []
        self.generated = []

    def select(self, inp):
        self.calls.append(inp)
        if self.behaviour == "silent":
            return Selection(action="stay_silent", reason="nothing good", model="fake", latency_ms=5, cost_usd=0.001)
        if self.behaviour == "error":
            return Selection(action="speak", error="timeout", model="fake", latency_ms=4000, cost_usd=0.0)
        c = inp.candidates[-1] if self.behaviour == "second" else inp.candidates[0]
        claim_ids = [str(cl.id) for cl in c.item.claims]
        if self.behaviour == "bad_claims":
            claim_ids = [str(uuid.uuid4())]
        sel = Selection(
            action="speak", knowledge_id=str(c.item.id), title="LLMタイトル",
            text="すぐそばの話です。" if self.behaviour != "visual" else "目の前に見えます。",
            speech_text="すぐそばの話です。", reason="test", used_claim_ids=claim_ids,
            model="fake-model", prompt_version="select-v1", latency_ms=12, cost_usd=0.002,
        )
        from localvoice.services.llm import validate_selection

        sel.error = validate_selection(sel, inp)
        return sel

    def generate_items(self, cell, center, materials):
        lat, lon = center
        items = [
            {
                "title": "牡蠣筏の話", "title_en": "Oyster rafts", "category": "food",
                "short_ja": "この海では牡蠣筏による養殖が盛んです。", "body_ja": "この海では古くから牡蠣の養殖が行われ、筏に吊るして育てる方法が広まりました。穏やかな内海が養殖に向いています。",
                "short_en": "Oyster rafts.", "body_en": "Oysters are farmed on rafts here.",
                "lat": lat, "lon": lon, "radius_m": 1500, "fact_type": "verified_fact", "content_kind": "regional_background",
                "why_here": "沿岸のため", "interest_hook": "筏で育てる理由", "present_connection": None,
                "claims": [{"text_ja": "牡蠣の養殖が盛ん", "text_en": "oyster farming", "source_ids": ["m1"]},
                           {"text_ja": "出典なし", "text_en": "no source", "source_ids": ["m99"]}],
            },
            {
                "title": "小学校の沿革", "title_en": "School history", "category": "history",
                "short_ja": "この小学校は明治に開校しました。", "body_ja": "この小学校は明治に開校し、その後統合されました。統合後に校名が変わりました。長い歴史があります。",
                "short_en": "School.", "body_en": "School.", "lat": lat, "lon": lon, "radius_m": 200,
                "fact_type": "verified_fact", "content_kind": "institution_history", "why_here": "近い",
                "interest_hook": "古い", "present_connection": None,
                "claims": [{"text_ja": "明治に開校", "text_en": "opened", "source_ids": ["m2"]}],
            },
            {
                "title": "出典のない話", "title_en": "Unsourced", "category": "culture",
                "short_ja": "x" * 20, "body_ja": "x" * 50, "short_en": "x", "body_en": "x", "lat": lat, "lon": lon,
                "radius_m": 200, "fact_type": "legend", "content_kind": "anecdote", "why_here": "a", "interest_hook": "b",
                "present_connection": None, "claims": [{"text_ja": "a", "text_en": "a", "source_ids": []}],
            },
        ]
        self.generated.append(cell)
        return items, {"model": "fake-model", "latency_ms": 100, "cost_usd": 0.05, "prompt_version": "generate-v1"}


def _trip(client, t, **settings):
    return client.post("/api/v1/trips", headers=auth(t), json={"settings": settings}).get_json()["trip_id"]


def _send(client, t, trip, body):
    r = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_llm_selection_logged_with_rule_choice(app, client):
    app.extensions["lv_llm"] = FakeLLM("second")
    t = register(client)
    k_near = add_item(app, "近い", LAT, LON, interestingness=0.9)
    k_far = add_item(app, "遠い", LAT + 0.002, LON, interestingness=0.5, category="food")
    trip = _trip(client, t)
    res = _send(client, t, trip, ctx(LAT, LON))
    g = res["guide"]
    assert g["selection_mode"] == "llm" and g["title"] == "LLMタイトル" and g["knowledge_id"] == k_far
    assert res["decision"]["fallback"] is False
    with session_scope(app) as db:
        d = db.execute(select(GuideDecision)).scalars().one()
        assert str(d.rule_choice_id) == k_near and str(d.llm_choice_id) == k_far
        assert d.llm_model == "fake-model" and d.latency_ms == 12
        h = db.execute(select(NotificationHistory)).scalars().one()
        assert h.speech_snapshot_json["personalized"] is True


def test_llm_silence(app, client):
    app.extensions["lv_llm"] = FakeLLM("silent")
    t = register(client)
    add_item(app, "A", LAT, LON)
    trip = _trip(client, t)
    res = _send(client, t, trip, ctx(LAT, LON))
    assert res["guide"] is None and res["decision"]["reason"] == "llm_silent"


def test_llm_failures_fall_back_to_rule(app, client):
    for behaviour in ("error", "bad_claims", "visual"):
        app.extensions["lv_llm"] = FakeLLM(behaviour)
        t = register(client, f"u{behaviour.replace('_', '')}")
        kid = add_item(app, f"A-{behaviour}", LAT, LON, interestingness=1.0)
        trip = _trip(client, t)
        res = _send(client, t, trip, ctx(LAT, LON))
        assert res["guide"]["selection_mode"] == "rule", behaviour
        assert res["decision"]["fallback"] is True
        assert res["guide"]["text"].endswith("の短い話")


def test_rule_mode_never_calls_llm(app, client):
    fake = FakeLLM("second")
    app.extensions["lv_llm"] = fake
    t = register(client)
    add_item(app, "A", LAT, LON)
    trip = _trip(client, t, selection_mode="rule")
    res = _send(client, t, trip, ctx(LAT, LON))
    assert res["guide"]["selection_mode"] == "rule" and res["decision"]["fallback"] is False
    assert fake.calls == []


def test_context_enqueues_generation_and_worker_stores_attributed_items(app, client, monkeypatch):
    fake = FakeLLM()
    app.extensions["lv_llm"] = fake
    t = register(client)
    trip = _trip(client, t)
    _send(client, t, trip, ctx(LAT, LON, speed=10, course=0, mode="motorized"))
    with session_scope(app) as db:
        jobs = db.execute(select(KnowledgeGenerationJob)).scalars().all()
        assert len(jobs) >= 2  # current cell + look-ahead cells
        assert max(j.priority for j in jobs) == 10
    # second context in the same cell does not enqueue again
    _send(client, t, trip, ctx(LAT, LON, speed=10, course=0, mode="motorized"))
    with session_scope(app) as db:
        assert len(db.execute(select(KnowledgeGenerationJob)).scalars().all()) == len(jobs)

    mats = [
        {"id": "m1", "kind": "wikipedia_ja", "title": "牡蠣", "url": "https://ja.wikipedia.org/wiki/牡蠣", "publisher": "Wikipedia (ja)", "text": "..."},
        {"id": "m2", "kind": "osm", "title": "学校", "url": "https://www.openstreetmap.org/node/1", "publisher": "OpenStreetMap", "text": "..."},
    ]
    monkeypatch.setattr("localvoice.services.knowledge_gen.collect_materials", lambda *a, **k: [dict(m) for m in mats])
    from localvoice.worker import process_generation

    with app.app_context():
        n = process_generation(app, max_jobs=10)
    assert n == len(jobs)
    with session_scope(app) as db:
        items = db.execute(select(KnowledgeItem).where(KnowledgeItem.origin == "generated")).scalars().all()
        titles = {i.title: i for i in items}
        assert "出典のない話" not in titles
        oyster = titles["牡蠣筏の話"]
        assert oyster.auto_eligible() and oyster.review_status == "unreviewed"
        assert oyster.confidence_level == "low"
        claims = db.execute(select(KnowledgeClaim).where(KnowledgeClaim.knowledge_item_id == oyster.id)).scalars().all()
        assert len(claims) == 1  # the unsourced claim was dropped
        assert not titles["小学校の沿革"].auto_eligible()
        assert titles["小学校の沿革"].story_quality()["hold_reason"] == "chronology_only"
        covs = db.execute(select(AreaCoverage)).scalars().all()
        assert all(c.status == "done" for c in covs)
    # generated story is now served, marked as generated
    t2 = register(client, "bob")
    trip2 = _trip(client, t2, selection_mode="rule")
    g = _send(client, t2, trip2, ctx(LAT, LON))["guide"]
    assert g is not None and g["origin"] == "generated"


def test_generation_failure_retries_then_fails(app, client, monkeypatch):
    class Broken(FakeLLM):
        def generate_items(self, *a):
            from localvoice.services.llm import LLMError

            raise LLMError("timeout")

    app.extensions["lv_llm"] = Broken()
    monkeypatch.setattr("localvoice.services.knowledge_gen.collect_materials", lambda *a, **k: [{"id": "m1", "kind": "wikipedia_ja", "title": "x", "url": "u", "text": "t"}])
    t = register(client)
    trip = _trip(client, t)
    _send(client, t, trip, ctx(LAT, LON, speed=0, course=None, mode="stationary"))
    from localvoice.worker import process_generation

    with app.app_context():
        for _ in range(3):
            process_generation(app, max_jobs=5)
    with session_scope(app) as db:
        job = db.execute(select(KnowledgeGenerationJob)).scalars().one()
        assert job.status == "failed" and job.attempts == 3
        assert db.get(AreaCoverage, job.area_cell).status == "failed"


def test_seed_loads_and_serves(app, client):
    from localvoice.seed import curated

    with session_scope(app) as db:
        created, _ = curated.load(db)
    assert created == len(curated.ITEMS)
    t = register(client)
    trip = _trip(client, t, selection_mode="rule")
    g = _send(client, t, trip, ctx(34.2970, 132.3187))["guide"]
    assert g is not None and g["origin"] == "curated" and g["sources"]


def test_validate_selection_rules(app):
    from localvoice.services.llm import validate_selection
    from localvoice.services.ranking import Candidate
    from localvoice.services.selector import SelectionInput

    kid = add_item(app, "検証", LAT, LON)
    with session_scope(app) as db:
        item = db.get(KnowledgeItem, uuid.UUID(kid))
        claim = str(item.claims[0].id)
        cand = Candidate(item=item, distance_m=300, lat=LAT, lon=LON, in_area=False)
        inp = SelectionInput(candidates=[cand], language="ja", detail_mode="auto", transport_class="walking",
                             course_confident=False, recent_titles=[], memory_summary=None, interests={}, boosts={},
                             local_time="")

        def check(text, ids=None):
            return validate_selection(Selection(action="speak", knowledge_id=kid, text=text, speech_text=text,
                                                used_claim_ids=ids or [claim]), inp)

        assert check("約300mの位置にある話です。") is None
        assert check("右手側にあります。") == "direction_without_confidence"
        assert check("1234年に建てられました。") == "unsupported_number"
        assert check("ここから見える景色") == "visual_expression"
        assert check("ok", ids=[str(uuid.uuid4())]) == "invalid_claims"
        inp.course_confident = True
        assert check("進行方向右手側にあります。") is None


def test_claude_adapter_request_shape_and_cost(app):
    from types import SimpleNamespace

    from localvoice.services.llm import SELECT_SCHEMA, ClaudeLLM

    captured = {}

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(
                stop_reason="end_turn", model="claude-opus-5-5",
                usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0),
                content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text='{"action": "stay_silent"}')],
            )

    llm = ClaudeLLM.__new__(ClaudeLLM)
    llm.cfg = app.config["LV"]
    llm.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    data, meta = llm._json_call("sys", "user", SELECT_SCHEMA, "low", 4.0, model="claude-opus-5-5")
    assert data == {"action": "stay_silent"}
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["effort"] == "low"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["fallbacks"] == "default" and captured["timeout"] == 4.0
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert abs(meta["cost_usd"] - (1000 * 4 + 200 * 20) / 1_000_000) < 1e-9


def _openai_llm(app, responses):
    from types import SimpleNamespace

    from localvoice.services.llm import OpenAILLM

    llm = OpenAILLM.__new__(OpenAILLM)
    llm.cfg = app.config["LV"]
    llm.client = SimpleNamespace(responses=responses)
    return llm


def test_openai_adapter_request_shape_and_cost(app):
    from types import SimpleNamespace

    from localvoice.services.llm import SELECT_SCHEMA

    captured = {}

    class FakeResponses:
        def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(
                status="completed", incomplete_details=None, model="gpt-6.1-sol",
                usage=SimpleNamespace(input_tokens=1000, output_tokens=200,
                                      input_tokens_details=SimpleNamespace(cached_tokens=0)),
                output=[SimpleNamespace(type="reasoning"), SimpleNamespace(type="message", content=[
                    SimpleNamespace(type="output_text", text='{"action": "stay_silent"}', annotations=[])])],
            )

    llm = _openai_llm(app, FakeResponses())
    assert llm.provider == "openai"
    data, meta = llm._json_call("sys", "user", SELECT_SCHEMA, "low", 4.0, model="gpt-6.1-sol")
    assert data == {"action": "stay_silent"}
    assert captured["model"] == "gpt-6.1-sol"
    assert captured["instructions"] == "sys" and captured["input"] == "user"
    assert captured["reasoning"] == {"effort": "low"} and captured["timeout"] == 4.0
    fmt = captured["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["schema"] is SELECT_SCHEMA
    expected = (1000 * 2 + 200 * 10) / 1_000_000  # gpt-6.1-sol list price
    assert abs(meta["cost_usd"] - expected) < 1e-9


def test_openai_adapter_truncated_output_and_web_citations(app):
    from types import SimpleNamespace

    import pytest

    from localvoice.services.llm import SELECT_SCHEMA, _MetaError

    usage = SimpleNamespace(input_tokens=10, output_tokens=10, input_tokens_details=None)
    cite1 = " ([example.org](https://example.org/oysters?utm_source=openai))"
    cite2 = " ([example.org](https://example.org/name))"
    text = ("1. **Oysters:** Oysters are farmed here. A festival is held in February." + cite1
            + "\n\n2. **Name:** The name means shrine island." + cite2)
    i1, i2 = text.index(cite1), text.index(cite2)
    responses = [
        SimpleNamespace(status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                        model="gpt-6.1-sol", usage=usage,
                        output=[SimpleNamespace(type="message", content=[
                            SimpleNamespace(type="output_text", text='{"act', annotations=[])])]),
        SimpleNamespace(status="completed", model="gpt-6.1-sol", usage=usage, output=[
            SimpleNamespace(type="web_search_call"),
            SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text, annotations=[
                SimpleNamespace(type="url_citation", url="https://example.org/oysters?utm_source=openai",
                                title="Oysters", start_index=i1, end_index=i1 + len(cite1)),
                SimpleNamespace(type="url_citation", url="https://example.org/name", title=None,
                                start_index=i2, end_index=i2 + len(cite2)),
            ])]),
        ]),
    ]

    class FakeResponses:
        def create(self, **kw):
            return responses.pop(0)

    llm = _openai_llm(app, FakeResponses())
    with pytest.raises(_MetaError) as e:
        llm._json_call("sys", "user", SELECT_SCHEMA, "low", 4.0, model="gpt-6-luna")
    assert e.value.code == "max_tokens"
    materials, _meta = llm.research_with_web_search("xn76", (34.3, 132.3), ["宮島"])
    assert materials == [
        {"kind": "web", "title": "Oysters", "url": "https://example.org/oysters",
         "text": "Oysters: Oysters are farmed here. A festival is held in February."},
        {"kind": "web", "title": "https://example.org/name", "url": "https://example.org/name",
         "text": "Name: The name means shrine island."},
    ]


def test_models_per_task(app, monkeypatch):
    from types import SimpleNamespace

    from localvoice.config import Config
    from localvoice.services.llm import OpenAILLM

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    cfg = Config()
    assert (cfg.LLM_PROVIDER, cfg.LLM_REALTIME_MODEL, cfg.LLM_BACKGROUND_MODEL) == ("openai", "gpt-6-luna", "gpt-6.1-sol")
    monkeypatch.setenv("LLM_MODEL", "gpt-6-astra")
    monkeypatch.setenv("LLM_REALTIME_MODEL", "gpt-6-luna")
    monkeypatch.setenv("LLM_PRICES", "gpt-6-astra=8/40")
    cfg = Config()
    assert (cfg.LLM_REALTIME_MODEL, cfg.LLM_BACKGROUND_MODEL) == ("gpt-6-luna", "gpt-6-astra")
    assert cfg.llm_price("gpt-6-astra") == (8.0, 40.0) and cfg.llm_price("unknown") == (4.0, 20.0)

    calls = []

    class FakeResponses:
        def create(self, **kw):
            calls.append(kw["model"])
            return SimpleNamespace(
                status="completed", model=kw["model"], usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                output=[SimpleNamespace(type="message", content=[SimpleNamespace(
                    type="output_text", annotations=[],
                    text='{"intents": [], "states": [], "resume": false, "end_condition": null, '
                         '"confidence": 0, "summary": "s", "items": []}')])],
            )

    llm = OpenAILLM.__new__(OpenAILLM)
    llm.cfg = cfg
    llm.client = SimpleNamespace(responses=FakeResponses())
    llm.parse_command("静かにして", "ja")
    llm.generate_items("xn76", (34.3, 132.3), [])
    llm.summarize(SimpleNamespace(language="ja", memory_summary=None), [])
    llm.research_with_web_search("xn76", (34.3, 132.3), [])
    assert calls == ["gpt-6-luna", "gpt-6-astra", "gpt-6-astra", "gpt-6-astra"]
