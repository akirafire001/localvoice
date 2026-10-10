"""A story in any narration language: its written version when it has one, otherwise a translation made the first
time someone needs it and kept on the story, so every later traveller reuses it (and its cached audio)."""
import logging

from ..models import ApiUsageLog
from .languages import NATIVE_LANGUAGES

log = logging.getLogger(__name__)


def written_story(item, language):
    """{title, short, body, speech} as written at generation time, or None."""
    speech = ((item.metadata_json or {}).get("speech") or {}).get(language)
    if language == "ja" and (item.body_ja or item.short_ja):
        return {"title": item.title, "short": item.short_ja or item.body_ja, "body": item.body_ja or item.short_ja,
                "speech": speech}
    if language == "en" and (item.body_en or item.short_en):
        return {"title": item.title_en or item.title, "short": item.short_en or item.body_en,
                "body": item.body_en or item.short_en, "speech": speech}
    return None


def cached_translation(item, language):
    t = ((item.metadata_json or {}).get("translations") or {}).get(language)
    if t and t.get("content_version") == item.content_version:
        return t
    return None


def localized_story(item, language):
    """The story in `language` without calling the LLM, or None when it still has to be translated."""
    return written_story(item, language) or cached_translation(item, language)


def spoken_text(story, detail_mode="auto"):
    """What is heard: the storytelling speech, else the screen text."""
    if story.get("speech"):
        return story["speech"]
    return story["body"] if detail_mode == "detailed" else story["short"]


def ensure_story(db, item, language, trip_id=None):
    """The story in `language`, translating it now when needed. None when no translation can be made."""
    story = localized_story(item, language)
    if story is not None:
        return story
    from .llm import LLMError, get_llm, llm_provider

    llm = get_llm()
    source_lang = next((lang for lang in NATIVE_LANGUAGES if written_story(item, lang)), None)
    if llm is None or source_lang is None:
        return None
    source = written_story(item, source_lang)
    try:
        data, meta = llm.translate_story({"source_language": source_lang, **source}, language)
    except LLMError as e:
        log.warning("translation of %s to %s failed: %s", item.id, language, e)
        return None
    if not (data.get("speech") or data.get("body")):
        return None
    story = {k: (data.get(k) or "").strip() for k in ("title", "short", "body", "speech")}
    story["short"] = story["short"] or story["body"]
    story["body"] = story["body"] or story["short"]
    story.update(content_version=item.content_version, source_language=source_lang)
    meta_json = dict(item.metadata_json or {})
    meta_json["translations"] = {**(meta_json.get("translations") or {}), language: story}
    item.metadata_json = meta_json
    db.add(ApiUsageLog(
        trip_session_id=trip_id, provider=llm_provider(llm), operation="translate_story", request_units=1,
        estimated_cost=meta.get("cost_usd") or 0,
        details_json={"model": meta.get("model"), "language": language, "knowledge_item_id": str(item.id),
                      "latency_ms": meta.get("latency_ms"), "prompt_version": meta.get("prompt_version")},
    ))
    return story
