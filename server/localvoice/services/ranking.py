"""Rule-based candidate retrieval and scoring (mvp-technical-design §5, §7, §10). No LLM here."""
import random
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select, text

from ..models import KnowledgeItem, NotificationHistory, TopicBoost, TripSession, UserInterest
from ..util import now
from . import geo
from .prefs import MAX_SAME_CATEGORY_IN_ROW, SERENDIPITY_LEVELS

WEIGHTS = {
    "location": 0.25,
    "interest": 0.20,
    "topic": 0.15,
    "interestingness": 0.15,
    "timeliness": 0.10,
    "novelty": 0.10,
    "direction": 0.05,
}


@dataclass
class Candidate:
    item: KnowledgeItem
    distance_m: float
    lat: float
    lon: float
    in_area: bool
    bearing: float | None = None
    relative_direction: str | None = None
    components: dict = field(default_factory=dict)
    penalties: dict = field(default_factory=dict)
    score: float = 0.0
    heard_before: bool = False  # told to this user on an earlier trip

    def summary(self):
        return {
            "knowledge_id": str(self.item.id),
            "title": self.item.title,
            "category": self.item.category,
            "origin": self.item.origin,
            "distance_m": round(self.distance_m),
            "relative_direction": self.relative_direction,
            "in_area": self.in_area,
            "heard_before": self.heard_before,
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "penalties": {k: round(v, 4) for k, v in self.penalties.items()},
        }


# Country-wide stories (manners common to the whole country) sit just below the stories of this very place
COUNTRY_WIDE_PENALTY = 0.05
COUNTRY_WIDE_LIMIT = 50


def fetch_candidates(db, lat, lon, tclass, course_deg=None, course_confident=False, language="ja", t=None,
                     home_country=None):
    """Stories around the position, plus the country-wide ones of the country it is in. Country-wide stories are
    for travellers from elsewhere: they are left out when the country is `home_country` (ISO code)."""
    t = t or now()
    search_r = geo.SEARCH_RADIUS_M.get(tclass, 700)
    params = {"lat": lat, "lon": lon, "r": search_r, "t": t}
    ahead_clause = ""
    if course_confident and course_deg is not None and geo.LOOKAHEAD_M.get(tclass):
        alat, alon = geo.destination(lat, lon, course_deg, geo.LOOKAHEAD_M[tclass])
        params.update({"alat": alat, "alon": alon})
        ahead_clause = (
            " OR ST_DWithin(position, ST_SetSRID(ST_MakePoint(:alon, :alat), 4326)::geography, :r)"
        )
    lang_clause = " AND (body_en IS NOT NULL OR short_en IS NOT NULL)" if language == "en" else ""
    rows = db.execute(
        text(
            f"""
            SELECT id,
                   ST_Distance(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d,
                   ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, radius_m) AS in_area,
                   ST_Y(position::geometry) AS ilat, ST_X(position::geometry) AS ilon
            FROM knowledge_items
            WHERE position IS NOT NULL
              AND review_status <> 'suspended'
              AND (valid_from IS NULL OR valid_from <= :t)
              AND (valid_until IS NULL OR valid_until > :t)
              AND COALESCE((metadata_json->'story_quality'->>'auto_eligible')::boolean, false)
              AND COALESCE(metadata_json->>'scope', '') <> 'country'
              {lang_clause}
              AND (ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)
                   OR ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, radius_m)
                   {ahead_clause})
            ORDER BY d
            LIMIT 200
            """
        ),
        params,
    ).all()
    if not rows:
        return [], search_r
    items = {
        i.id: i for i in db.execute(select(KnowledgeItem).where(KnowledgeItem.id.in_([r.id for r in rows]))).scalars()
    }
    out = []
    country = _country_here(items.values())
    if country and country != (home_country or "").lower():
        for item in _country_wide(db, country, lang_clause, t):
            # holds anywhere in the country: an area story covering the position, with no direction
            out.append(Candidate(item=item, distance_m=float(search_r), lat=lat, lon=lon, in_area=True))
    for r in rows:
        c = Candidate(item=items[r.id], distance_m=float(r.d), lat=r.ilat, lon=r.ilon, in_area=bool(r.in_area))
        if r.d > 1:
            c.bearing = geo.bearing_deg(lat, lon, r.ilat, r.ilon)
            if course_confident and course_deg is not None:
                c.relative_direction = geo.relative_direction(course_deg, c.bearing)
        out.append(c)
    return out, search_r


def _country_here(items):
    """Country of the position: the one most nearby stories were generated in. Stories record it since
    2026-10-09; older ones and the curated ones are all in Japan."""
    counts = {}
    for i in items:
        c = (i.metadata_json or {}).get("country") or "jp"
        counts[c] = counts.get(c, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _country_wide(db, country, lang_clause, t):
    ids = db.execute(
        text(
            f"""
            SELECT id FROM knowledge_items
            WHERE metadata_json->>'scope' = 'country' AND metadata_json->>'country' = :c
              AND review_status <> 'suspended'
              AND (valid_from IS NULL OR valid_from <= :t)
              AND (valid_until IS NULL OR valid_until > :t)
              AND COALESCE((metadata_json->'story_quality'->>'auto_eligible')::boolean, false)
              {lang_clause}
            ORDER BY created_at, id
            LIMIT {COUNTRY_WIDE_LIMIT}
            """
        ),
        {"c": country, "t": t},
    ).scalars().all()
    if not ids:
        return []
    return list(db.execute(select(KnowledgeItem).where(KnowledgeItem.id.in_(ids))).scalars())


def load_interests(db, user_id):
    out = {}
    for ui in db.execute(select(UserInterest).where(UserInterest.user_id == user_id)).scalars():
        explicit = float(ui.explicit_score) if ui.explicit_score is not None else 0.5
        learned = float(ui.learned_score or 0)
        out[ui.category] = max(0.0, min(1.0, explicit + learned))
    return out


def active_boosts(db, trip_id, t=None):
    """topic_key -> current strength after time decay (negative = suppressed)."""
    t = t or now()
    out = {}
    for b in db.execute(
        select(TopicBoost).where(
            TopicBoost.trip_session_id == trip_id, TopicBoost.ended_at.is_(None), TopicBoost.expires_at > t
        )
    ).scalars():
        hours = (t - b.created_at).total_seconds() / 3600
        strength = float(b.strength) * max(0.0, 1 - float(b.decay_rate) * hours)
        out[b.topic_key] = out.get(b.topic_key, 0.0) + strength
    return out


def todays_history(db, trip_id, t=None):
    t = t or now()
    return list(
        db.execute(
            select(NotificationHistory)
            .where(NotificationHistory.trip_session_id == trip_id, NotificationHistory.shown_at >= t - timedelta(hours=24))
            .order_by(NotificationHistory.shown_at)
        ).scalars()
    )


def heard_before_ids(db, user_id, trip_id, item_ids):
    """Ids among item_ids that this user was already told on an earlier trip (any device, any day)."""
    if not item_ids:
        return set()
    return set(
        db.execute(
            select(NotificationHistory.knowledge_item_id)
            .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
            .where(
                TripSession.user_id == user_id,
                TripSession.id != trip_id,
                NotificationHistory.knowledge_item_id.in_(list(item_ids)),
            )
            .distinct()
        ).scalars()
    )


def _timeliness(item, t):
    meta = item.metadata_json or {}
    months = meta.get("season_months")
    if months and t.month in months:
        return 1.0
    if item.valid_until is not None and item.valid_until - t < timedelta(days=14):
        return 0.9
    if item.category == "seasonal":
        return 0.6
    return 0.3


def score_candidates(
    candidates,
    *,
    search_r,
    interests,
    session_topics,
    boosts,
    history,
    serendipity="normal",
    seed=None,
    excluded_ids=(),
    heard_ids=(),
    t=None,
):
    """Score in place, drop excluded, return sorted list (best first).

    Stories in heard_ids (told on an earlier trip) keep their score but sort after every unheard one,
    so a new trip on the same route does not open with the stories the user just heard."""
    t = t or now()
    shown_ids = {h.knowledge_item_id for h in history} | set(excluded_ids)
    shown_keys = set()
    recent_categories = []
    for h in history:
        recent_categories.append(h.score_components.get("category") if h.score_components else None)
    last_story_type = (history[-1].score_components or {}).get("story_type") if history else None
    rng = random.Random(seed)
    # Serendipity: occasionally ignore the interest profile so out-of-interest stories surface.
    serendipitous = rng.random() < SERENDIPITY_LEVELS.get(serendipity, 0.2)
    tail = [c for c in recent_categories[-MAX_SAME_CATEGORY_IN_ROW:]]
    out = []
    for c in candidates:
        item = c.item
        if item.id in shown_ids or item.canonical_key in shown_keys:
            continue
        dup_of = (item.metadata_json or {}).get("duplicate_group")
        if dup_of and any(
            (h.score_components or {}).get("duplicate_group") == dup_of for h in history
        ):
            continue
        cat = item.category
        if len(tail) >= MAX_SAME_CATEGORY_IN_ROW and all(x == cat for x in tail):
            continue
        comp = {}
        if c.in_area and c.distance_m > search_r:
            comp["location"] = 0.6  # regional story that covers the current position
        else:
            comp["location"] = max(0.0, 1 - c.distance_m / max(search_r, 1))
            if c.in_area:
                comp["location"] = max(comp["location"], 0.6)
        comp["interest"] = 0.5 if serendipitous else interests.get(cat, 0.5)
        topic = 0.0
        if cat in session_topics:
            topic += 0.6
        topic += boosts.get(cat, 0.0) + boosts.get(f"item:{item.id}", 0.0)
        for rel in (item.metadata_json or {}).get("topics", []):
            topic += 0.5 * boosts.get(rel, 0.0)
        comp["topic"] = max(-1.0, min(1.0, topic))
        comp["interestingness"] = float(item.interestingness or 0.5)
        comp["timeliness"] = _timeliness(item, t)
        comp["novelty"] = float(item.novelty or 0.5)
        if c.relative_direction is None:
            comp["direction"] = 0.5
        else:
            comp["direction"] = {"ahead": 1.0, "right": 0.6, "left": 0.6, "behind": 0.0}[c.relative_direction]
        pen = {}
        if recent_categories and recent_categories[-1] == cat:
            pen["same_category"] = 0.08
        if len(recent_categories) >= 2 and recent_categories[-2] == cat:
            pen["same_category"] = pen.get("same_category", 0) + 0.05
        story_type = ((item.metadata_json or {}).get("storytelling") or {}).get("story_type")
        if story_type and story_type == last_story_type:
            pen["same_story_type"] = 0.05  # two "place-name origin" stories in a row sound alike
        if c.relative_direction == "behind" and c.distance_m > 300 and not c.in_area:
            pen["behind"] = 0.1
        if item.category == "practical":
            pen["practical_auto"] = 0.1  # practical info is pulled on demand, not pushed
        if (item.metadata_json or {}).get("scope") == "country":
            pen["country_wide"] = COUNTRY_WIDE_PENALTY
        c.heard_before = item.id in heard_ids
        c.components = {**comp, "category": cat}
        c.penalties = pen
        c.score = sum(WEIGHTS[k] * comp[k] for k in WEIGHTS) - sum(pen.values())
        out.append(c)
    out.sort(key=lambda c: (c.heard_before, -c.score))
    for c in out:
        c.components.pop("category", None)
    return out, serendipitous


def seed_for(value):
    if isinstance(value, uuid.UUID):
        return value.int & 0xFFFFFFFF
    return hash(value) & 0xFFFFFFFF
