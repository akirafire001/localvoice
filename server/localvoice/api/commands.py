"""P1: POST /trips/{id}/commands, overrides, temporary states, participants (api-design P1)."""
import logging

from flask import Blueprint, current_app, jsonify
from sqlalchemy import select

from ..auth.sessions import require_auth
from ..db import get_db
from ..errors import ApiError, bad_request, not_found
from ..models import ApiUsageLog, IntentOverride, Participant, TemporaryState
from ..services import commands
from ..services.engine import llm_cost_so_far
from ..services.llm import LLMError, _MetaError, get_llm, llm_provider
from ..services.prefs import LANGUAGES
from ..util import json_body, now, parse_uuid, require_str
from .trips import get_owned_trip

bp = Blueprint("commands", __name__)
log = logging.getLogger(__name__)

MAX_PARTICIPANTS = 8


def _active_payload(db, trip):
    t = now()
    return [commands.override_payload(o) for o in commands.active_overrides(db, trip.id, t)] + [
        commands.state_payload(s, trip.language) for s in commands.active_states(db, trip.id, t)
    ]


def _parse(db, trip, text):
    cfg = current_app.config["LV"]
    llm = get_llm()
    if llm is not None and hasattr(llm, "parse_command") and trip.selection_mode == "llm" \
            and llm_cost_so_far(db, trip.id) < cfg.LLM_SESSION_COST_LIMIT_USD:
        meta = {}
        try:
            data, meta = llm.parse_command(text, trip.language)
            parsed = commands.validate_llm(data)
            # A model that understood nothing gets a second chance from the keyword parser.
            if parsed.intents or parsed.states or parsed.resume:
                return parsed, meta
        except _MetaError as e:
            meta = e.meta
            log.info("command parse fell back: %s", e.code)
        except LLMError as e:
            log.info("command parse fell back: %s", e)
        finally:
            if meta.get("model"):
                db.add(ApiUsageLog(trip_session_id=trip.id, provider=llm_provider(llm), operation="parse_command",
                                   request_units=1, estimated_cost=meta.get("cost_usd") or 0,
                                   details_json={"model": meta.get("model"), "latency_ms": meta.get("latency_ms")}))
    return commands.rule_parse(text), {}


@bp.post("/trips/<trip_id>/commands")
@require_auth
def post_command(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, lock=True)
    if trip.ended_at is not None:
        raise ApiError(409, "trip_finished", "trip already finished")
    text = require_str(json_body(), "text", max_len=500)
    parsed, _meta = _parse(db, trip, text.strip())
    if not (parsed.intents or parsed.states or parsed.resume):
        db.commit()
        raise ApiError(422, "command_not_understood", "could not understand the instruction",
                       {"hint": "e.g. 「しばらく建築を多めに」「30分静かに」"})
    intents, states, confirm = commands.apply(db, trip, parsed, text)
    db.commit()
    created = [commands.override_payload(o) for o in intents] + [
        commands.state_payload(s, trip.language) for s in states
    ]
    return jsonify({
        "created": created,
        "resumed": parsed.resume,
        "needs_confirmation": confirm,
        "parser": parsed.parser,
        "active": _active_payload(db, trip),
    }), 201


@bp.get("/trips/<trip_id>/overrides")
@require_auth
def list_overrides(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id)
    return jsonify({"active": _active_payload(db, trip)})


@bp.delete("/trips/<trip_id>/overrides/<override_id>")
@require_auth
def delete_override(trip_id, override_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id)
    oid = parse_uuid(override_id, "override_id")
    row = db.get(IntentOverride, oid) or db.get(TemporaryState, oid)
    if row is None or row.trip_session_id != trip.id:
        raise not_found("override not found")
    if row.ended_at is None:
        row.ended_at = now()
    db.commit()
    return jsonify({"active": _active_payload(db, trip)})


@bp.post("/trips/<trip_id>/states")
@require_auth
def post_state(trip_id):
    """One-tap temporary state from the UI (e.g. the quiet button)."""
    db = get_db()
    trip = get_owned_trip(db, trip_id, lock=True)
    if trip.ended_at is not None:
        raise ApiError(409, "trip_finished", "trip already finished")
    data = json_body()
    st = data.get("type")
    if st not in commands.STATE_TYPES:
        raise bad_request(f"type must be one of {sorted(commands.STATE_TYPES)}", {"field": "type"})
    minutes = commands._clamp(data.get("minutes"), commands.STATE_TYPES[st])
    parsed = commands.ParsedCommand(states=[{"type": st, "ttl_min": minutes}], parser="ui")
    _, states, _ = commands.apply(db, trip, parsed, "", source="ui")
    db.commit()
    return jsonify({"created": [commands.state_payload(s, trip.language) for s in states],
                    "active": _active_payload(db, trip)}), 201


def _participant_payload(p):
    return {"participant_id": str(p.id), "display_name": p.display_name, "locale": p.locale,
            "home_region": p.home_region, "interests": (p.profile_json or {}).get("interests", [])}


@bp.get("/trips/<trip_id>/participants")
@require_auth
def list_participants(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id)
    rows = db.execute(select(Participant).where(Participant.trip_session_id == trip.id)).scalars()
    return jsonify({"participants": [_participant_payload(p) for p in rows]})


@bp.post("/trips/<trip_id>/participants")
@require_auth
def add_participant(trip_id):
    """Companion profile kept on the host's trip (no account for the companion)."""
    db = get_db()
    trip = get_owned_trip(db, trip_id, lock=True)
    data = json_body()
    name = require_str(data, "display_name", max_len=100)
    locale = data.get("locale")
    if locale is not None and locale not in LANGUAGES:
        raise bad_request(f"locale must be one of {sorted(LANGUAGES)}", {"field": "locale"})
    home = require_str(data, "home_region", max_len=200, required=False)
    interests = data.get("interests") or []
    if not isinstance(interests, list) or any(c not in commands.CATEGORY_WORDS for c in interests):
        raise bad_request("interests must be a list of categories", {"field": "interests"})
    count = len(list(db.execute(select(Participant.id).where(Participant.trip_session_id == trip.id))))
    if count >= MAX_PARTICIPANTS:
        raise ApiError(409, "too_many_participants", f"up to {MAX_PARTICIPANTS} participants")
    p = Participant(trip_session_id=trip.id, display_name=name, locale=locale, home_region=home,
                    profile_json={"interests": sorted(set(interests))})
    db.add(p)
    db.commit()
    return jsonify(_participant_payload(p)), 201


@bp.delete("/trips/<trip_id>/participants/<participant_id>")
@require_auth
def delete_participant(trip_id, participant_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id)
    p = db.get(Participant, parse_uuid(participant_id, "participant_id"))
    if p is None or p.trip_session_id != trip.id:
        raise not_found("participant not found")
    db.delete(p)
    db.commit()
    return "", 204
