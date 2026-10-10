"""GET /languages, GET /voices, POST /guides/{id}/speech, GET /speech-assets/{id} (api-design 音声)."""
from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import func, select

from ..auth.sessions import require_auth
from ..db import get_db
from ..errors import ApiError, bad_request, not_found
from ..models import AudioAsset, KnowledgeItem, NotificationHistory, TripSession
from ..services import languages, translation, voice
from ..services.prefs import trip_settings
from ..util import json_body, now, parse_uuid
from .guides import get_owned_history

bp = Blueprint("voices", __name__)


def _asset_body(asset):
    if asset.status == "ready":
        return {
            "status": "ready",
            "asset_id": str(asset.id),
            "audio_path": f"/api/v1/speech-assets/{asset.id}",
            "audio_format": asset.audio_format,
            "duration_ms": asset.duration_ms,
            "valid_until": asset.valid_until.isoformat() if asset.valid_until else None,
            "attribution": asset.attribution_json or [],
        }, 200
    if asset.status == "failed":
        raise ApiError(503, "tts_failed", "speech generation failed", headers={"Retry-After": "30"})
    return {"status": "pending", "asset_id": str(asset.id), "retry_after_sec": 2}, 202


@bp.get("/languages")
@require_auth
def list_languages():
    """Languages for the settings screen: the app's screens (one) and narration (several, in order)."""
    return jsonify(languages.catalog())


@bp.get("/voices")
@require_auth
def list_voices():
    lang = request.args.get("language")
    out = []
    for vid, p in voice.VOICE_PROFILES.items():
        if lang and p["language"] != lang:
            continue
        out.append({
            "voice_profile_id": vid,
            "display_name": p["display_name"],
            "language": p["language"],
            "sample_text": voice.SAMPLE_TEXT[p["language"]],
            "sample_endpoint": f"/api/v1/voices/{vid}/sample",  # POST → asset, then GET audio_path
            "credits": [],
        })
    return jsonify({"voices": out, "tts_available": voice.get_provider() is not None})


@bp.post("/voices/<voice_profile_id>/sample")
@require_auth
def voice_sample(voice_profile_id):
    if voice_profile_id not in voice.VOICE_PROFILES:
        raise not_found("voice not found")
    db = get_db()
    asset, provider = voice.sample_asset(db, voice_profile_id)
    if asset is None:
        raise ApiError(503, "tts_unavailable", "speech synthesis is not available")
    db.commit()
    if asset.status in ("pending", "invalidated"):
        asset = voice.synthesize_asset(db, asset, provider)
    body, status = _asset_body(asset)
    return jsonify(body), status


@bp.post("/guides/<history_id>/speech")
@require_auth
def guide_speech(history_id):
    db = get_db()
    h, trip = get_owned_history(db, history_id)
    data = json_body()
    vid = data.get("voice_profile_id")
    # one of the guide's narration languages; without it, the screen language (apps before narration languages)
    lang = data.get("language") or h.language
    if vid not in voice.VOICE_PROFILES:
        raise bad_request("unknown voice_profile_id", {"field": "voice_profile_id"})
    if voice.VOICE_PROFILES[vid]["language"] != lang:
        raise bad_request("voice language does not match the guide", {"field": "voice_profile_id"})
    item = db.get(KnowledgeItem, h.knowledge_item_id)
    snap = h.speech_snapshot_json or {}
    expired = item.valid_until is not None and item.valid_until <= now()
    if item.review_status == "suspended" or expired or snap.get("content_version") != item.content_version:
        raise ApiError(410, "content_gone", "this guide is no longer valid")
    narration = next((n for n in snap.get("narrations") or [] if n.get("language") == lang), None)
    if narration is None and lang != h.language:
        raise bad_request("the guide is not told in this language", {"field": "language"})
    if narration is not None:
        text, intro, scope = narration.get("body"), narration.get("intro"), "shared"
        if text is None:
            story = translation.ensure_story(db, item, lang, trip_id=trip.id)
            if story is None:
                raise ApiError(503, "translation_unavailable", "this story is not available in this language")
            text = translation.spoken_text(story, trip_settings(trip, g.user)["detail_mode"])
            h.speech_snapshot_json = {**snap, "narrations": [
                {**n, "body": text} if n is narration else n for n in snap["narrations"]]}
    elif "body" in snap:
        # the story from audio shared by every traveller, plus an optional short private intro
        text, intro, scope = snap["body"] or h.rendered_text, snap.get("intro"), "shared"
    else:  # guides recorded before intros: one text, private when the LLM wrote it
        text, intro = snap.get("text") or h.rendered_text, None
        scope = "private" if snap.get("personalized") else "shared"

    def private_limit_reached():
        count = db.execute(
            select(func.count()).select_from(AudioAsset).where(AudioAsset.trip_session_id == trip.id)
        ).scalar_one()
        return count >= voice.PRIVATE_ASSETS_PER_TRIP

    def asset_for(text, scope):
        return voice.get_or_create_asset(
            db, text=text, language=lang, voice_profile_id=vid, scope=scope,
            content_version=item.content_version, knowledge_item_id=item.id,
            user_id=g.user.id, trip_id=trip.id, valid_until=item.valid_until,
        )

    if scope == "private" and private_limit_reached():
        raise ApiError(429, "tts_limit", "speech generation limit reached for this trip")
    asset, provider = asset_for(text, scope)
    if asset is None:
        raise ApiError(503, "tts_unavailable", "speech synthesis is not available")
    # past the per-trip limit the story still plays, only without its intro
    intro_asset = asset_for(intro, "private")[0] if intro and not private_limit_reached() else None
    if lang == h.language:
        h.audio_asset_id = asset.id
    db.commit()
    if asset.status in ("pending", "invalidated"):
        asset = voice.synthesize_asset(db, asset, provider)
    if intro_asset is not None and intro_asset.status in ("pending", "invalidated"):
        intro_asset = voice.synthesize_asset(db, intro_asset, provider)
    body, status = _asset_body(asset)
    if status == 200:
        if intro_asset is not None and intro_asset.status not in ("ready", "failed"):
            return jsonify({"status": "pending", "asset_id": body["asset_id"], "retry_after_sec": 2}), 202
        # a failed intro is dropped rather than holding the story back
        body["intro"] = _asset_body(intro_asset)[0] if intro_asset is not None and intro_asset.status == "ready" else None
    return jsonify(body), status


@bp.get("/speech-assets/<asset_id>")
@require_auth
def get_asset(asset_id):
    db = get_db()
    asset = db.get(AudioAsset, parse_uuid(asset_id, "asset_id"))
    if asset is None:
        raise not_found("audio not found")
    if asset.scope == "private":
        if asset.owner_user_id != g.user.id:
            raise not_found("audio not found")
    elif not (asset.synthesis_settings_json or {}).get("sample"):
        # shared story audio: only for users who actually received this story (in any of its languages)
        owned = db.execute(
            select(NotificationHistory.id)
            .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
            .where(NotificationHistory.knowledge_item_id == asset.knowledge_item_id, TripSession.user_id == g.user.id)
            .limit(1)
        ).first()
        if owned is None:
            raise not_found("audio not found")
    if not voice.asset_is_servable(db, asset):
        raise ApiError(410, "content_gone", "audio is not available")
    data = voice.read_audio(asset)
    resp = Response(data, mimetype=asset.audio_format)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp
