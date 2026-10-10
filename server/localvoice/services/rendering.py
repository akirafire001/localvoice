"""Turn a KnowledgeItem (+ optional LLM narration) into the guide payload (api-design /context)."""
from .languages import LANGUAGES


def item_texts(item, language, detail_mode="auto"):
    if language not in ("ja", "en"):
        from .translation import localized_story

        story = localized_story(item, language)
        if story and (story.get("short") or story.get("body")):
            title = story.get("title") or item.title_en or item.title
            short = story.get("short") or story.get("body") or ""
            body = story.get("body") or short
            text = body if detail_mode == "detailed" else short
            return title, text, body
        language = "en" if (item.short_en or item.body_en or item.title_en) else "ja"
    if language == "en":
        title = item.title_en or item.title
        short, body = item.short_en, item.body_en
    else:
        title = item.title
        short, body = item.short_ja, item.body_ja
    short = short or body or ""
    body = body or short
    text = body if detail_mode == "detailed" else short
    return title, text, body


def item_speech_text(item, language, text):
    speech = ((item.metadata_json or {}).get("speech") or {}).get(language)
    return speech or text


def sources_payload(item):
    return [
        {"title": s.title, "publisher": s.publisher, "url": s.url, "license": s.license_info}
        for s in item.sources
    ]


def location_payload(cand):
    return {
        "lat": cand.lat,
        "lon": cand.lon,
        "radius_m": cand.item.radius_m,
        "kind": "area" if (cand.item.metadata_json or {}).get("scope") == "area" or cand.item.radius_m >= 800 else "point",
        "distance_m": round(cand.distance_m),
        "relative_direction": cand.relative_direction,
    }


def narrations_payload(history, snap, voice_for):
    narrations = snap.get("narrations")
    if not narrations:  # guides recorded before narration languages: the screen language only
        narrations = [{"language": history.language, "intro": snap.get("intro"), "body": snap.get("body")}]
    out = []
    for n in narrations:
        body, intro = n.get("body"), n.get("intro")
        out.append({
            "language": n["language"],
            # for device TTS when server audio fails; null until the story has been translated
            "text": (f"{intro} {body}" if intro else body) if body else None,
            "intro": intro,
            "voice_profile_id": voice_for(n["language"]),
            "tts_locale": LANGUAGES.get(n["language"], {}).get("tts_locale"),
        })
    return out


def guide_payload(history, item, location, *, voice_for, selection_mode):
    """voice_for(language) → the user's voice_profile_id for that language."""
    voice_profile_id = voice_for(history.language)
    snap = history.speech_snapshot_json or {}
    return {
        "history_id": str(history.id),
        "knowledge_id": str(item.id),
        "title": history.title,
        "text": history.rendered_text,
        "detail_text": history.detail_text,
        "category": item.category,
        "language": history.language,
        "confidence": {"level": item.confidence_level, "fact_type": item.fact_type},
        "sources": sources_payload(item),
        "image": (item.metadata_json or {}).get("image"),
        "speech": {
            "enabled": True,
            "text": snap.get("text"),
            "intro": snap.get("intro"),
            "content_version": snap.get("content_version"),
            "voice_profile_id": voice_profile_id,
            "audio": None,
            # the story is told in each of these, one after another
            "narrations": narrations_payload(history, snap, voice_for),
        },
        "location": location,
        "origin": item.origin,
        # told while the stories here were not ready yet: "tutorial", "nearby" (from a little further away) or
        # "global" (holds anywhere); null for the usual stories of this place
        "waiting": (history.score_components or {}).get("waiting"),
        "selection_mode": selection_mode,
        "shown_at": history.shown_at.isoformat(),
        "rating": history.rating,
    }
