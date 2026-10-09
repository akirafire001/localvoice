"""Turn a KnowledgeItem (+ optional LLM narration) into the guide payload (api-design /context)."""


def item_texts(item, language, detail_mode="auto"):
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


def guide_payload(history, item, location, *, voice_profile_id, selection_mode):
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
        },
        "location": location,
        "origin": item.origin,
        "selection_mode": selection_mode,
        "shown_at": history.shown_at.isoformat(),
        "rating": history.rating,
    }
