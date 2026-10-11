"""What to tell while there is nothing to tell here yet (the stories of a new place are still being written).

In order: the app tutorial (once per user, ever), then, only while stories are being written here, a story from a
little further away (told as such), then a story that holds anywhere in the world. Every one is a real story; this
only changes which one fills the wait. engine.evaluate tells them through the usual guide path.
"""
import hashlib

from sqlalchemy import select, text

from ..models import KnowledgeItem, NotificationHistory, TripSession
from ..util import now

TUTORIAL_KEY_PREFIX = "system:tutorial:"

# The app tutorial, told on a user's first wait. Plain facts about the app; keep in step with the app's buttons.
TUTORIAL = [
    {
        "title": "LocalVoiceへようこそ", "title_en": "Welcome to LocalVoice",
        "ja": "LocalVoiceへようこそ。このアプリは、あなたがいま通っている場所の話を、声でお届けします。"
              "画面を見ていなくても大丈夫です。スマホをポケットやかばんに入れたままで、話が自動で流れます。",
        "en": "Welcome to LocalVoice. This app tells you stories about the places you are passing through. "
              "You do not need to watch the screen: keep your phone in your pocket or bag, and the stories play "
              "by themselves.",
    },
    {
        "title": "はじめての場所では", "title_en": "In a new place",
        "ja": "まだ誰も聞いていない場所では、いまこの瞬間に、この辺りのことを調べて話を書いています。"
              "地名の由来や昔の地形などを、出典を確かめながら集めるので、少し時間がかかります。"
              "その間は、少し離れた場所の話や、世界のどこでも通じる話をお届けします。"
              "この辺りの話ができあがったら、そちらに切り替わります。",
        "en": "Where nobody has listened before, the app is looking up this area and writing its stories right "
              "now. It gathers things like the origins of place names and how the land used to be, checking each "
              "source, so it takes a little while. Meanwhile you will hear stories from a little further away, or "
              "stories that hold anywhere in the world. Once the stories of this area are ready, the guide "
              "switches to them.",
    },
    {
        "title": "ボタンの使い方", "title_en": "Using the buttons",
        "ja": "話が面白かったら「面白い」、好みでなければ「興味なし」を押してください。"
              "押すほど、あなた好みの話が選ばれるようになります。"
              "内容の間違いに気づいたら「情報が違う」でお知らせください。その話はすぐに止まります。"
              "話す頻度や声、話す言語は、設定画面でいつでも変えられます。",
        "en": "If you enjoyed a story, tap Interesting. If it was not for you, tap Not for me. The more you tap, "
              "the more the stories suit you. If you notice a mistake, tap Wrong info and that story stops at "
              "once. You can change how often the guide talks, the voice and the languages in Settings at any "
              "time.",
    },
]


def _version(t):
    return "t" + hashlib.sha256((t["ja"] + t["en"] + t["title"]).encode()).hexdigest()[:10]


def ensure_tutorial(db):
    """Stores the tutorial stories, updating any whose text changed. Returns them in order."""
    keys = [f"{TUTORIAL_KEY_PREFIX}{i}" for i in range(1, len(TUTORIAL) + 1)]
    existing = {i.canonical_key: i for i in db.execute(
        select(KnowledgeItem).where(KnowledgeItem.canonical_key.in_(keys))).scalars()}
    out = []
    for n, (key, t) in enumerate(zip(keys, TUTORIAL), 1):
        version = _version(t)
        item = existing.get(key)
        if item is not None and item.content_version == version:
            out.append(item)
            continue
        if item is None:
            item = KnowledgeItem(canonical_key=key)
            db.add(item)
        item.title, item.title_en = t["title"], t["title_en"]
        item.category = "practical"
        item.short_ja = item.body_ja = t["ja"]
        item.short_en = item.body_en = t["en"]
        item.position = None
        item.radius_m = 0
        item.confidence_level, item.fact_type = "high", "verified_fact"
        item.origin, item.review_status = "system", "reviewed"
        item.content_version = version
        item.metadata_json = {
            "scope": "tutorial", "order": n,
            "speech": {"ja": t["ja"], "en": t["en"]},
            # never picked by the usual ranking; told only through waiting_story
            "story_quality": {"auto_eligible": False, "reviewer": "system"},
        }
        db.flush()
        out.append(item)
    return out


def heard_ids(db, user_id):
    """Every story this user has been told, on any trip."""
    return set(db.execute(
        select(NotificationHistory.knowledge_item_id)
        .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
        .where(TripSession.user_id == user_id)
        .distinct()
    ).scalars())


def _first_trip(db, user_id, trip_id):
    """True when the user was never told anything before this trip (the tutorial is for a first wait only)."""
    return db.execute(
        select(NotificationHistory.id)
        .join(TripSession, TripSession.id == NotificationHistory.trip_session_id)
        .where(TripSession.user_id == user_id, TripSession.id != trip_id)
        .limit(1)
    ).first() is None


def _eligible_sql(language):
    lang = " AND (body_en IS NOT NULL OR short_en IS NOT NULL)" if language == "en" else ""
    return f"""review_status <> 'suspended'
              AND (valid_from IS NULL OR valid_from <= :t)
              AND (valid_until IS NULL OR valid_until > :t)
              AND COALESCE((metadata_json->'story_quality'->>'auto_eligible')::boolean, false)
              AND NOT (id = ANY(:skip)){lang}"""


def nearby_filler(db, lat, lon, radius_m, language, skip, t=None):
    """The nearest story within radius_m not heard yet: (item, distance in metres) or None."""
    row = db.execute(
        text(
            f"""SELECT id, ST_Distance(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d
                FROM knowledge_items
                WHERE position IS NOT NULL
                  AND COALESCE(metadata_json->>'scope', '') NOT IN ('country', 'global', 'tutorial')
                  AND ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)
                  AND {_eligible_sql(language)}
                ORDER BY d LIMIT 1"""
        ),
        {"lat": lat, "lon": lon, "r": radius_m, "t": t or now(), "skip": list(skip)},
    ).first()
    if row is None:
        return None
    return db.get(KnowledgeItem, row.id), float(row.d)


def global_story(db, language, skip, seed, t=None):
    """A story for anywhere in the world not heard yet, or None. `seed` varies the order between travellers."""
    row = db.execute(
        text(
            f"""SELECT id FROM knowledge_items
                WHERE metadata_json->>'scope' = 'global' AND {_eligible_sql(language)}
                ORDER BY md5(id::text || :seed) LIMIT 1"""
        ),
        {"t": t or now(), "skip": list(skip), "seed": str(seed)},
    ).first()
    return db.get(KnowledgeItem, row.id) if row is not None else None


def _distance_words(d, lang):
    if d < 1000:
        m = max(100, int(round(d, -2)))
        return {"ja": f"{m}メートル", "en": f"{m} metres", "zh": f"{m}米", "ko": f"{m}미터",
                "es": f"{m} metros", "fr": f"{m} mètres"}.get(lang, f"{m} m")
    km = f"{d / 1000:.1f}".rstrip("0").rstrip(".")
    return {"ja": f"{km}キロ", "en": f"{km} kilometres", "zh": f"{km}公里", "ko": f"{km}킬로미터",
            "es": f"{km} kilómetros", "fr": f"{km} kilomètres"}.get(lang, f"{km} km")


def filler_intro(d, lang):
    """Says the story is about somewhere else, so it is never taken for a story of this spot."""
    w = _distance_words(d, lang)
    return {
        "ja": f"この辺りの話を準備している間に、ここから{w}ほど離れた場所の話をひとつ。",
        "en": f"While the stories of this area are being prepared, here is one from about {w} away.",
        "zh": f"在准备这一带的故事期间，先讲一个离这里大约{w}的地方的故事。",
        "ko": f"이 근처 이야기를 준비하는 동안, 여기서 {w}쯤 떨어진 곳의 이야기를 하나 들려드릴게요.",
        "es": f"Mientras preparamos las historias de esta zona, aquí va una de un lugar a unos {w}.",
        "fr": f"Pendant que nous préparons les histoires de ce coin, en voici une d'un endroit à environ {w}.",
    }.get(lang)


def global_intro(lang):
    return {
        "ja": "この辺りの話を準備している間に、世界のどこでも通じる話をひとつ。",
        "en": "While the stories of this area are being prepared, here is one that holds anywhere in the world.",
        "zh": "在准备这一带的故事期间，先讲一个在世界任何地方都适用的故事。",
        "ko": "이 근처 이야기를 준비하는 동안, 세계 어디에서나 통하는 이야기를 하나 들려드릴게요.",
        "es": "Mientras preparamos las historias de esta zona, aquí va una que vale en cualquier parte del mundo.",
        "fr": "Pendant que nous préparons les histoires de ce coin, en voici une qui vaut partout dans le monde.",
    }.get(lang)


def waiting_story(db, user, trip, lat, lon, language, *, searching, filler_radius_m, exclude_ids=(), seed=0,
                  tutorial=True):
    """(item, kind, distance_m or None) to tell while nothing is ready here, or None.

    kind: "tutorial" (on the user's first trip, any time nothing is ready here, until it has all been told),
    "nearby" and "global" (only while stories are being written here)."""
    skip = heard_ids(db, user.id) | {i for i in exclude_ids if i is not None}
    if tutorial and _first_trip(db, user.id, trip.id):
        for item in ensure_tutorial(db):
            if item.id not in skip:
                return item, "tutorial", None
    if not searching:
        return None
    found = nearby_filler(db, lat, lon, filler_radius_m, language, skip)
    if found is not None:
        return found[0], "nearby", found[1]
    item = global_story(db, language, skip, f"{user.id}:{seed}")
    if item is not None:
        return item, "global", None
    return None
