"""Trips, context, history and track (api-design)."""
import base64
import json
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request
from geoalchemy2.shape import to_shape
from sqlalchemy import and_, func, or_, select

from ..auth.sessions import require_auth
from ..db import get_db
from ..errors import ApiError, bad_request, not_found
from ..models import ApiUsageLog, ContextSnapshot, GuideDecision, NotificationHistory, TripSession
from ..services import engine, memory, next_story
from ..services.prefs import (
    DETAIL_MODES,
    LANGUAGES,
    MANUAL_TRANSPORT_MODES,
    NOTIFICATION_LEVELS,
    PURPOSES,
    SELECTION_MODES,
    SERENDIPITY_LEVELS,
    CATEGORIES,
)
from ..util import iso, json_body, now, parse_datetime, parse_uuid

bp = Blueprint("trips", __name__)


def _cfg():
    return current_app.config["LV"]


def get_owned_trip(db, trip_id, lock=False):
    trip = db.get(TripSession, parse_uuid(trip_id, "trip_id"), with_for_update=lock)
    # Same 404 for "missing" and "not yours" so IDs cannot be probed.
    if trip is None or trip.user_id != g.user.id:
        raise not_found("trip not found")
    return trip


def _apply_settings(trip, data):
    settings = dict(trip.settings_json or {})
    s = data.get("settings") or {}
    if not isinstance(s, dict):
        raise bad_request("settings must be an object")
    checks = {
        "notification_level": set(NOTIFICATION_LEVELS),
        "detail_mode": DETAIL_MODES,
        "serendipity": set(SERENDIPITY_LEVELS),
    }
    for k, allowed in checks.items():
        if k in s:
            if s[k] not in allowed:
                raise bad_request(f"settings.{k} must be one of {sorted(allowed)}", {"field": k})
            settings[k] = s[k]
    if "focus_categories" in s:
        cats = s["focus_categories"] or []
        if not isinstance(cats, list) or any(c not in CATEGORIES for c in cats):
            raise bad_request("invalid focus_categories")
        settings["focus_categories"] = cats
    if "selection_mode" in s:
        if s["selection_mode"] not in SELECTION_MODES:
            raise bad_request("settings.selection_mode must be llm or rule")
        trip.selection_mode = s["selection_mode"]
    if "manual_transport_mode" in data:
        m = data["manual_transport_mode"]
        if m not in MANUAL_TRANSPORT_MODES:
            raise bad_request(f"manual_transport_mode must be one of {sorted(MANUAL_TRANSPORT_MODES)}")
        trip.manual_transport_mode = None if m == "auto" else m
    if "language" in data:
        if data["language"] not in LANGUAGES:
            raise bad_request(f"language must be one of {sorted(LANGUAGES)}")
        trip.language = data["language"]
    trip.settings_json = settings


def trip_payload(trip):
    return {
        "trip_id": str(trip.id),
        "purpose": trip.purpose,
        "language": trip.language,
        "started_at": iso(trip.started_at),
        "ended_at": iso(trip.ended_at),
        "selection_mode": trip.selection_mode,
        "manual_transport_mode": trip.manual_transport_mode or "auto",
        "settings": trip.settings_json or {},
    }


@bp.post("/trips")
@require_auth
def create_trip():
    db = get_db()
    data = json_body()
    purpose = data.get("purpose", "travel")
    if purpose not in PURPOSES:
        raise bad_request(f"purpose must be one of {sorted(PURPOSES)}")
    trip = TripSession(user_id=g.user.id, purpose=purpose, language=g.user.locale or "ja", settings_json={})
    _apply_settings(trip, data)
    db.add(trip)
    db.commit()
    body = trip_payload(trip)
    return jsonify(body), 201


@bp.get("/trips")
@require_auth
def list_trips():
    db = get_db()
    since = now() - timedelta(days=_cfg().TRACK_RETENTION_DAYS)
    trips = db.execute(
        select(TripSession)
        .where(TripSession.user_id == g.user.id, TripSession.started_at >= since)
        .order_by(TripSession.started_at.desc())
        .limit(100)
    ).scalars()
    return jsonify({"trips": [trip_payload(t) for t in trips]})


@bp.get("/trips/<trip_id>")
@require_auth
def get_trip(trip_id):
    return jsonify(trip_payload(get_owned_trip(get_db(), trip_id)))


@bp.patch("/trips/<trip_id>")
@require_auth
def patch_trip(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, lock=True)
    if trip.ended_at is not None:
        raise ApiError(409, "trip_finished", "trip already finished")
    _apply_settings(trip, json_body())
    db.commit()
    return jsonify(trip_payload(trip))


@bp.post("/trips/<trip_id>/finish")
@require_auth
def finish_trip(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, lock=True)
    if trip.ended_at is None:
        trip.ended_at = now()
        # A rule summary is enough to leave the screen. The worker replaces it with the LLM
        # summary; waiting for that model here held the phone on this request for many seconds.
        memory.update_summary(db, trip, final=True, use_llm=False)
        state = dict(trip.state_json or {})
        state["summary_dirty"] = True
        trip.state_json = state
    db.commit()
    return jsonify({**trip_payload(trip), "summary": trip_summary(db, trip)})


def trip_summary(db, trip):
    n_points = db.execute(
        select(func.count()).select_from(ContextSnapshot).where(ContextSnapshot.trip_session_id == trip.id)
    ).scalar_one()
    reasons = dict(
        db.execute(
            select(GuideDecision.reason, func.count())
            .where(GuideDecision.trip_session_id == trip.id)
            .group_by(GuideDecision.reason)
        ).all()
    )
    hist = list(
        db.execute(select(NotificationHistory).where(NotificationHistory.trip_session_id == trip.id)).scalars()
    )
    ratings = {}
    for h in hist:
        if h.rating:
            ratings[h.rating] = ratings.get(h.rating, 0) + 1
    fallbacks = db.execute(
        select(func.count()).select_from(GuideDecision).where(
            GuideDecision.trip_session_id == trip.id, GuideDecision.fallback.is_(True)
        )
    ).scalar_one()
    cost = db.execute(
        select(ApiUsageLog.provider, func.coalesce(func.sum(ApiUsageLog.estimated_cost), 0))
        .where(ApiUsageLog.trip_session_id == trip.id)
        .group_by(ApiUsageLog.provider)
    ).all()
    return {
        "context_snapshots": n_points,
        "guides": len(hist),
        "decisions_by_reason": reasons,
        "ratings": ratings,
        "llm_fallbacks": fallbacks,
        "estimated_cost_usd": {p: float(c) for p, c in cost},
        "memory_summary": trip.memory_summary,
    }


@bp.get("/trips/<trip_id>/summary")
@require_auth
def get_summary(trip_id):
    db = get_db()
    return jsonify(trip_summary(db, get_owned_trip(db, trip_id)))


@bp.post("/trips/<trip_id>/context")
@require_auth
def post_context(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, lock=True)  # serialize evaluation per trip
    ctx = engine.parse_context(json_body())
    snap, dup = engine.store_snapshot(db, trip, ctx)
    if dup:
        db.commit()
        return jsonify({"guide": None, "decision": {"reason": "duplicate_event", "next_check_after_sec": 60}})
    if trip.ended_at is not None:
        db.commit()
        return jsonify({"guide": None, "decision": {"reason": "trip_finished", "next_check_after_sec": None}})
    latest = engine.latest_snapshot(db, trip)
    stale = (now() - ctx["observed_at"]).total_seconds() > _cfg().FRESHNESS_SEC
    if stale or (latest is not None and latest.id != snap.id):
        # Late/resent past points are stored for the track only (api-design 冪等性/再送).
        db.commit()
        return jsonify({"guide": None, "decision": {"reason": "stale_event", "next_check_after_sec": 60}})
    result = engine.evaluate(db, trip, g.user, snap)
    prepare_more = False
    if result["guide"] is not None:
        memory.maybe_update(db, trip)
        prepare_more = next_story.schedule(db, trip, result["guide"]["history_id"], snap)
    elif next_story.note_position(db, trip, snap):
        prepare_more = True
    db.commit()
    if prepare_more:
        next_story.kick(current_app._get_current_object(), trip.id)
    return jsonify(result)


@bp.get("/trips/<trip_id>/history")
@require_auth
def get_history(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id)
    rows = db.execute(
        select(NotificationHistory)
        .where(NotificationHistory.trip_session_id == trip.id)
        .order_by(NotificationHistory.shown_at)
    ).scalars()
    return jsonify({"trip_id": str(trip.id), "items": [engine.history_payload(db, h, g.user) for h in rows]})


def _encode_cursor(observed_at, row_id):
    return base64.urlsafe_b64encode(json.dumps([observed_at.isoformat(), row_id]).encode()).decode()


def _decode_cursor(cursor):
    try:
        ts, rid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return parse_datetime(ts, "cursor"), int(rid)
    except Exception:  # noqa: BLE001
        raise bad_request("invalid cursor", {"field": "cursor"})


@bp.get("/trips/<trip_id>/track")
@require_auth
def get_track(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id)
    try:
        limit = int(request.args.get("limit", 500))
    except ValueError:
        raise bad_request("limit must be an integer")
    if not 1 <= limit <= 1000:
        raise bad_request("limit must be 1-1000")
    q = select(ContextSnapshot).where(ContextSnapshot.trip_session_id == trip.id)
    retention_floor = now() - timedelta(days=_cfg().TRACK_RETENTION_DAYS)
    q = q.where(ContextSnapshot.observed_at >= retention_floor)
    if request.args.get("from"):
        q = q.where(ContextSnapshot.observed_at >= parse_datetime(request.args["from"], "from"))
    if request.args.get("until"):
        q = q.where(ContextSnapshot.observed_at < parse_datetime(request.args["until"], "until"))
    if request.args.get("cursor"):
        cts, cid = _decode_cursor(request.args["cursor"])
        q = q.where(
            or_(ContextSnapshot.observed_at > cts, and_(ContextSnapshot.observed_at == cts, ContextSnapshot.id > cid))
        )
    rows = list(db.execute(q.order_by(ContextSnapshot.observed_at, ContextSnapshot.id).limit(limit + 1)).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    points = []
    for r in rows:
        p = to_shape(r.position)
        points.append(
            {
                "client_event_id": str(r.client_event_id),
                "observed_at": r.observed_at.isoformat(),
                "location": {"lat": p.y, "lon": p.x, "accuracy_m": float(r.accuracy_m) if r.accuracy_m is not None else None},
            }
        )
    return jsonify(
        {
            "trip_id": str(trip.id),
            "points": points,
            "next_cursor": _encode_cursor(rows[-1].observed_at, rows[-1].id) if more else None,
        }
    )
