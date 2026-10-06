from localvoice.services.commands import rule_parse

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx

LAT, LON = MIYAJIMA


def _trip(client, t):
    r = client.post("/api/v1/trips", headers=auth(t), json={"purpose": "travel"})
    return r.get_json()["trip_id"]


def test_rule_parser():
    p = rule_parse("しばらく建築を多めに")
    assert p.intents == [{"type": "focus_category", "target": "architecture", "ttl_min": 60}] and p.confidence == 1.0
    p = rule_parse("30分静かにして")
    assert p.states == [{"type": "quiet", "ttl_min": 30}] and not p.resume
    p = rule_parse("歴史はもういらない")
    assert p.intents[0]["type"] == "suppress_category" and p.intents[0]["target"] == "history"
    p = rule_parse("お腹が空いた")
    assert [s["type"] for s in p.states] == ["hungry"] and p.intents == []
    p = rule_parse("この電車を降りるまで建築を多めに教えて")
    assert p.end_condition and p.intents[0]["target"] == "architecture"
    assert rule_parse("こんにちは").confidence == 0.0
    assert rule_parse("建築").confidence == 0.5  # bare category → short TTL, confirm


def test_command_focus_changes_choice_and_can_be_removed(app, client):
    t = register(client)
    add_item(app, "古い寺", LAT + 0.001, LON, category="history", interestingness=0.8)
    arch = add_item(app, "近代建築", LAT - 0.001, LON, category="architecture", interestingness=0.7)
    trip = _trip(client, t)
    r = client.post(f"/api/v1/trips/{trip}/commands", headers=auth(t), json={"text": "しばらく建築を多めに"})
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body["parser"] == "rule" and not body["needs_confirmation"]
    assert body["created"][0]["label"] == "建築を多めに"
    res = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()
    assert res["guide"]["knowledge_id"] == arch
    oid = body["created"][0]["id"]
    r = client.delete(f"/api/v1/trips/{trip}/overrides/{oid}", headers=auth(t))
    assert r.status_code == 200 and r.get_json()["active"] == []


def test_quiet_state_and_resume(app, client):
    t = register(client)
    add_item(app, "A", LAT + 0.001, LON)
    trip = _trip(client, t)
    r = client.post(f"/api/v1/trips/{trip}/states", headers=auth(t), json={"type": "quiet", "minutes": 10})
    assert r.status_code == 201
    res = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()
    assert res["guide"] is None and res["decision"]["reason"] == "quiet_mode"
    r = client.post(f"/api/v1/trips/{trip}/commands", headers=auth(t), json={"text": "また話して"})
    assert r.status_code == 201 and r.get_json()["resumed"] is True and r.get_json()["active"] == []
    res = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()
    assert res["guide"] is not None


def test_unclear_command_and_ownership(app, client):
    t = register(client)
    other = register(client, login_id="bob")
    trip = _trip(client, t)
    r = client.post(f"/api/v1/trips/{trip}/commands", headers=auth(t), json={"text": "こんにちは"})
    assert r.status_code == 422 and r.get_json()["code"] == "command_not_understood"
    r = client.post(f"/api/v1/trips/{trip}/commands", headers=auth(t), json={"text": "建築"})
    assert r.status_code == 201 and r.get_json()["needs_confirmation"] is True
    oid = r.get_json()["created"][0]["id"]
    assert client.post(f"/api/v1/trips/{trip}/commands", headers=auth(other), json={"text": "静かに"}).status_code == 404
    assert client.delete(f"/api/v1/trips/{trip}/overrides/{oid}", headers=auth(other)).status_code == 404


class CommandLLM:
    def __init__(self, data):
        self.data = data

    def parse_command(self, text, language):
        return self.data, {"model": "fake", "cost_usd": 0.001, "latency_ms": 10}


def test_llm_command_is_validated(app, client):
    app.extensions["lv_llm"] = CommandLLM({
        "intents": [{"type": "focus_category", "target": "food", "ttl_min": 9999},
                    {"type": "focus_category", "target": "weapons", "ttl_min": 30}],
        "states": [{"type": "dance", "ttl_min": 10}],
        "resume": False, "end_condition": "until the train stops", "confidence": 0.9,
    })
    t = register(client)
    trip = _trip(client, t)
    r = client.post(f"/api/v1/trips/{trip}/commands", headers=auth(t), json={"text": "電車を降りるまで食べ物の話"})
    body = r.get_json()
    assert r.status_code == 201 and body["parser"] == "llm"
    assert [c["target"] for c in body["created"]] == ["food"]
    assert body["created"][0]["end_condition"] == "until the train stops"
    summary = client.get(f"/api/v1/trips/{trip}/summary", headers=auth(t)).get_json()
    assert summary["estimated_cost_usd"]["anthropic"] > 0


def test_participants(app, client):
    t = register(client)
    other = register(client, login_id="bob")
    trip = _trip(client, t)
    r = client.post(f"/api/v1/trips/{trip}/participants", headers=auth(t),
                    json={"display_name": "母", "locale": "ja", "interests": ["food"]})
    assert r.status_code == 201
    pid = r.get_json()["participant_id"]
    assert client.post(f"/api/v1/trips/{trip}/participants", headers=auth(t),
                       json={"display_name": "x", "interests": ["bogus"]}).status_code == 400
    assert client.get(f"/api/v1/trips/{trip}/participants", headers=auth(other)).status_code == 404
    lst = client.get(f"/api/v1/trips/{trip}/participants", headers=auth(t)).get_json()["participants"]
    assert [p["display_name"] for p in lst] == ["母"]
    assert client.delete(f"/api/v1/trips/{trip}/participants/{pid}", headers=auth(other)).status_code == 404
    assert client.delete(f"/api/v1/trips/{trip}/participants/{pid}", headers=auth(t)).status_code == 204
