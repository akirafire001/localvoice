"""Natural-language temporary instructions and temporary states (product-spec §10, feasibility §10–11).

Text → structured IntentOverride / TemporaryState. Claude parses when available; otherwise a
keyword parser. Ambiguous results are stored with a short TTL and flagged for confirmation, and
every active item is listed so the user can remove it with one tap.
"""
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select

from ..models import IntentOverride, TemporaryState
from ..util import now
from .prefs import CATEGORIES

INTENT_TYPES = {"focus_category", "suppress_category"}
# state → default TTL minutes and its effect on guiding (applied in engine.state_effects)
STATE_TYPES = {
    "quiet": 30,       # stop automatic guides
    "hungry": 60,      # food first
    "toilet": 20,      # practical first
    "tired": 60,       # fewer guides
    "bored": 60,       # more guides
    "no_time": 60,     # short texts
}
MIN_TTL, MAX_TTL = 5, 240
AMBIGUOUS_TTL = 15

CATEGORY_WORDS = {
    "history": ["歴史", "史跡", "昔", "history", "historic"],
    "architecture": ["建築", "建物", "architecture", "building"],
    "nature": ["自然", "山", "川", "景色", "nature", "scenery"],
    "food": ["食", "グルメ", "名物", "food", "eat"],
    "culture": ["文化", "祭", "芸術", "culture", "art"],
    "everyday_life": ["暮らし", "生活", "地元", "everyday", "local life"],
    "industry": ["産業", "工場", "industry", "factory"],
    "seasonal": ["季節", "旬", "seasonal", "season"],
    "practical": ["実用", "便利", "practical", "useful"],
}
MORE_WORDS = ["多め", "多く", "もっと", "教えて", "中心", "優先", "more", "focus", "tell me"]
LESS_WORDS = ["いらない", "不要", "少なめ", "やめて", "なしで", "控えて", "no more", "less", "skip", "stop"]
STATE_WORDS = {
    "quiet": ["静かに", "黙って", "しゃべらないで", "話さないで", "be quiet", "quiet", "silence", "mute"],
    "hungry": ["お腹が空", "おなかがす", "お腹すい", "腹減", "hungry"],
    "toilet": ["トイレ", "お手洗い", "toilet", "restroom", "bathroom"],
    "tired": ["疲れ", "tired"],
    "bored": ["暇", "ひま", "退屈", "bored"],
    "no_time": ["時間がない", "急いで", "急ぎ", "no time", "in a hurry", "hurry"],
}
RESUME_WORDS = ["再開", "話して", "しゃべって", "戻して", "resume", "talk again", "unmute"]

LABELS = {
    "focus_category": ("{cat}を多めに", "More {cat}"),
    "suppress_category": ("{cat}は控えめに", "Less {cat}"),
    "quiet": ("静かに", "Quiet"),
    "hungry": ("食事を探し中", "Looking for food"),
    "toilet": ("トイレを探し中", "Looking for a restroom"),
    "tired": ("休憩モード", "Taking it easy"),
    "bored": ("話題多め", "More stories"),
    "no_time": ("手短に", "Keep it short"),
}
CATEGORY_NAMES = {
    "history": ("歴史", "history"), "architecture": ("建築", "architecture"), "nature": ("自然", "nature"),
    "food": ("食", "food"), "culture": ("文化", "culture"), "everyday_life": ("暮らし", "everyday life"),
    "industry": ("産業", "industry"), "seasonal": ("季節", "seasonal topics"), "practical": ("実用情報", "practical info"),
}


@dataclass
class ParsedCommand:
    intents: list = field(default_factory=list)   # dicts: type, target, ttl_min
    states: list = field(default_factory=list)    # dicts: type, ttl_min
    resume: bool = False
    confidence: float = 1.0
    end_condition: str | None = None              # free text like "until I get off the train"
    parser: str = "rule"


def label_for(kind, target, lang):
    ja, en = LABELS[kind]
    cat = CATEGORY_NAMES.get(target, (target or "", target or ""))
    return (en if lang == "en" else ja).format(cat=cat[1] if lang == "en" else cat[0])


def _minutes(text):
    m = re.search(r"(\d+)\s*(分|min|minutes?)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(時間|h|hours?)", text)
    if m:
        return int(m.group(1)) * 60
    if any(w in text for w in ("今日", "today")):
        return MAX_TTL
    return None


def rule_parse(text):
    t = text.lower()
    out = ParsedCommand()
    minutes = _minutes(t)
    if any(w in t for w in RESUME_WORDS):
        out.resume = True
    for st, words in STATE_WORDS.items():
        if any(w in t for w in words):
            out.states.append({"type": st, "ttl_min": minutes or STATE_TYPES[st]})
    cats = [c for c, words in CATEGORY_WORDS.items() if any(w in t for w in words)]
    # "food" is implied by hungry; don't double-count unless explicitly asked for more/less
    less = any(w in t for w in LESS_WORDS)
    more = any(w in t for w in MORE_WORDS)
    for c in cats:
        if less:
            out.intents.append({"type": "suppress_category", "target": c, "ttl_min": minutes or 60})
        elif more or not out.states:
            out.intents.append({"type": "focus_category", "target": c, "ttl_min": minutes or 60})
    if any(w in t for w in ("降りるまで", "着くまで", "until")):
        out.end_condition = text.strip()[:200]
    if not out.intents and not out.states and not out.resume:
        out.confidence = 0.0
    elif not more and not less and out.intents:
        out.confidence = 0.5  # a bare category name: guess "more", keep it short
    if out.states and "quiet" in [s["type"] for s in out.states] and out.resume:
        out.resume = False  # e.g. "静かにして" contains "して"; quiet wins
    return out


def validate_llm(data):
    """Keep only allowed types/categories and clamp TTLs; never trust free-form fields."""
    out = ParsedCommand(parser="llm")
    for it in (data.get("intents") or [])[:5]:
        if it.get("type") in INTENT_TYPES and it.get("target") in CATEGORIES:
            out.intents.append({"type": it["type"], "target": it["target"], "ttl_min": _clamp(it.get("ttl_min"), 60)})
    for st in (data.get("states") or [])[:3]:
        if st.get("type") in STATE_TYPES:
            out.states.append({"type": st["type"], "ttl_min": _clamp(st.get("ttl_min"), STATE_TYPES[st["type"]])})
    out.resume = bool(data.get("resume"))
    try:
        out.confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        out.confidence = 0.0
    ec = data.get("end_condition")
    out.end_condition = ec[:200] if isinstance(ec, str) and ec.strip() else None
    return out


def _clamp(v, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(MIN_TTL, min(MAX_TTL, v))


def apply(db, trip, parsed, text, source="command"):
    """Persist the parsed command. Returns (intents, states, needs_confirmation)."""
    t = now()
    ambiguous = parsed.confidence < 0.6
    lang = trip.language
    if parsed.resume:
        for s in active_states(db, trip.id, t):
            if s.state_type == "quiet":
                s.ended_at = t
    new_intents, new_states = [], []
    for it in parsed.intents:
        # a newer instruction for the same category replaces the old one
        for old in active_overrides(db, trip.id, t):
            if old.target == it["target"]:
                old.ended_at = t
        ttl = AMBIGUOUS_TTL if ambiguous else it["ttl_min"]
        row = IntentOverride(
            trip_session_id=trip.id, type=it["type"], target=it["target"], strength=1.0,
            label=label_for(it["type"], it["target"], lang), expires_at=t + timedelta(minutes=ttl),
            end_condition_json={"text": parsed.end_condition, "source_text": text[:500], "parser": parsed.parser,
                                "confidence": parsed.confidence},
        )
        db.add(row)
        new_intents.append(row)
    for st in parsed.states:
        for old in active_states(db, trip.id, t):
            if old.state_type == st["type"]:
                old.ended_at = t  # updated by the new utterance
        ttl = AMBIGUOUS_TTL if ambiguous else st["ttl_min"]
        row = TemporaryState(
            trip_session_id=trip.id, state_type=st["type"], source=source,
            payload_json={"source_text": text[:500], "parser": parsed.parser},
            expires_at=t + timedelta(minutes=ttl),
        )
        db.add(row)
        new_states.append(row)
    db.flush()
    return new_intents, new_states, ambiguous and bool(new_intents or new_states)


def active_overrides(db, trip_id, t):
    return list(db.execute(
        select(IntentOverride).where(IntentOverride.trip_session_id == trip_id, IntentOverride.ended_at.is_(None),
                                     IntentOverride.expires_at > t).order_by(IntentOverride.created_at)
    ).scalars())


def active_states(db, trip_id, t):
    return list(db.execute(
        select(TemporaryState).where(TemporaryState.trip_session_id == trip_id, TemporaryState.ended_at.is_(None),
                                     TemporaryState.expires_at > t).order_by(TemporaryState.created_at)
    ).scalars())


def override_payload(o):
    return {"id": str(o.id), "kind": "intent", "type": o.type, "target": o.target, "label": o.label,
            "expires_at": o.expires_at.isoformat(), "end_condition": (o.end_condition_json or {}).get("text")}


def state_payload(s, lang):
    return {"id": str(s.id), "kind": "state", "type": s.state_type, "target": None,
            "label": label_for(s.state_type, None, lang), "expires_at": s.expires_at.isoformat(), "end_condition": None}


def state_effects(states):
    """How temporary states change guiding: (extra topics, cooldown factor, detail override)."""
    topics, factor, detail = set(), 1.0, None
    for s in states:
        if s.state_type == "hungry":
            topics.add("food")
        elif s.state_type == "toilet":
            topics.add("practical")
        elif s.state_type == "tired":
            factor = max(factor, 2.0)
        elif s.state_type == "bored":
            factor = min(factor, 0.5)
        elif s.state_type == "no_time":
            detail = "short"
    return topics, factor, detail
