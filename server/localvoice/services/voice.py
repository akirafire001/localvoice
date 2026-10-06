"""Voice service (synthesis filled in M4)."""

# Server-side allow list of voice profiles (voice-design §4). Provider/model/voice stay server-side.
VOICE_PROFILES = {
    "ja-default": {"language": "ja", "display_name": "あかり（落ち着いた語り）"},
    "ja-bright": {"language": "ja", "display_name": "みなと（明るい語り）"},
    "en-default": {"language": "en", "display_name": "Clara (calm narrator)"},
    "en-warm": {"language": "en", "display_name": "Owen (warm narrator)"},
}


def allowed_voice_ids(language):
    return {k for k, v in VOICE_PROFILES.items() if v["language"] == language}


def delete_user_audio_files(db, user_id):
    return 0
