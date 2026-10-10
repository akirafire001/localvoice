from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import GuideDecision, KnowledgeItem

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx, iso_now

LAT, LON = MIYAJIMA


def _trip(client, t, **settings):
    r = client.post("/api/v1/trips", headers=auth(t), json={"purpose": "travel", "settings": settings})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["trip_id"]


def _send(client, t, trip_id, body):
    r = client.post(f"/api/v1/trips/{trip_id}/context", headers=auth(t), json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_no_candidates_is_silent(client):
    t = register(client)
    trip = _trip(client, t)
    res = _send(client, t, trip, ctx(LAT, LON))
    assert res["guide"] is None and res["decision"]["reason"] == "no_candidates"


def test_guide_selected_with_rule_fallback_and_logged(app, client):
    t = register(client)
    kid = add_item(app, "厳島神社の回廊", LAT + 0.001, LON)
    trip = _trip(client, t)
    res = _send(client, t, trip, ctx(LAT, LON))
    g = res["guide"]
    assert g["knowledge_id"] == kid
    assert g["text"] == "厳島神社の回廊の短い話"
    assert g["sources"][0]["url"] == "https://example.org/src"
    assert g["selection_mode"] == "rule" and res["decision"]["fallback"] is True
    assert g["location"]["relative_direction"] in ("ahead", "left", "right", "behind")
    with session_scope(app) as db:
        d = db.execute(select(GuideDecision)).scalars().one()
        assert d.final_action == "speak" and d.fallback_reason == "llm_disabled"
        assert str(d.rule_choice_id) == kid and d.candidates_json[0]["knowledge_id"] == kid


def test_cooldown_duplicate_and_conflict(app, client):
    t = register(client)
    add_item(app, "A", LAT + 0.001, LON)
    add_item(app, "B", LAT - 0.001, LON)
    trip = _trip(client, t)
    body = ctx(LAT, LON)
    assert _send(client, t, trip, body)["guide"] is not None
    # same event again → no second notification
    dup = _send(client, t, trip, body)
    assert dup["guide"] is None and dup["decision"]["reason"] == "duplicate_event"
    # same id, different content → 409
    bad = dict(body, location={"lat": LAT + 1, "lon": LON, "accuracy_m": 5})
    assert client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=bad).status_code == 409
    res = _send(client, t, trip, ctx(LAT, LON))
    assert res["decision"]["reason"] == "cooldown" and res["decision"]["next_check_after_sec"] > 0


def test_low_accuracy_and_quality_filters(app, client):
    t = register(client)
    add_item(app, "沿革だけ", LAT, LON, auto_eligible=False)
    add_item(app, "停止中", LAT, LON, review_status="suspended")
    trip = _trip(client, t)
    assert _send(client, t, trip, ctx(LAT, LON, acc=500))["decision"]["reason"] == "low_accuracy"
    assert _send(client, t, trip, ctx(LAT, LON))["decision"]["reason"] == "no_candidates"


def test_area_story_covers_far_center(app, client):
    t = register(client)
    # center 3km away but radius 5km covers the user
    kid = add_item(app, "瀬戸内の牡蠣", LAT + 0.027, LON, category="food", radius_m=5000)
    trip = _trip(client, t)
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    assert g["knowledge_id"] == kid and g["location"]["kind"] == "area"


def test_english_trip_uses_english_text(app, client):
    t = register(client)
    add_item(app, "日本語のみ", LAT, LON, en=False)
    kid = add_item(app, "英語あり", LAT + 0.0005, LON)
    r = client.post("/api/v1/trips", headers=auth(t), json={"language": "en"})
    trip = r.get_json()["trip_id"]
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    assert g["knowledge_id"] == kid and g["text"].startswith("Short story") and g["language"] == "en"


def test_stale_event_is_stored_only(app, client):
    t = register(client)
    add_item(app, "A", LAT, LON)
    trip = _trip(client, t)
    res = _send(client, t, trip, ctx(LAT, LON, observed_at=iso_now(-3600)))
    assert res["guide"] is None and res["decision"]["reason"] == "stale_event"
    track = client.get(f"/api/v1/trips/{trip}/track", headers=auth(t)).get_json()
    assert len(track["points"]) == 1


def test_owner_checks(app, client):
    a = register(client, "alice")
    b = register(client, "bob")
    add_item(app, "A", LAT, LON)
    trip = _trip(client, a)
    g = _send(client, a, trip, ctx(LAT, LON))["guide"]
    hb = auth(b)
    assert client.post(f"/api/v1/trips/{trip}/context", headers=hb, json=ctx(LAT, LON)).status_code == 404
    assert client.get(f"/api/v1/trips/{trip}/track", headers=hb).status_code == 404
    assert client.get(f"/api/v1/trips/{trip}/history", headers=hb).status_code == 404
    assert client.patch(f"/api/v1/trips/{trip}", headers=hb, json={}).status_code == 404
    assert client.post(f"/api/v1/trips/{trip}/finish", headers=hb).status_code == 404
    r = client.post(f"/api/v1/guides/{g['history_id']}/feedback", headers=hb, json={"action": "interesting"})
    assert r.status_code == 404


def test_track_pagination_and_range(app, client):
    t = register(client)
    trip = _trip(client, t)
    times = [iso_now(-500 + i * 10) for i in range(7)]
    for ts in times:
        _send(client, t, trip, ctx(LAT, LON, observed_at=ts))
    r = client.get(f"/api/v1/trips/{trip}/track?limit=3", headers=auth(t)).get_json()
    pts = r["points"]
    while r["next_cursor"]:
        r = client.get(f"/api/v1/trips/{trip}/track?limit=3&cursor={r['next_cursor']}", headers=auth(t)).get_json()
        pts += r["points"]
    assert len(pts) == 7
    assert [p["observed_at"] for p in pts] == sorted(p["observed_at"] for p in pts)
    from urllib.parse import quote

    r = client.get(
        f"/api/v1/trips/{trip}/track?from={quote(times[2])}&until={quote(times[5])}", headers=auth(t)
    ).get_json()
    assert len(r["points"]) == 3


def test_feedback_actions(app, client):
    t = register(client)
    k1 = add_item(app, "A", LAT, LON, category="architecture")
    k2 = add_item(app, "B", LAT + 0.0008, LON, category="food")
    trip = _trip(client, t)
    g = _send(client, t, trip, ctx(LAT, LON))["guide"]
    hid = g["history_id"]
    r = client.post(f"/api/v1/guides/{hid}/feedback", headers=auth(t), json={"action": "more_detail"}).get_json()
    assert r["detail_text"].endswith("詳しい話")
    assert client.post(f"/api/v1/guides/{hid}/feedback", headers=auth(t), json={"action": "more_related"}).status_code == 200
    r = client.post(f"/api/v1/guides/{hid}/feedback", headers=auth(t), json={"action": "skip_story"}).get_json()
    assert r["guide"] is not None and r["guide"]["knowledge_id"] != g["knowledge_id"]
    assert {r["guide"]["knowledge_id"], g["knowledge_id"]} == {k1, k2}
    # wrong_info suspends the item
    r = client.post(f"/api/v1/guides/{hid}/feedback", headers=auth(t), json={"action": "wrong_info"})
    assert r.status_code == 200
    with session_scope(app) as db:
        item = db.get(KnowledgeItem, __import__("uuid").UUID(g["knowledge_id"]))
        assert item.review_status == "suspended"
    hist = client.get(f"/api/v1/trips/{trip}/history", headers=auth(t)).get_json()["items"]
    assert len(hist) == 2 and hist[0]["rating"] == "wrong_info"
    bad = client.post(f"/api/v1/guides/{hid}/feedback", headers=auth(t), json={"action": "nope"})
    assert bad.status_code == 400


def test_finish_and_late_points(app, client):
    t = register(client)
    add_item(app, "A", LAT, LON)
    trip = _trip(client, t)
    _send(client, t, trip, ctx(LAT, LON))

    class Summarizing:
        def summarize(self, trip_row, hist):
            raise AssertionError("finish must not wait on the summary model")

    app.extensions["lv_llm"] = Summarizing()
    r = client.post(f"/api/v1/trips/{trip}/finish", headers=auth(t)).get_json()
    assert r["ended_at"] and r["summary"]["guides"] == 1
    assert "これまでに話した話題" in r["summary"]["memory_summary"]
    from uuid import UUID

    from localvoice.models import TripSession

    with session_scope(app) as db:
        assert db.get(TripSession, UUID(trip)).state_json["summary_dirty"] is True
    res = _send(client, t, trip, ctx(LAT, LON, observed_at=iso_now(-30)))
    assert res["decision"]["reason"] == "trip_finished"
    assert len(client.get(f"/api/v1/trips/{trip}/track", headers=auth(t)).get_json()["points"]) == 2
    lst = client.get("/api/v1/trips", headers=auth(t)).get_json()["trips"]
    assert lst[0]["trip_id"] == trip


def test_hourly_limit_and_notification_level(app, client, monkeypatch):
    from localvoice.services.prefs import NOTIFICATION_LEVELS

    monkeypatch.setitem(NOTIFICATION_LEVELS["quiet"], "hourly_limit", 3)  # the default (1000) is effectively off
    t = register(client)
    for i in range(5):
        add_item(app, f"I{i}", LAT + i * 0.0003, LON, category=["history", "food", "nature", "culture", "industry"][i])
    trip = _trip(client, t, notification_level="quiet")
    from localvoice.models import NotificationHistory
    from datetime import timedelta
    from localvoice.util import now

    assert _send(client, t, trip, ctx(LAT, LON))["guide"] is not None
    # pretend previous guides were older than cooldown but within the hour
    for n in range(2):
        with session_scope(app) as db:
            for h in db.execute(select(NotificationHistory)).scalars():
                h.shown_at = h.shown_at - timedelta(minutes=16)
        assert _send(client, t, trip, ctx(LAT, LON))["guide"] is not None
    with session_scope(app) as db:
        for h in db.execute(select(NotificationHistory)).scalars():
            h.shown_at = h.shown_at - timedelta(minutes=16)
            assert h.shown_at > now() - timedelta(hours=1)
    assert _send(client, t, trip, ctx(LAT, LON))["decision"]["reason"] == "hourly_limit"


def test_preferences_and_interests(client):
    t = register(client)
    p = client.get("/api/v1/users/me/preferences", headers=auth(t)).get_json()
    assert p["voice"]["enabled"] is True
    assert p["voice"]["allow_device_tts_fallback"] is True
    r = client.patch(
        "/api/v1/users/me/preferences",
        headers=auth(t),
        json={"notification_level": "chatty", "voice": {"enabled": True, "voices": {"ja": "ja-bright"}, "playback_rate": 1.2}},
    )
    assert r.status_code == 200 and r.get_json()["voice"]["voices"]["ja"] == "ja-bright"
    assert client.patch("/api/v1/users/me/preferences", headers=auth(t), json={"voice": {"voices": {"ja": "x"}}}).status_code == 400
    r = client.patch(
        "/api/v1/users/me/interests", headers=auth(t), json={"interests": [{"category": "food", "explicit_score": 1}]}
    )
    food = [i for i in r.get_json()["interests"] if i["category"] == "food"][0]
    assert food["explicit_score"] == 1.0


def test_new_trip_prefers_stories_not_heard_on_earlier_trips(app, client):
    t = register(client)
    first = add_item(app, "A", LAT + 0.0005, LON, interestingness=0.9)
    second = add_item(app, "B", LAT - 0.001, LON, interestingness=0.6)
    trip1 = _trip(client, t)
    assert _send(client, t, trip1, ctx(LAT, LON))["guide"]["knowledge_id"] == first
    assert client.post(f"/api/v1/trips/{trip1}/finish", headers=auth(t)).status_code == 200
    # Same place, new trip: the story heard on the previous trip waits behind the unheard one,
    # even though it scores higher.
    trip2 = _trip(client, t)
    res = _send(client, t, trip2, ctx(LAT, LON))
    assert res["guide"]["knowledge_id"] == second
    with session_scope(app) as db:
        d = db.execute(select(GuideDecision).where(GuideDecision.trip_session_id == trip2)).scalars().one()
        assert [c["knowledge_id"] for c in d.candidates_json] == [second]


def test_heard_story_is_retold_when_nothing_unheard_fits(app, client):
    t = register(client)
    kid = add_item(app, "A", LAT + 0.0005, LON)
    trip1 = _trip(client, t)
    assert _send(client, t, trip1, ctx(LAT, LON))["guide"]["knowledge_id"] == kid
    client.post(f"/api/v1/trips/{trip1}/finish", headers=auth(t))
    trip2 = _trip(client, t)
    res = _send(client, t, trip2, ctx(LAT, LON))
    assert res["guide"]["knowledge_id"] == kid
    # another user has not heard it, so it is not marked for them
    other = register(client, "bob")
    trip3 = _trip(client, other)
    _send(client, other, trip3, ctx(LAT, LON))
    with session_scope(app) as db:
        heard = {
            str(d.trip_session_id): d.candidates_json[0]["heard_before"]
            for d in db.execute(select(GuideDecision)).scalars()
        }
    assert heard == {trip1: False, trip2: True, trip3: False}


def test_pacing_is_explained_and_speaking_is_not_interrupted(app, client):
    t = register(client)
    add_item(app, "A", LAT + 0.001, LON)
    add_item(app, "B", LAT - 0.001, LON)
    trip = _trip(client, t)
    first = _send(client, t, trip, ctx(LAT, LON))
    d = first["decision"]
    assert first["guide"] is not None
    assert d["notification_level"] == "normal" and d["cooldown_sec"] == 360 and d["next_check_after_sec"] == 360
    res = _send(client, t, trip, dict(ctx(LAT, LON), speaking=True))
    assert res["decision"]["reason"] == "cooldown"  # the cooldown is what the app should show
    from datetime import timedelta
    from localvoice.models import NotificationHistory

    with session_scope(app) as db:
        for h in db.execute(select(NotificationHistory)).scalars():
            h.shown_at = h.shown_at - timedelta(minutes=7)
    res = _send(client, t, trip, dict(ctx(LAT, LON), speaking=True))
    assert res["guide"] is None and res["decision"]["reason"] == "speaking"
    assert res["decision"]["cooldown_sec"] == 360


def test_no_candidates_reports_search_state(app, client, monkeypatch):
    t = register(client)
    trip = _trip(client, t)
    res = _send(client, t, trip, ctx(LAT, LON))
    # generation is enabled in tests' config or not; either way the app is told whether stories are being looked for
    assert res["decision"]["reason"] == "no_candidates" and isinstance(res["decision"]["searching"], bool)
    from localvoice.services import engine

    monkeypatch.setattr(engine, "_generation_running", lambda *a: True)
    res = _send(client, t, trip, ctx(LAT, LON))
    assert res["decision"]["searching"] is True and res["decision"]["next_check_after_sec"] == 30


def test_continuous_mode_moves_on_without_skip(app, client):
    from localvoice.models import NotificationHistory

    t = register(client)
    for i in range(3):
        add_item(app, f"C{i}", LAT + i * 0.0004, LON, category=["history", "food", "nature"][i])
    trip = _trip(client, t, notification_level="continuous")
    first = _send(client, t, trip, ctx(LAT, LON))
    assert first["guide"] is not None and first["decision"]["cooldown_sec"] == 15
    r = client.post(f"/api/v1/guides/{first['guide']['history_id']}/feedback", headers=auth(t),
                    json={"action": "continue"}).get_json()
    second = r["guide"]
    assert second is not None and second["knowledge_id"] != first["guide"]["knowledge_id"]
    assert r["decision"]["notification_level"] == "continuous"
    # continuing from an older story does not start a second one on top of the newest
    again = client.post(f"/api/v1/guides/{first['guide']['history_id']}/feedback", headers=auth(t),
                        json={"action": "continue"}).get_json()
    assert again["guide"] is None and again["decision"]["reason"] == "superseded"
    with session_scope(app) as db:
        rows = db.execute(select(NotificationHistory).order_by(NotificationHistory.shown_at)).scalars().all()
        assert not rows[0].skipped  # heard to the end, not skipped
        assert all(h.channel == "auto" for h in rows)
    # the short cooldown keeps a location update from cutting in right after the continued story starts
    res = _send(client, t, trip, ctx(LAT, LON))
    assert res["guide"] is None and res["decision"]["reason"] == "cooldown"


def test_continue_respects_quiet_mode(app, client):
    t = register(client)
    add_item(app, "Q1", LAT + 0.001, LON)
    add_item(app, "Q2", LAT - 0.001, LON, category="food")
    trip = _trip(client, t, notification_level="continuous")
    first = _send(client, t, trip, ctx(LAT, LON))["guide"]
    assert client.post(f"/api/v1/trips/{trip}/states", headers=auth(t), json={"type": "quiet", "minutes": 30}).status_code in (200, 201)
    r = client.post(f"/api/v1/guides/{first['history_id']}/feedback", headers=auth(t),
                    json={"action": "continue"}).get_json()
    assert r["guide"] is None and r["decision"]["reason"] == "quiet_mode"
