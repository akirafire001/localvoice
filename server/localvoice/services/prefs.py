"""User-facing setting values and the rule parameters they map to (PoC tuning values)."""
from .languages import UI_LANGUAGES

CATEGORIES = [
    "history",        # 歴史・文化
    "architecture",   # 建築
    "nature",         # 自然（山・川・地形・地質・植物・動物）
    "food",           # 食
    "culture",        # 地名・方言・伝承・習慣
    "everyday_life",  # 街・暮らし
    "industry",       # 社会・産業・交通
    "seasonal",       # 今日だから価値がある情報
    "practical",      # 実用・安全
]

# New users and anything unknown get the next story right after one ends (土居輝, 2026-10-10).
DEFAULT_NOTIFICATION_LEVEL = "continuous"
# Effectively no hourly cap for now; free users get a real cap back when paid plans exist.
HOURLY_LIMIT = 1000
NOTIFICATION_LEVELS = {
    # cooldown seconds between automatic guides, max automatic guides per hour
    "quiet": {"cooldown_sec": 900, "hourly_limit": HOURLY_LIMIT},
    "normal": {"cooldown_sec": 360, "hourly_limit": HOURLY_LIMIT},
    "talkative": {"cooldown_sec": 180, "hourly_limit": HOURLY_LIMIT},
    "chatty": {"cooldown_sec": 90, "hourly_limit": HOURLY_LIMIT},
    # The app asks for the next story as soon as one finishes ("continue"); the short cooldown only keeps a
    # location update from cutting in right after a story starts.
    "continuous": {"cooldown_sec": 15, "hourly_limit": HOURLY_LIMIT},
}
DETAIL_MODES = {"auto", "short", "summary", "detailed"}
SERENDIPITY_LEVELS = {"low": 0.1, "normal": 0.2, "high": 0.35}
SELECTION_MODES = {"llm", "rule"}
PURPOSES = {"travel", "walk", "business", "commute", "other"}
LANGUAGES = set(UI_LANGUAGES)  # the app's screen language (narration languages: languages.py)
MANUAL_TRANSPORT_MODES = {"auto", "walk", "bicycle", "car", "train", "shinkansen", "ship", "other"}
MAX_SAME_CATEGORY_IN_ROW = 3


def trip_settings(trip, user):
    s = dict(trip.settings_json or {})
    s.setdefault("notification_level", user.notification_level or DEFAULT_NOTIFICATION_LEVEL)
    s.setdefault("detail_mode", user.detail_mode or "auto")
    s.setdefault("serendipity", user.serendipity_level or "normal")
    return s
