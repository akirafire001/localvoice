"""Rewrite stories already in the database into spoken versions with storytelling techniques.

`flask --app localvoice rewrite-stories` gives each story without a storytelling-based speech a spoken version
(metadata_json["speech"]) and records how it was told (metadata_json["storytelling"]). The screen texts, claims
and sources stay as they are.
"""
from collections import Counter

from sqlalchemy import select

from ..models import ApiUsageLog, KnowledgeItem
from ..util import now
from .knowledge_gen import speech_check, speech_metadata
from .llm import VISUAL_PATTERNS, LLMError, llm_provider


def story_payload(item):
    meta = item.metadata_json or {}
    quality = meta.get("story_quality") or {}
    return {
        "title": item.title, "title_en": item.title_en, "category": item.category, "fact_type": item.fact_type,
        "short_ja": item.short_ja, "body_ja": item.body_ja, "short_en": item.short_en, "body_en": item.body_en,
        "why_here": quality.get("why_here"), "interest_hook": quality.get("interest_hook"),
        "present_connection": quality.get("present_connection"),
        "claims": [{"text_ja": c.claim_text_ja, "text_en": c.claim_text_en} for c in item.claims],
    }


def _used_nearby(items):
    """Most used openings and structures among the stories of one cell, so rewrites spread them."""
    openings, structures = Counter(), Counter()
    for it in items:
        st = (it.metadata_json or {}).get("storytelling") or {}
        if st.get("opening"):
            openings[st["opening"]] += 1
        if st.get("structure"):
            structures[st["structure"]] += 1
    return {"openings": dict(openings.most_common(6)), "structures": dict(structures.most_common(6))}


def targets(db, cell=None, force=False):
    q = select(KnowledgeItem).where(KnowledgeItem.review_status != "suspended")
    if cell:
        q = q.where(KnowledgeItem.area_cell == cell)
    items = db.execute(q.order_by(KnowledgeItem.area_cell, KnowledgeItem.created_at)).scalars().all()
    return [it for it in items if force or not (it.metadata_json or {}).get("storytelling")]


def rewrite_item(db, llm, item, neighbours):
    """Rewrite one story. Returns (stored, hold_reason)."""
    data, meta = llm.rewrite_story(story_payload(item), _used_nearby(neighbours))
    db.add(ApiUsageLog(
        trip_session_id=None, provider=llm_provider(llm), operation="rewrite_story", request_units=1,
        estimated_cost=meta.get("cost_usd") or 0,
        details_json={**{k: v for k, v in meta.items() if k != "cost_usd"}, "knowledge_item_id": str(item.id)},
    ))
    speech = f"{data.get('speech_ja') or ''} {data.get('speech_en') or ''}"
    if any(p.lower() in speech.lower() for p in VISUAL_PATTERNS):
        return False, "visual_expression"  # keep the old version rather than store a broken one
    ok, hold = speech_check(data)
    md = dict(item.metadata_json or {})
    if hold == "no_speech":
        return False, hold
    md.update(speech_metadata(data))
    quality = dict(md.get("story_quality") or {})
    if not ok:
        # A story with no punchline or a hedge in its speech is kept out of automatic guidance until reviewed.
        quality.update(auto_eligible=False, hold_reason=hold)
    quality.update(rewritten_at=now().isoformat(), rewrite_version=meta.get("prompt_version"))
    md["story_quality"] = quality
    item.metadata_json = md  # a new dict, so SQLAlchemy writes the JSONB column
    return True, hold


def rewrite_all(db, llm, cell=None, limit=None, force=False, dry_run=False, echo=print):
    todo = targets(db, cell, force)
    if limit:
        todo = todo[:limit]
    echo(f"{len(todo)} stories to rewrite")
    stats = Counter()
    by_cell = {}
    for item in todo:
        if item.area_cell not in by_cell:
            by_cell[item.area_cell] = db.execute(
                select(KnowledgeItem).where(KnowledgeItem.area_cell == item.area_cell)
            ).scalars().all() if item.area_cell else []
        try:
            stored, hold = rewrite_item(db, llm, item, by_cell[item.area_cell])
        except LLMError as e:
            stats["error"] += 1
            echo(f"  ! {item.title}: {e}")
            db.rollback()
            continue
        stats["stored" if stored else "skipped"] += 1
        if hold:
            stats[hold] += 1
        speech = ((item.metadata_json or {}).get("speech") or {}).get("ja", "")
        echo(f"  {'+' if stored else '-'} {item.title}{f' [{hold}]' if hold else ''}\n    {speech}")
        if dry_run:
            db.rollback()
        else:
            db.commit()
    echo(", ".join(f"{k}: {v}" for k, v in stats.items()) or "nothing done")
    return stats
