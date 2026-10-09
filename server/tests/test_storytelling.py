import json

from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import ApiUsageLog, KnowledgeItem, NotificationHistory

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx
from .test_llm_and_generation import SPEECH, FakeLLM

LAT, LON = MIYAJIMA


def _trip(client, t, **settings):
    return client.post("/api/v1/trips", headers=auth(t), json={"settings": settings}).get_json()["trip_id"]


def _send(client, t, trip, body):
    r = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _strict_ok(schema, path="$"):
    """OpenAI strict mode: every object lists all its properties as required and forbids extra ones."""
    if schema.get("type") == "object" or "properties" in schema:
        assert set(schema["required"]) == set(schema["properties"]), path
        assert schema["additionalProperties"] is False, path
        for k, v in schema["properties"].items():
            _strict_ok(v, f"{path}.{k}")
    if "items" in schema:
        _strict_ok(schema["items"], f"{path}[]")


def test_schemas_are_strict_and_prompts_carry_the_catalogue():
    from localvoice.services import llm, storytelling

    for schema in (llm.GENERATE_SCHEMA, llm.SELECT_SCHEMA, llm.REWRITE_SCHEMA):
        _strict_ok(schema)
    for prompt in (llm.GENERATE_SYSTEM, llm.SELECT_SYSTEM, llm.REWRITE_SYSTEM):
        assert "A1:" in prompt and "G10:" in prompt and "H6:" in prompt and "J5:" in prompt
        assert "B7:" not in prompt and "D4:" not in prompt  # rejected: they tie one story's timing to the next
    codes = [*storytelling.OPENINGS, *storytelling.STRUCTURES, *storytelling.STYLES, *storytelling.DEVICES]
    assert len(codes) == len(set(codes))
    assert "famous_people" in dict(llm.LOCAL_RESEARCH_THEMES) and "specialty_deepdive" in dict(llm.LOCAL_RESEARCH_THEMES)


def test_speech_check_holds_dull_hedged_or_joking_serious_stories():
    from localvoice.services.knowledge_gen import _quality_check

    base = {"content_kind": "anecdote", "why_here": "a", "interest_hook": "b",
            "short_ja": "x" * 20, "body_ja": "x" * 50, **SPEECH}
    assert _quality_check(base) == (True, None)
    assert _quality_check({**base, "punchline": ""}) == (False, "no_punchline")
    assert _quality_check({**base, "speech_ja": "短い"}) == (False, "no_speech")
    assert _quality_check({**base, "speech_ja": SPEECH["speech_ja"] + "諸説あります。"}) == (False, "hedge_in_speech")
    assert _quality_check({**base, "speech_ja": SPEECH["speech_ja"] + "目の前に見えます。"}) == (False, "visual_expression")
    assert _quality_check({**base, "tone": "serious", "devices": ["F6"]}) == (False, "humour_on_serious")
    assert _quality_check({**base, "tone": "serious"}) == (True, None)


def test_rule_path_speaks_the_spoken_version(app, client):
    add_item(app, "牡蠣の話", LAT, LON, speech={"ja": SPEECH["speech_ja"]},
             storytelling={"story_type": "why_here", "opening": "I2", "structure": "B1", "style": "plain",
                           "devices": ["I6"], "tone": "light"})
    t = register(client)
    trip = _trip(client, t, selection_mode="rule")
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    assert g["text"] == "牡蠣の話の短い話"  # the screen keeps the exact text
    with session_scope(app) as db:
        h = db.execute(select(NotificationHistory)).scalar_one()
        assert h.speech_snapshot_json["text"] == SPEECH["speech_ja"]
        assert h.speech_snapshot_json["techniques"]["opening"] == "I2"
        assert h.score_components["story_type"] == "why_here"


def test_selection_gets_speech_and_recent_techniques_of_the_story_told(app, client):
    fake = FakeLLM(behaviour="first")
    app.extensions["lv_llm"] = fake
    for i, cat in enumerate(("history", "food", "nature")):
        add_item(app, f"話{i}", LAT + i * 0.0003, LON, category=cat, speech={"ja": f"語り{i}"},
                 storytelling={"story_type": "lost_trace", "tone": "light", "opening": "A3"})
    t = register(client)
    trip = _trip(client, t)
    hid = _send(client, t, trip, ctx(LAT, LON))["guide"]["history_id"]
    r = client.post(f"/api/v1/guides/{hid}/feedback", headers=auth(t), json={"action": "skip_story"}).get_json()
    assert r["guide"] is not None
    from localvoice.services.llm import build_select_payload

    first, second = fake.calls
    assert first.recent_stories == []
    assert second.recent_stories[-1]["techniques"] == {"opening": "A3"}  # the shared speech's own techniques
    assert second.recent_stories[-1]["story_type"] == "lost_trace"
    payload = build_select_payload(second)
    assert payload["recent_techniques"] == second.recent_stories
    cand = payload["candidates"][0]
    assert cand["speech"].startswith("語り") and cand["storytelling"]["story_type"] == "lost_trace"
    json.dumps(payload, ensure_ascii=False)  # the payload must stay serialisable


def test_same_story_type_twice_in_a_row_is_penalised():
    from types import SimpleNamespace

    from localvoice.models import KnowledgeItem as KI
    from localvoice.services.ranking import Candidate, score_candidates

    def cand(n, story_type):
        item = KI(id=n, canonical_key=f"k{n}", title=f"t{n}", category=f"c{n}", interestingness=0.5, novelty=0.5,
                  metadata_json={"storytelling": {"story_type": story_type}})
        return Candidate(item=item, distance_m=50, lat=0, lon=0, in_area=False)

    told = SimpleNamespace(knowledge_item_id=99, score_components={"category": "x", "story_type": "place_name"})
    ranked, _ = score_candidates([cand(1, "place_name"), cand(2, "why_here")], search_r=300, interests={},
                                 session_topics=set(), boosts={}, history=[told], serendipity="low", seed=1)
    by = {c.item.id: c for c in ranked}
    assert by[1].penalties == {"same_story_type": 0.05} and by[2].penalties == {}


def test_select_adapter_parses_intro(app):
    from localvoice.services import llm as llm_mod
    from localvoice.services.selector import SelectionInput

    class Stub(llm_mod.ClaudeLLM):
        def __init__(self, cfg):
            self.cfg = cfg

        def _json_call(self, *a, **k):
            return {"action": "stay_silent", "knowledge_id": "", "title": "", "text": "", "intro": " ",
                    "reason": "r", "used_claim_ids": []}, {"model": "m", "latency_ms": 1, "cost_usd": 0.0}

    inp = SelectionInput(candidates=[], language="ja", detail_mode="normal", transport_class="walking",
                         course_confident=False, recent_titles=[], memory_summary=None, interests={}, boosts={},
                         local_time="2026-10-08T12:00:00+09:00")
    sel = Stub(app.config["LV"]).select(inp)
    assert sel.action == "stay_silent" and sel.intro == ""


class Rewriter:
    provider = "anthropic"

    def __init__(self, **override):
        self.calls = []
        self.override = override

    def rewrite_story(self, story, techniques_used_nearby=None):
        self.calls.append((story, techniques_used_nearby))
        return {**SPEECH, "opening": "A4", **self.override}, {"model": "fake", "cost_usd": 0.01, "prompt_version": "rewrite-v1"}


def test_rewrite_stories_adds_speech_and_keeps_facts(app):
    from localvoice.services.rewrite import rewrite_all

    a = add_item(app, "筆子塚の話", LAT, LON, area_cell="wy7v3x")
    add_item(app, "書き直し済み", LAT, LON, storytelling={"opening": "A4", "structure": "B1"})
    with session_scope(app) as db:
        db.get(KnowledgeItem, a).area_cell = "wy7v3x"
    fake = Rewriter()
    with session_scope(app) as db:
        stats = rewrite_all(db, fake, echo=lambda *_: None)
    assert stats["stored"] == 1 and len(fake.calls) == 1  # the already rewritten story is skipped
    story, nearby = fake.calls[0]
    assert story["title"] == "筆子塚の話" and story["claims"] == [{"text_ja": "筆子塚の話の事実", "text_en": None}]
    with session_scope(app) as db:
        item = db.get(KnowledgeItem, a)
        assert item.metadata_json["speech"]["ja"] == SPEECH["speech_ja"]
        assert item.metadata_json["storytelling"]["opening"] == "A4"
        assert item.metadata_json["story_quality"]["auto_eligible"] is True
        assert item.metadata_json["story_quality"]["rewrite_version"] == "rewrite-v1"
        assert item.short_ja == "筆子塚の話の短い話" and len(item.claims) == 1
        assert db.execute(select(ApiUsageLog).where(ApiUsageLog.operation == "rewrite_story")).scalar_one()
    # running again finds nothing to do; --force rewrites everything
    with session_scope(app) as db:
        assert rewrite_all(db, Rewriter(), echo=lambda *_: None)["stored"] == 0
        assert rewrite_all(db, Rewriter(), force=True, echo=lambda *_: None)["stored"] == 2


def test_rewrite_without_punchline_holds_the_story_and_dry_run_saves_nothing(app):
    from localvoice.services.rewrite import rewrite_all

    a = add_item(app, "石碑の話", LAT, LON)
    with session_scope(app) as db:
        rewrite_all(db, Rewriter(), dry_run=True, echo=lambda *_: None)
    with session_scope(app) as db:
        assert "speech" not in db.get(KnowledgeItem, a).metadata_json
    with session_scope(app) as db:
        stats = rewrite_all(db, Rewriter(punchline=""), echo=lambda *_: None)
    assert stats["no_punchline"] == 1
    with session_scope(app) as db:
        q = db.get(KnowledgeItem, a).metadata_json["story_quality"]
        assert q["auto_eligible"] is False and q["hold_reason"] == "no_punchline"
    # a rewrite that says the listener can see something is not stored at all
    b = add_item(app, "見える話", LAT, LON)
    with session_scope(app) as db:
        stats = rewrite_all(db, Rewriter(speech_ja=SPEECH["speech_ja"] + "目の前に見えます。"), echo=lambda *_: None)
    with session_scope(app) as db:
        assert "speech" not in db.get(KnowledgeItem, b).metadata_json
    assert stats["visual_expression"] == 1


def test_reseeding_keeps_rewritten_speech(app):
    from localvoice.seed import curated

    with session_scope(app) as db:
        curated.load(db)
        item = db.execute(select(KnowledgeItem).where(KnowledgeItem.origin == "curated")).scalars().first()
        item.metadata_json = {**item.metadata_json, "speech": {"ja": "語り"}, "storytelling": {"opening": "A1"}}
        key = item.canonical_key
    with session_scope(app) as db:
        curated.load(db)
        item = db.execute(select(KnowledgeItem).where(KnowledgeItem.canonical_key == key)).scalar_one()
        assert item.metadata_json["speech"] == {"ja": "語り"} and item.metadata_json["storytelling"] == {"opening": "A1"}
