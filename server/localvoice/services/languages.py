"""Languages the guide can speak, and the ones the app's own screens are written in.

Adding a narration language takes one entry here and at least one voice in voice.VOICE_PROFILES. Stories are
written in Japanese and English; any other language (or a story missing its English version) is translated from
them the first time it is needed and the translation is kept on the story (see translation.py).
"""

# code: native name, Japanese and English names (for the settings screen), device TTS locale, character-dense
# (intro length limits count characters rather than words).
LANGUAGES = {
    "ja": {"name": "日本語", "name_ja": "日本語", "name_en": "Japanese", "tts_locale": "ja-JP", "dense": True},
    "en": {"name": "English", "name_ja": "英語", "name_en": "English", "tts_locale": "en-US", "dense": False},
    "zh": {"name": "中文", "name_ja": "中国語", "name_en": "Chinese", "tts_locale": "zh-CN", "dense": True},
    "ko": {"name": "한국어", "name_ja": "韓国語", "name_en": "Korean", "tts_locale": "ko-KR", "dense": True},
    "es": {"name": "Español", "name_ja": "スペイン語", "name_en": "Spanish", "tts_locale": "es-ES", "dense": False},
    "fr": {"name": "Français", "name_ja": "フランス語", "name_en": "French", "tts_locale": "fr-FR", "dense": False},
}
# The app's screens are translated into these; the UI language stays a single choice among them.
UI_LANGUAGES = ("ja", "en", "zh", "ko", "es", "fr")
# Languages stories are written in when they are generated (KnowledgeItem *_ja / *_en columns).
NATIVE_LANGUAGES = ("ja", "en")
# How many languages one story may be told in, one after another.
MAX_NARRATION_LANGUAGES = 4


def is_dense(language):
    return LANGUAGES.get(language, {}).get("dense", False)


def from_device_language(tag):
    """OS language tag → (app language, narration language). Anything this app does not speak becomes English."""
    primary = tag.strip().lower().replace("_", "-").split("-")[0]
    ui = primary if primary in UI_LANGUAGES else "en"
    narration = primary if primary in LANGUAGES else "en"
    return ui, narration


def apply_device_language(user, data):
    """Initial languages for a new account. Ignored when the client sent no OS language."""
    tag = data.get("device_language") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not tag.strip():
        return
    ui, narration = from_device_language(tag)
    user.locale = ui
    user.voice_settings_json = {**(user.voice_settings_json or {}), "narration_languages": [narration]}


def default_narration_languages(user):
    return [user.locale if user.locale in LANGUAGES else "en"]


def narration_languages(user):
    """The user's narration languages in the order they are spoken (the first is the main one)."""
    stored = (user.voice_settings_json or {}).get("narration_languages")
    langs = [lang for lang in (stored or []) if lang in LANGUAGES]
    return langs or default_narration_languages(user)


def validate_narration_languages(value):
    """Returns the cleaned list, or an error message."""
    if not isinstance(value, list) or not value:
        return None, "narration_languages must be a non-empty list"
    if len(value) > MAX_NARRATION_LANGUAGES:
        return None, f"at most {MAX_NARRATION_LANGUAGES} narration languages"
    if len(set(value)) != len(value):
        return None, "narration_languages must not repeat a language"
    unknown = [v for v in value if v not in LANGUAGES]
    if unknown:
        return None, f"unsupported narration language: {unknown[0]!r}"
    return list(value), None


def catalog():
    return {
        "ui": [{"code": c, **_public(c)} for c in UI_LANGUAGES],
        "narration": [{"code": c, **_public(c)} for c in LANGUAGES],
        "max_narration_languages": MAX_NARRATION_LANGUAGES,
    }


def _public(code):
    entry = LANGUAGES[code]
    return {k: entry[k] for k in ("name", "name_ja", "name_en", "tts_locale")}
