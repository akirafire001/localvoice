"""The next two stories, including their audio, are prepared while the current one is playing."""
import uuid

from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import AudioAsset, TripSession
from localvoice.services import next_story

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx
from .test_llm_and_generation import FakeLLM

LAT, LON = MIYAJIMA


def test_two_stories_are_ready_before_skip(app, client):
    fake = FakeLLM("first")
    app.extensions["lv_llm"] = fake
    t = register(client)
    ids = [
        add_item(app, "近い", LAT, LON, category="history"),
        add_item(app, "次", LAT + 0.0008, LON, category="food"),
        add_item(app, "その次", LAT + 0.0016, LON, category="nature"),
    ]
    trip = client.post("/api/v1/trips", headers=auth(t), json={"purpose": "travel"}).get_json()["trip_id"]
    shown = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()["guide"]
    assert shown["knowledge_id"] == ids[0]
    assert len(fake.calls) == 1

    with app.app_context():
        assert next_story.prepare(app, uuid.UUID(trip)) == 2

    with session_scope(app) as db:
        queued = db.get(TripSession, uuid.UUID(trip)).state_json["upcoming"]["stories"]
        ready = [a.status for a in db.execute(select(AudioAsset)).scalars()]
    assert [s["knowledge_item_id"] for s in queued] == ids[1:]
    assert ready and set(ready) == {"ready"}
    prepared = len(fake.calls)

    first = client.post(
        f"/api/v1/guides/{shown['history_id']}/feedback", headers=auth(t), json={"action": "skip_story"}
    ).get_json()["guide"]
    assert first["knowledge_id"] == ids[1]
    assert len(fake.calls) == prepared  # the prepared story is published without another selection
    speech = client.post(
        f"/api/v1/guides/{first['history_id']}/speech",
        headers=auth(t), json={"voice_profile_id": "ja-default", "language": "ja"},
    )
    assert speech.status_code == 200

    second = client.post(
        f"/api/v1/guides/{first['history_id']}/feedback", headers=auth(t), json={"action": "skip_story"}
    ).get_json()["guide"]
    assert second["knowledge_id"] == ids[2]
    assert len(fake.calls) == prepared


def test_automatic_story_after_cooldown_uses_the_prepared_one(app, client):
    from datetime import timedelta

    from localvoice.models import NotificationHistory

    fake = FakeLLM("first")
    app.extensions["lv_llm"] = fake
    t = register(client)
    ids = [
        add_item(app, "近い", LAT, LON, category="history"),
        add_item(app, "次", LAT + 0.0008, LON, category="food"),
        add_item(app, "その次", LAT + 0.0016, LON, category="nature"),
    ]
    trip = client.post("/api/v1/trips", headers=auth(t), json={"purpose": "travel"}).get_json()["trip_id"]
    shown = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()["guide"]
    assert shown["knowledge_id"] == ids[0]
    with app.app_context():
        assert next_story.prepare(app, uuid.UUID(trip)) == 2
    prepared = len(fake.calls)
    with session_scope(app) as db:
        for h in db.execute(select(NotificationHistory)).scalars():
            h.shown_at = h.shown_at - timedelta(minutes=7)  # past the 360 s cooldown
    res = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()
    assert res["guide"]["knowledge_id"] == ids[1] and "_keep" not in res
    assert len(fake.calls) == prepared  # no new selection: the story (and its audio) was ready
    with session_scope(app) as db:
        upcoming = db.get(TripSession, uuid.UUID(trip)).state_json["upcoming"]
        assert [s["knowledge_item_id"] for s in upcoming["stories"]] == ids[2:]
        assert upcoming["anchor_history_id"] == res["guide"]["history_id"]
        latest = db.execute(select(NotificationHistory).order_by(NotificationHistory.shown_at.desc())).scalars().first()
        assert latest.channel == "auto"
