"""Usage figures for the signed-in user, and generation figures for the operator dashboard."""
from datetime import timezone

from sqlalchemy import func, select, text

from ..models import AuthIdentity, KnowledgeItem, NotificationHistory, PasswordCredential, TripSession, User, UserInterest
from ..services.languages import LANGUAGES

CATEGORY_NAMES = {
    "history": "歴史・文化",
    "architecture": "建築",
    "nature": "自然",
    "food": "食",
    "culture": "文化",
    "everyday_life": "暮らし",
    "industry": "産業",
    "seasonal": "季節",
    "practical": "実用",
}

_GENERATED_LANGUAGES = text("""
WITH langs AS (
  SELECT 'ja' AS language FROM knowledge_items
   WHERE origin = 'generated' AND coalesce(body_ja, short_ja) IS NOT NULL
  UNION ALL
  SELECT 'en' FROM knowledge_items
   WHERE origin = 'generated' AND coalesce(body_en, short_en) IS NOT NULL
  UNION ALL
  SELECT k.key FROM knowledge_items AS i
   CROSS JOIN LATERAL jsonb_object_keys(
     CASE WHEN jsonb_typeof(i.metadata_json -> 'translations') = 'object'
          THEN i.metadata_json -> 'translations'
          ELSE '{}'::jsonb END
   ) AS k(key)
   WHERE i.origin = 'generated'
)
SELECT language, count(*) AS n FROM langs GROUP BY language ORDER BY n DESC, language
""")

_GENERATION_MAP = text("""
SELECT round(ST_Y(position::geometry)::numeric, 1) AS lat,
       round(ST_X(position::geometry)::numeric, 1) AS lon,
       count(*) AS n
FROM knowledge_items
WHERE origin = 'generated' AND position IS NOT NULL
GROUP BY 1, 2
ORDER BY n DESC, lat, lon
""")


def _lang_name(code):
    info = LANGUAGES.get(code) or {}
    return info.get("name_ja") or code


def _bars(rows):
    counts = [(code, int(n)) for code, n in rows]
    top = max((n for _, n in counts), default=0)
    return [
        {
            "code": code,
            "name": _lang_name(code),
            "count": n,
            "percent": round(100 * n / top) if top else 0,
        }
        for code, n in counts
    ]


def _when(value):
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _geo_label(lat, lon):
    ns = "北緯" if lat >= 0 else "南緯"
    ew = "東経" if lon >= 0 else "西経"
    return f"{ns} {abs(lat):.1f}° {ew} {abs(lon):.1f}°"


def _guide_state(history):
    if history.skipped:
        return "スキップ"
    if history.spoken:
        return "再生済み"
    if history.opened:
        return "開いた"
    return "未再生"


def login_methods(db, user_id):
    labels = []
    if db.get(PasswordCredential, user_id) is not None:
        labels.append("IDとパスワード")
    rows = db.execute(
        select(AuthIdentity.provider).where(AuthIdentity.user_id == user_id, AuthIdentity.status == "active")
    ).scalars()
    names = {"google": "Google", "apple": "Apple"}
    for provider in rows:
        labels.append(names.get(provider, provider))
    return labels


def _guide_count(db, user_id, *extra):
    query = (
        select(func.count())
        .select_from(NotificationHistory)
        .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
        .where(TripSession.user_id == user_id, *extra)
    )
    return int(db.scalar(query) or 0)


def user_usage(db, user):
    trips = db.scalar(select(func.count()).select_from(TripSession).where(TripSession.user_id == user.id)) or 0
    active = db.scalar(
        select(func.count()).select_from(TripSession).where(
            TripSession.user_id == user.id, TripSession.ended_at.is_(None)
        )
    ) or 0
    guides = _guide_count(db, user.id)
    spoken = _guide_count(db, user.id, NotificationHistory.spoken.is_(True))
    skipped = _guide_count(db, user.id, NotificationHistory.skipped.is_(True))
    languages = db.execute(
        select(NotificationHistory.language, func.count())
        .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
        .where(TripSession.user_id == user.id)
        .group_by(NotificationHistory.language)
        .order_by(func.count().desc(), NotificationHistory.language)
    ).all()
    recent_rows = db.execute(
        select(NotificationHistory)
        .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
        .where(TripSession.user_id == user.id)
        .order_by(NotificationHistory.shown_at.desc())
        .limit(10)
    ).scalars().all()
    interests = db.execute(
        select(UserInterest).where(UserInterest.user_id == user.id).order_by(UserInterest.category)
    ).scalars().all()
    return {
        "display_name": user.display_name or "名前未設定",
        "joined": _when(user.created_at),
        "methods": login_methods(db, user.id),
        "trips": int(trips),
        "active_trips": int(active),
        "guides": int(guides),
        "spoken": int(spoken),
        "skipped": int(skipped),
        "languages": _bars(languages),
        "recent": [
            {
                "title": row.title or "無題のガイド",
                "language": _lang_name(row.language),
                "when": _when(row.shown_at),
                "state": _guide_state(row),
            }
            for row in recent_rows
        ],
        "interests": [
            {
                "name": CATEGORY_NAMES.get(row.category, row.category),
                "explicit": None if row.explicit_score is None else float(row.explicit_score),
                "learned": float(row.learned_score or 0),
            }
            for row in interests
        ],
    }


def admin_overview(db):
    generated = db.scalar(
        select(func.count()).select_from(KnowledgeItem).where(KnowledgeItem.origin == "generated")
    ) or 0
    delivered = db.scalar(select(func.count()).select_from(NotificationHistory)) or 0
    users = db.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0
    generated_languages = db.execute(_GENERATED_LANGUAGES).all()
    delivered_languages = db.execute(
        select(NotificationHistory.language, func.count())
        .group_by(NotificationHistory.language)
        .order_by(func.count().desc(), NotificationHistory.language)
    ).all()
    points = []
    for lat, lon, n in db.execute(_GENERATION_MAP):
        lat_f, lon_f = float(lat), float(lon)
        points.append({"lat": lat_f, "lon": lon_f, "count": int(n), "label": _geo_label(lat_f, lon_f)})
    return {
        "generated": int(generated),
        "delivered": int(delivered),
        "users": int(users),
        "generated_languages": _bars(generated_languages),
        "delivered_languages": _bars(delivered_languages),
        "points": points,
    }
