"""Voice service: VoiceProvider, audio asset cache and storage (voice-design §4-7, api-design 音声).

Provider/model/voice stay on the server; clients only pick a voice_profile_id from the allow list.
"""
import base64
import hashlib
import io
import json
import logging
import os
import struct
import wave
from datetime import timedelta

import requests
from flask import current_app
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..models import ApiUsageLog, AudioAsset, KnowledgeItem
from ..util import now

log = logging.getLogger(__name__)

# Server-side allow list of voice profiles. Display names are product names, not the provider's.
VOICE_PROFILES = {
    "ja-default": {"language": "ja", "display_name": "あかり（落ち着いた語り）",
                   "google": {"languageCode": "ja-JP", "name": "ja-JP-Chirp3-HD-Aoede"}, "voice_version": "1"},
    "ja-bright": {"language": "ja", "display_name": "みなと（明るい語り）",
                  "google": {"languageCode": "ja-JP", "name": "ja-JP-Chirp3-HD-Puck"}, "voice_version": "1"},
    "en-default": {"language": "en", "display_name": "Clara (calm narrator)",
                   "google": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Aoede"}, "voice_version": "1"},
    "en-warm": {"language": "en", "display_name": "Owen (warm narrator)",
                "google": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Charon"}, "voice_version": "1"},
    "zh-default": {"language": "zh", "display_name": "小云（沉稳的讲述）",
                   "google": {"languageCode": "cmn-CN", "name": "cmn-CN-Chirp3-HD-Aoede"}, "voice_version": "1"},
    "ko-default": {"language": "ko", "display_name": "하나 (차분한 이야기)",
                   "google": {"languageCode": "ko-KR", "name": "ko-KR-Chirp3-HD-Aoede"}, "voice_version": "1"},
    "es-default": {"language": "es", "display_name": "Lucía (narradora serena)",
                   "google": {"languageCode": "es-ES", "name": "es-ES-Chirp3-HD-Aoede"}, "voice_version": "1"},
    "fr-default": {"language": "fr", "display_name": "Claire (narratrice posée)",
                   "google": {"languageCode": "fr-FR", "name": "fr-FR-Chirp3-HD-Aoede"}, "voice_version": "1"},
}
SAMPLE_TEXT = {
    "ja": "宮島の大鳥居は、海の底に埋められているわけではなく、自分の重さで立っています。",
    "en": "The great torii of Miyajima is not buried in the seabed. It stands by its own weight.",
    "zh": "宫岛的大鸟居并没有埋在海底，而是靠自身的重量矗立在那里。",
    "ko": "미야지마의 큰 도리이는 바닷속에 묻혀 있는 것이 아니라, 자신의 무게로 서 있습니다.",
    "es": "El gran torii de Miyajima no está enterrado en el fondo del mar: se sostiene por su propio peso.",
    "fr": "Le grand torii de Miyajima n'est pas enfoui dans le fond marin : il tient debout par son propre poids.",
}
MAX_ATTEMPTS = 3
PRIVATE_ASSETS_PER_TRIP = 300


def allowed_voice_ids(language):
    return {k for k, v in VOICE_PROFILES.items() if v["language"] == language}


def _cfg():
    return current_app.config["LV"]


class ProviderError(Exception):
    pass


class SilentProvider:
    """Development/test provider: returns a short silent WAV sized to the text."""

    name, model, model_version, audio_format, ext = "silent", "silent", "1", "audio/wav", "wav"

    def synthesize(self, text, profile):
        duration_ms = min(60000, 300 + 120 * len(text))
        rate = 8000
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack("<h", 0) * int(rate * duration_ms / 1000))
        return buf.getvalue(), duration_ms, 0.0, []


class GoogleTTSProvider:
    """Google Cloud Text-to-Speech (Chirp 3 HD). Price is a configurable estimate per million characters."""

    name, model, model_version, audio_format, ext = "google", "chirp3-hd", "1", "audio/mpeg", "mp3"
    URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
    USD_PER_MCHAR = 30.0

    def synthesize(self, text, profile):
        key = _cfg().GOOGLE_TTS_API_KEY
        if not key:
            raise ProviderError("google tts not configured")
        body = {"input": {"text": text}, "voice": profile["google"], "audioConfig": {"audioEncoding": "MP3"}}
        try:
            r = requests.post(self.URL, params={"key": key}, json=body, timeout=15)
        except requests.RequestException as e:
            raise ProviderError(str(e))
        if r.status_code != 200:
            raise ProviderError(f"google tts {r.status_code}")
        audio = base64.b64decode(r.json()["audioContent"])
        duration_ms = int(len(audio) / (32000 / 8) * 1000)  # 32kbps estimate, refined on the client
        return audio, duration_ms, len(text) * self.USD_PER_MCHAR / 1_000_000, []


def get_provider():
    ext = current_app.extensions
    if "lv_tts" in ext:
        return ext["lv_tts"]
    p = _cfg().TTS_PROVIDER
    if p == "google":
        return GoogleTTSProvider()
    if p == "silent":
        return SilentProvider()
    return None


# ---------------------------------------------------------------- cache keys / storage


def cache_key(*, text, content_version, language, provider, voice_profile_id, scope, user_id=None, trip_id=None):
    profile = VOICE_PROFILES[voice_profile_id]
    parts = {
        "text_hash": hashlib.sha256(text.encode()).hexdigest(),
        "content_version": content_version,
        "pronunciation": _cfg().PRONUNCIATION_VERSION,
        "language": language,
        "provider": provider.name,
        "model": f"{provider.model}:{provider.model_version}",
        "voice": voice_profile_id,
        "voice_version": profile["voice_version"],
        "settings": {"rate": 1.0},
        "format": provider.audio_format,
        "scope": scope,
        "user": str(user_id) if scope == "private" else None,
        "trip": str(trip_id) if scope == "private" else None,
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def _store_path(storage_key):
    return os.path.join(_cfg().AUDIO_STORE_DIR, storage_key)


def read_audio(asset):
    with open(_store_path(asset.storage_key), "rb") as f:
        return f.read()


def _delete_file(asset):
    if asset.storage_key:
        try:
            os.remove(_store_path(asset.storage_key))
        except FileNotFoundError:
            pass


def get_or_create_asset(db, *, text, language, voice_profile_id, scope, content_version, knowledge_item_id=None,
                        user_id=None, trip_id=None, valid_until=None, sample=False):
    provider = get_provider()
    if provider is None:
        return None, None
    key = cache_key(text=text, content_version=content_version, language=language, provider=provider,
                    voice_profile_id=voice_profile_id, scope=scope, user_id=user_id, trip_id=trip_id)
    retention = now() + timedelta(days=_cfg().PRIVATE_AUDIO_RETENTION_DAYS) if scope == "private" else None
    db.execute(
        insert(AudioAsset).values(
            id=__import__("uuid").uuid4(), cache_key=key, scope=scope, knowledge_item_id=knowledge_item_id,
            owner_user_id=user_id if scope == "private" else None, trip_session_id=trip_id if scope == "private" else None,
            content_version=content_version, speech_text_hash=hashlib.sha256(text.encode()).hexdigest(),
            pronunciation_version=_cfg().PRONUNCIATION_VERSION, language=language, provider=provider.name,
            model=provider.model, model_version=provider.model_version, voice_profile_id=voice_profile_id,
            voice_version=VOICE_PROFILES[voice_profile_id]["voice_version"],
            synthesis_settings_json={"rate": 1.0, "sample": sample, "text": text},
            status="pending", audio_format=provider.audio_format, valid_until=valid_until,
            retention_until=retention, attribution_json=[], attempts=0, created_at=now(), updated_at=now(),
        ).on_conflict_do_nothing(index_elements=["cache_key"])
    )
    asset = db.execute(select(AudioAsset).where(AudioAsset.cache_key == key)).scalar_one()
    return asset, provider


def synthesize_asset(db, asset, provider=None):
    """Generate audio for a pending asset. Concurrent callers for the same key collapse to one."""
    provider = provider or get_provider()
    locked = db.execute(
        select(AudioAsset).where(AudioAsset.id == asset.id).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if locked is None or locked.status not in ("pending", "invalidated"):
        return locked or asset
    asset = locked
    text = (asset.synthesis_settings_json or {}).get("text") or ""
    profile = VOICE_PROFILES[asset.voice_profile_id]
    asset.attempts += 1
    try:
        audio, duration_ms, cost, attribution = provider.synthesize(text, profile)
    except ProviderError as e:
        asset.error = str(e)[:300]
        asset.status = "failed" if asset.attempts >= MAX_ATTEMPTS else "pending"
        db.commit()
        return asset
    storage_key = f"{asset.scope}/{asset.cache_key}.{provider.ext}"
    path = _store_path(storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(audio)
    asset.storage_key = storage_key
    asset.duration_ms = duration_ms
    asset.attribution_json = attribution
    asset.status = "ready"
    asset.error = None
    db.add(ApiUsageLog(
        trip_session_id=asset.trip_session_id, provider=f"tts:{provider.name}", operation="synthesize",
        request_units=len(text), estimated_cost=cost,
        details_json={"voice": asset.voice_profile_id, "duration_ms": duration_ms, "scope": asset.scope},
    ))
    db.commit()
    return asset


def asset_is_servable(db, asset):
    if asset.status != "ready":
        return False
    if asset.valid_until is not None and asset.valid_until <= now():
        return False
    if asset.retention_until is not None and asset.retention_until <= now():
        return False
    if asset.knowledge_item_id is not None:
        item = db.get(KnowledgeItem, asset.knowledge_item_id)
        if item is None or item.review_status == "suspended":
            return False
        if item.valid_until is not None and item.valid_until <= now():
            return False
        if asset.content_version != item.content_version and not (asset.synthesis_settings_json or {}).get("sample"):
            return False
    return True


def process_pending_audio(db, limit=5):
    provider = get_provider()
    if provider is None:
        return 0
    assets = db.execute(
        select(AudioAsset).where(AudioAsset.status == "pending", AudioAsset.attempts < MAX_ATTEMPTS)
        .order_by(AudioAsset.created_at).limit(limit)
    ).scalars().all()
    for a in assets:
        synthesize_asset(db, a, provider)
    return len(assets)


def cleanup_expired_audio(db):
    t = now()
    for a in db.execute(
        select(AudioAsset).where(AudioAsset.retention_until.is_not(None), AudioAsset.retention_until <= t)
    ).scalars():
        _delete_file(a)
        db.delete(a)


def delete_user_audio_files(db, user_id):
    n = 0
    for a in db.execute(select(AudioAsset).where(AudioAsset.owner_user_id == user_id)).scalars():
        _delete_file(a)
        db.delete(a)
        n += 1
    db.flush()
    return n


def sample_asset(db, voice_profile_id):
    profile = VOICE_PROFILES[voice_profile_id]
    return get_or_create_asset(
        db, text=SAMPLE_TEXT[profile["language"]], language=profile["language"], voice_profile_id=voice_profile_id,
        scope="shared", content_version="sample-1", sample=True,
    )
