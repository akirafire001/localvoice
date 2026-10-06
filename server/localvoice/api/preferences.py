"""GET/PATCH /users/me/preferences and /users/me/interests."""
from flask import Blueprint, g, jsonify
from sqlalchemy import select

from ..auth.sessions import require_auth
from ..db import get_db
from ..errors import bad_request
from ..models import UserInterest
from ..services.prefs import CATEGORIES, DETAIL_MODES, LANGUAGES, NOTIFICATION_LEVELS, SERENDIPITY_LEVELS
from ..services.voice import allowed_voice_ids
from ..util import json_body, now

bp = Blueprint("preferences", __name__)

PLAYBACK_RATE_RANGE = (0.75, 1.5)


def _prefs(user):
    vs = user.voice_settings_json or {}
    return {
        "language": user.locale,
        "notification_level": user.notification_level,
        "detail_mode": user.detail_mode,
        "serendipity": user.serendipity_level,
        "voice": {
            "enabled": bool(vs.get("enabled", False)),  # never auto-enable audio (flutter-ux §8)
            "voices": vs.get("voices", {}),
            "playback_rate": vs.get("playback_rate", 1.0),
            "allow_device_tts_fallback": bool(vs.get("allow_device_tts_fallback", False)),
        },
    }


@bp.get("/users/me/preferences")
@require_auth
def get_preferences():
    return jsonify(_prefs(g.user))


@bp.patch("/users/me/preferences")
@require_auth
def patch_preferences():
    db = get_db()
    data = json_body()
    u = g.user
    if "language" in data:
        if data["language"] not in LANGUAGES:
            raise bad_request("language must be ja or en", {"field": "language"})
        u.locale = data["language"]
    for key, attr, allowed in (
        ("notification_level", "notification_level", set(NOTIFICATION_LEVELS)),
        ("detail_mode", "detail_mode", DETAIL_MODES),
        ("serendipity", "serendipity_level", set(SERENDIPITY_LEVELS)),
    ):
        if key in data:
            if data[key] not in allowed:
                raise bad_request(f"{key} must be one of {sorted(allowed)}", {"field": key})
            setattr(u, attr, data[key])
    if "voice" in data:
        v = data["voice"]
        if not isinstance(v, dict):
            raise bad_request("voice must be an object")
        vs = dict(u.voice_settings_json or {})
        if "enabled" in v:
            vs["enabled"] = bool(v["enabled"])
        if "allow_device_tts_fallback" in v:
            vs["allow_device_tts_fallback"] = bool(v["allow_device_tts_fallback"])
        if "playback_rate" in v:
            try:
                rate = float(v["playback_rate"])
            except (TypeError, ValueError):
                raise bad_request("playback_rate must be a number")
            if not PLAYBACK_RATE_RANGE[0] <= rate <= PLAYBACK_RATE_RANGE[1]:
                raise bad_request(f"playback_rate must be within {PLAYBACK_RATE_RANGE}")
            vs["playback_rate"] = rate
        if "voices" in v:
            voices = dict(vs.get("voices", {}))
            for lang, vid in (v["voices"] or {}).items():
                if lang not in LANGUAGES or vid not in allowed_voice_ids(lang):
                    raise bad_request(f"voice {vid!r} is not available for {lang!r}", {"field": "voices"})
                voices[lang] = vid
            vs["voices"] = voices
        u.voice_settings_json = vs
    db.commit()
    return jsonify(_prefs(u))


def _interests(db, user_id):
    rows = {r.category: r for r in db.execute(select(UserInterest).where(UserInterest.user_id == user_id)).scalars()}
    out = []
    for c in CATEGORIES:
        r = rows.get(c)
        out.append(
            {
                "category": c,
                "explicit_score": float(r.explicit_score) if r and r.explicit_score is not None else None,
                "learned_score": float(r.learned_score) if r else 0.0,
                "knowledge_score": float(r.knowledge_score) if r else 0.0,
            }
        )
    return out


@bp.get("/users/me/interests")
@require_auth
def get_interests():
    return jsonify({"interests": _interests(get_db(), g.user.id)})


@bp.patch("/users/me/interests")
@require_auth
def patch_interests():
    db = get_db()
    data = json_body()
    items = data.get("interests")
    if not isinstance(items, list):
        raise bad_request("interests must be a list of {category, explicit_score}")
    for it in items:
        cat = (it or {}).get("category")
        if cat not in CATEGORIES:
            raise bad_request(f"unknown category {cat!r}", {"field": "category"})
        score = it.get("explicit_score")
        if score is not None:
            try:
                score = float(score)
            except (TypeError, ValueError):
                raise bad_request("explicit_score must be a number")
            if not 0 <= score <= 1:
                raise bad_request("explicit_score must be within 0..1")
        ui = db.get(UserInterest, (g.user.id, cat))
        if ui is None:
            ui = UserInterest(user_id=g.user.id, category=cat, learned_score=0, knowledge_score=0, confidence=0)
            db.add(ui)
        ui.explicit_score = score
        ui.updated_at = now()
    db.commit()
    return jsonify({"interests": _interests(db, g.user.id)})
