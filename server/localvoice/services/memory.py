"""TripMemorySummary: a short running summary of what was told today, used to connect stories."""
from sqlalchemy import select

from ..models import NotificationHistory

UPDATE_EVERY = 3  # guides


def _history(db, trip):
    return list(
        db.execute(
            select(NotificationHistory)
            .where(NotificationHistory.trip_session_id == trip.id)
            .order_by(NotificationHistory.shown_at)
        ).scalars()
    )


def rule_summary(hist, language):
    if not hist:
        return None
    cats = {}
    for h in hist:
        c = (h.score_components or {}).get("category")
        if c:
            cats[c] = cats.get(c, 0) + 1
    top = ", ".join(f"{k}×{v}" for k, v in sorted(cats.items(), key=lambda x: -x[1]))
    titles = " / ".join(h.title or "" for h in hist[-6:])
    if language == "en":
        return f"Told so far ({len(hist)}): {titles}. Categories: {top}."
    return f"これまでに話した話題（{len(hist)}件）: {titles}。カテゴリ: {top}。"


def update_summary(db, trip, final=False, use_llm=True):
    hist = _history(db, trip)
    summary = None
    try:
        from .llm import get_llm

        llm = get_llm()
        if use_llm and llm is not None and hist and hasattr(llm, "summarize"):
            summary = llm.summarize(trip, hist)
    except Exception:  # noqa: BLE001  summary must never break the guide
        summary = None
    trip.memory_summary = summary or rule_summary(hist, trip.language)


def maybe_update(db, trip):
    n = len(_history(db, trip))
    if n and n % UPDATE_EVERY == 0:
        # keep /context fast: rule summary inline, the worker refreshes it with the LLM
        update_summary(db, trip, use_llm=False)
        state = dict(trip.state_json or {})
        state["summary_dirty"] = True
        trip.state_json = state
