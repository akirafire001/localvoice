"""While one story plays, select and synthesize the next two so "next story" does not wait on the model.

Prepared stories are not shown yet: they sit on the trip until the traveller asks, and they are dropped when
the traveller has moved out of the area they were chosen for, or when feedback changes what should come next.
"""
import logging
import threading
import time
import uuid

from sqlalchemy import select

from ..models import KnowledgeItem, NotificationHistory, TripSession, User
from ..util import now
from . import engine, geo, voice

log = logging.getLogger(__name__)

AHEAD = 2
STALE_FILL_SEC = 120


class _Told:
    """A prepared story treated as already heard while choosing the one after it."""

    def __init__(self, draft):
        self.knowledge_item_id = uuid.UUID(draft["knowledge_item_id"])
        self.title = draft["title"]
        self.score_components = draft.get("score_components") or {}
        self.speech_snapshot_json = draft.get("speech") or {}
        self.channel = "manual"
        self.shown_at = now()


def _upcoming(trip):
    return dict((trip.state_json or {}).get("upcoming") or {})


def _write(trip, upcoming):
    state = dict(trip.state_json or {})
    state["upcoming"] = upcoming
    trip.state_json = state


def close_enough(snap, upcoming):
    if upcoming.get("lat") is None or upcoming.get("lon") is None:
        return False
    lat, lon = engine.snapshot_point(snap)
    tclass = snap.inferred_transport_mode or upcoming.get("transport_class") or "walking"
    radius = geo.SEARCH_RADIUS_M.get(tclass, 700)
    return geo.haversine_m(upcoming["lat"], upcoming["lon"], lat, lon) <= max(200, radius * 0.5)


def schedule(db, trip, anchor_history_id, snap, *, keep_stories=()):
    """Remember which story is playing and which later ones are already prepared. Returns True when more are needed."""
    prev = _upcoming(trip)
    lat, lon = engine.snapshot_point(snap)
    stories = list(keep_stories)[:AHEAD]
    _write(trip, {
        "token": int(prev.get("token") or 0) + 1,
        "anchor_history_id": str(anchor_history_id),
        "lat": lat,
        "lon": lon,
        "transport_class": snap.inferred_transport_mode or "walking",
        "stories": stories,
        "filling": False,
        "started_at": None,
    })
    return len(stories) < AHEAD


def invalidate(db, trip, anchor_history_id, snap):
    """Drop prepared stories after feedback that changes what should be told next."""
    anchor = _upcoming(trip).get("anchor_history_id")
    if anchor and anchor != str(anchor_history_id):
        return False
    return schedule(db, trip, anchor_history_id, snap, keep_stories=[])


def note_position(db, trip, snap):
    """When the traveller leaves the area the queue was built for, choose again from here."""
    upcoming = _upcoming(trip)
    if not upcoming.get("anchor_history_id") or not upcoming.get("stories"):
        return False
    if close_enough(snap, upcoming):
        return False
    return schedule(db, trip, upcoming["anchor_history_id"], snap, keep_stories=[])


def take(db, trip, user, snap, history_id, trigger="skip_story"):
    """Publish the prepared next story when it still matches this request. None when the caller should select now.

    trigger: "skip_story" for a tap on "next", "continue" when continuous mode moves on after a story ends."""
    trip = db.execute(select(TripSession).where(TripSession.id == trip.id).with_for_update()).scalar_one()
    upcoming = _upcoming(trip)
    stories = list(upcoming.get("stories") or [])
    if upcoming.get("anchor_history_id") != str(history_id) or not stories or not close_enough(snap, upcoming):
        return None
    published = engine.materialize(db, trip, user, snap, {**stories[0], "trigger": trigger})
    if published is None:
        upcoming["stories"] = stories[1:]
        _write(trip, upcoming)
        return {"result": None, "remaining": []}
    lat, lon = engine.snapshot_point(snap)
    remaining = stories[1:]
    upcoming.update({
        "anchor_history_id": published["guide"]["history_id"],
        "lat": lat,
        "lon": lon,
        "transport_class": snap.inferred_transport_mode or upcoming.get("transport_class") or "walking",
        "stories": remaining,
        "filling": False,
    })
    _write(trip, upcoming)
    return {"result": published, "remaining": remaining}


def kick(app, trip_id):
    """Start preparation on the web process. Tests call prepare() themselves so requests stay synchronous."""
    if app.config["LV"].TESTING:
        return

    def run():
        with app.app_context():
            try:
                prepare(app, trip_id)
            except Exception:
                log.exception("preparing upcoming stories failed for %s", trip_id)

    threading.Thread(target=run, name=f"next-{trip_id}", daemon=True).start()


def prepare(app, trip_id):
    """Select and synthesize stories until two are waiting after the one now playing."""
    db = app.extensions["lv_sessionmaker"]()
    token = None
    try:
        token = _claim(db, trip_id)
        if token is None:
            return 0
        return _fill(db, trip_id, token)
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            if token is not None:
                _release(db, trip_id, token)
        finally:
            db.close()


def prepare_upcoming(app, limit=5):
    """Worker backup for a preparation the web process did not finish."""
    db = app.extensions["lv_sessionmaker"]()
    try:
        trips = db.execute(select(TripSession).where(TripSession.ended_at.is_(None)).limit(50)).scalars().all()
        ids = []
        for trip in trips:
            upcoming = _upcoming(trip)
            if upcoming.get("anchor_history_id") and not upcoming.get("exhausted") and len(upcoming.get("stories") or []) < AHEAD:
                ids.append(trip.id)
            if len(ids) >= limit:
                break
    finally:
        db.close()
    for trip_id in ids:
        try:
            prepare(app, trip_id)
        except Exception:
            log.exception("preparing upcoming stories failed for %s", trip_id)
    return len(ids)


def _claim(db, trip_id):
    trip = db.execute(select(TripSession).where(TripSession.id == trip_id).with_for_update()).scalar_one_or_none()
    if trip is None or trip.ended_at is not None:
        return None
    upcoming = _upcoming(trip)
    if not upcoming.get("anchor_history_id") or len(upcoming.get("stories") or []) >= AHEAD:
        return None
    started = upcoming.get("started_at")
    if upcoming.get("exhausted"):
        return None
    if upcoming.get("filling") and isinstance(started, (int, float)) and time.time() - started < STALE_FILL_SEC:
        return None
    upcoming["filling"] = True
    upcoming["started_at"] = time.time()
    _write(trip, upcoming)
    token = upcoming.get("token")
    db.commit()
    return token


def _release(db, trip_id, token):
    db.rollback()
    db.expire_all()
    trip = db.execute(select(TripSession).where(TripSession.id == trip_id).with_for_update()).scalar_one_or_none()
    if trip is None:
        return
    upcoming = _upcoming(trip)
    if upcoming.get("token") != token:
        return
    upcoming["filling"] = False
    _write(trip, upcoming)
    db.commit()


def _fill(db, trip_id, token):
    added = 0
    while True:
        db.expire_all()
        trip = db.get(TripSession, trip_id)
        user = db.get(User, trip.user_id)
        upcoming = _upcoming(trip)
        if upcoming.get("token") != token or trip.ended_at is not None:
            return added
        stories = list(upcoming.get("stories") or [])
        if len(stories) >= AHEAD:
            return added
        anchor = db.get(NotificationHistory, uuid.UUID(upcoming["anchor_history_id"]))
        snap = engine.latest_snapshot(db, trip)
        if anchor is None or snap is None or not close_enough(snap, upcoming):
            return added
        exclude = [anchor.knowledge_item_id] + [uuid.UUID(s["knowledge_item_id"]) for s in stories]
        planned = engine.evaluate(
            db, trip, user, snap, trigger="skip_story", exclude_ids=exclude, record=False,
            extra_history=[_Told(s) for s in stories], seed_extra=len(stories) + 1,
        )
        draft = planned.get("draft")
        if not draft:
            _mark_exhausted(db, trip_id, token)
            return added
        item = db.get(KnowledgeItem, uuid.UUID(draft["knowledge_item_id"]))
        voices = {
            n["language"]: engine.default_voice(user, n["language"])
            for n in draft["speech"].get("narrations") or [] if n.get("language")
        }
        draft["speech"] = voice.warm_narrations(
            db, item=item, speech=draft["speech"], voices=voices, trip_id=trip.id, user_id=user.id,
            detail_mode=draft.get("detail_mode") or "auto",
        )
        if not _append(db, trip_id, token, draft):
            return added
        added += 1


def _mark_exhausted(db, trip_id, token):
    db.expire_all()
    trip = db.execute(select(TripSession).where(TripSession.id == trip_id).with_for_update()).scalar_one()
    upcoming = _upcoming(trip)
    if upcoming.get("token") == token:
        upcoming["exhausted"] = True
        upcoming["filling"] = False
        _write(trip, upcoming)
    db.commit()


def _append(db, trip_id, token, draft):
    db.expire_all()
    trip = db.execute(select(TripSession).where(TripSession.id == trip_id).with_for_update()).scalar_one()
    upcoming = _upcoming(trip)
    if upcoming.get("token") != token:
        return False
    stories = list(upcoming.get("stories") or [])
    if any(s["knowledge_item_id"] == draft["knowledge_item_id"] for s in stories) or len(stories) >= AHEAD:
        db.commit()
        return False
    stories.append(draft)
    upcoming["stories"] = stories
    upcoming["filling"] = True
    _write(trip, upcoming)
    db.commit()
    return True
