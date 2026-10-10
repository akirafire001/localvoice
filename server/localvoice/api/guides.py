"""Guide feedback (api-design POST /guides/{history_id}/feedback)."""
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy import select

from ..auth.sessions import require_auth
from ..db import get_db
from ..errors import ApiError, bad_request, not_found
from ..models import KnowledgeItem, NotificationHistory, Participant, TopicBoost, TripSession, UserInterest
from ..services import engine, memory, next_story
from ..services.rendering import sources_payload
from ..util import json_body, now, parse_uuid

bp = Blueprint("guides", __name__)

RATINGS = {"interesting", "knew_it", "not_interesting", "wrong_info"}
ACTIONS = RATINGS | {"more_detail", "more_related", "enough_topic", "like", "dislike", "skip_story", "continue", "opened",
                     "spoken"}
LEARN = {"interesting": 0.1, "like": 0.1, "more_detail": 0.05, "more_related": 0.05, "not_interesting": -0.1, "dislike": -0.1}
# These change which story should come next, so anything already prepared is dropped.
INVALIDATE_NEXT = {"more_related", "enough_topic", "not_interesting", "dislike", "wrong_info"}


def get_owned_history(db, history_id):
    h = db.get(NotificationHistory, parse_uuid(history_id, "history_id"))
    if h is None:
        raise not_found("guide not found")
    trip = db.get(TripSession, h.trip_session_id)
    if trip is None or trip.user_id != g.user.id:
        raise not_found("guide not found")
    return h, trip


def _learn(db, user_id, category, delta=0.0, knowledge_delta=0.0):
    ui = db.get(UserInterest, (user_id, category))
    if ui is None:
        ui = UserInterest(user_id=user_id, category=category, learned_score=0, knowledge_score=0, confidence=0)
        db.add(ui)
    ui.learned_score = max(-0.5, min(0.5, float(ui.learned_score or 0) + delta))
    ui.knowledge_score = max(0.0, min(1.0, float(ui.knowledge_score or 0) + knowledge_delta))
    ui.confidence = min(1.0, float(ui.confidence or 0) + 0.05)
    ui.updated_at = now()


@bp.post("/guides/<history_id>/feedback")
@require_auth
def feedback(history_id):
    db = get_db()
    h, trip = get_owned_history(db, history_id)
    data = json_body()
    action = data.get("action")
    if action not in ACTIONS:
        raise bad_request(f"action must be one of {sorted(ACTIONS)}", {"field": "action"})
    if data.get("participant_id"):
        p = db.get(Participant, parse_uuid(data["participant_id"], "participant_id"))
        if p is None or p.trip_session_id != trip.id:
            raise not_found("participant not found")
    item = db.get(KnowledgeItem, h.knowledge_item_id)
    t = now()
    resp = {"status": "ok", "action": action}
    prepare_more = False

    if action == "opened":
        h.opened = True
    elif action == "spoken":
        h.spoken = True
    elif action in RATINGS:
        h.rating = action
        if action == "knew_it":
            _learn(db, g.user.id, item.category, knowledge_delta=0.1)
        elif action == "wrong_info":
            # Stop serving immediately and wait for review (realtime-llm-design §3.4)
            item.review_status = "suspended"
            meta = dict(item.metadata_json or {})
            meta.setdefault("wrong_info_reports", []).append({"history_id": str(h.id), "at": t.isoformat()})
            item.metadata_json = meta
        if action in LEARN:
            _learn(db, g.user.id, item.category, LEARN[action])
    else:
        h.feedback_type = action
        if action in LEARN:
            _learn(db, g.user.id, item.category, LEARN[action])
        if action == "more_detail":
            h.opened = True
            resp["detail_text"] = h.detail_text
            resp["sources"] = sources_payload(item)
        elif action == "more_related":
            topics = [item.category] + list((item.metadata_json or {}).get("topics", []))
            for topic in topics:
                db.add(TopicBoost(trip_session_id=trip.id, topic_key=topic, strength=0.8,
                                  expires_at=t + timedelta(hours=1), decay_rate=0.5))
            resp["topics"] = topics
        elif action == "enough_topic":
            # End the boost for this topic without lowering long-term interest
            for b in db.execute(
                select(TopicBoost).where(
                    TopicBoost.trip_session_id == trip.id, TopicBoost.topic_key == item.category,
                    TopicBoost.ended_at.is_(None),
                )
            ).scalars():
                b.ended_at = t
            db.add(TopicBoost(trip_session_id=trip.id, topic_key=item.category, strength=-1.0,
                              expires_at=t + timedelta(hours=2), decay_rate=0.25))
        elif action == "skip_story":
            h.skipped = True
            if trip.ended_at is not None:
                raise ApiError(409, "trip_finished", "trip already finished")
            snap = engine.latest_snapshot(db, trip)
            if snap is None:
                resp.update({"guide": None, "decision": {"reason": "no_context"}})
            else:
                taken = next_story.take(db, trip, g.user, snap, h.id)
                if taken and taken["result"]:
                    result, keep = taken["result"], taken["remaining"]
                else:
                    result = engine.evaluate(db, trip, g.user, snap, trigger="skip_story", exclude_ids=[item.id])
                    keep = []
                if result["guide"] is not None:
                    memory.maybe_update(db, trip)
                    prepare_more = next_story.schedule(db, trip, result["guide"]["history_id"], snap, keep_stories=keep)
                resp.update(result)
        elif action == "continue":
            # Continuous mode: this story was heard to the end, so tell the next one (not a skip).
            if trip.ended_at is not None:
                raise ApiError(409, "trip_finished", "trip already finished")
            result, keep = _continue(db, trip, h)
            if result["guide"] is not None:
                memory.maybe_update(db, trip)
                prepare_more = next_story.schedule(db, trip, result["guide"]["history_id"], result.pop("_snap"),
                                                   keep_stories=keep)
            result.pop("_snap", None)
            resp.update(engine.describe_pacing(result, trip, g.user))
    if action == "skip_story" and "decision" in resp:
        engine.describe_pacing(resp, trip, g.user)
    if action in INVALIDATE_NEXT and trip.ended_at is None:
        snap = engine.latest_snapshot(db, trip)
        if snap is not None:
            prepare_more = next_story.invalidate(db, trip, h.id, snap) or prepare_more
    db.commit()
    if prepare_more:
        next_story.kick(current_app._get_current_object(), trip.id)
    return jsonify(resp)


def _continue(db, trip, h):
    """The story after h for continuous mode. Returns (result, prepared stories to keep)."""
    # serialize with location updates for this trip, so the two never start a story each
    db.execute(select(TripSession.id).where(TripSession.id == trip.id).with_for_update())
    latest = db.execute(
        select(NotificationHistory.id)
        .where(NotificationHistory.trip_session_id == trip.id)
        .order_by(NotificationHistory.shown_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest != h.id:
        # a newer story already started (e.g. from a location update); it is the one playing now
        return {"guide": None, "decision": {"reason": "superseded", "next_check_after_sec": 60}}, []
    snap = engine.latest_snapshot(db, trip)
    if snap is None:
        return {"guide": None, "decision": {"reason": "no_context", "next_check_after_sec": 30}}, []
    quiet = engine.quiet_state(db, trip, now())
    if quiet is not None:
        wait = int((quiet.expires_at - now()).total_seconds())
        return {"guide": None, "decision": {"reason": "quiet_mode", "next_check_after_sec": wait}}, []
    taken = next_story.take(db, trip, g.user, snap, h.id, trigger="continue")
    if taken and taken["result"]:
        result, keep = taken["result"], taken["remaining"]
    else:
        result = engine.evaluate(db, trip, g.user, snap, trigger="continue", exclude_ids=[h.knowledge_item_id])
        keep = []
    if result is None:  # the chosen story was withdrawn meanwhile
        result = {"guide": None, "decision": {"reason": "no_candidates", "next_check_after_sec": 30}}
    result["_snap"] = snap
    return result, keep
