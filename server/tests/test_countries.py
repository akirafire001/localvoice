"""Research themes, towns abroad, country-wide manners and the user's home country (2026-10-09)."""
from datetime import datetime, timezone

from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import ApiUsageLog, KnowledgeItem

from .conftest import auth, register
from .helpers import add_item, ctx
from .test_llm_and_generation import SPEECH, FakeLLM, _send, _trip

PARIS = (48.8575, 2.3580)


def _story(title, lat, lon, **kw):
    return {
        "title": title, "title_en": title, "category": "culture", "short_ja": f"{title}の話です。とても面白い話です。",
        "body_ja": f"{title}についての詳しい話です。" * 3, "short_en": "s", "body_en": "b", "lat": lat, "lon": lon,
        "radius_m": 300, "fact_type": "verified_fact", "content_kind": "custom", "why_here": "ここだから",
        "interest_hook": "意外", "present_connection": None, "time_sensitive": False,
        "claims": [{"text_ja": "事実", "text_en": "fact", "source_ids": ["m1"]}], **SPEECH, **kw,
    }


def test_town_of_abroad_uses_districts_and_keeps_the_country():
    from localvoice.services.sources import _town_of

    addr = {"suburb": "マレ地区", "city": "パリ", "state": "イル＝ド＝フランス", "country": "フランス", "country_code": "fr"}
    assert _town_of(addr) == ("マレ地区", "パリ、イル＝ド＝フランス")
    assert _town_of({"town": "ハルシュタット", "state": "オーバーエスターライヒ州", "country_code": "at"}) == (
        "ハルシュタット", "オーバーエスターライヒ州")
    assert _town_of({"country": "フランス", "country_code": "fr"}) is None
    # Japan is unchanged
    assert _town_of({"neighbourhood": "尻手二丁目", "city": "横浜市", "country_code": "jp"}) == ("尻手", "横浜市")


def test_research_prompts_abroad_and_local_manners(app, monkeypatch):
    from localvoice.services.llm import COUNTRY_RESEARCH_THEMES, OpenAILLM

    prompts = []

    def fake_web(self, prompt, max_uses):
        prompts.append(prompt)
        return [], {"model": "m", "cost_usd": 0.0, "latency_ms": 1}

    monkeypatch.setattr(OpenAILLM, "_web_research", fake_web)
    llm = OpenAILLM.__new__(OpenAILLM)
    marais = {"town": "マレ地区", "municipality": "パリ", "country_code": "fr", "country": "フランス"}
    llm.research_local_history("u09tvw", PARIS, [marais], ["origin", "shrines_lore", "local_taboos"])
    origin, shrines, taboos = prompts
    assert "マレ地区（パリ）（フランス、緯度48.8575" in origin and "現地の言語の資料" in origin
    assert "江戸" not in origin and "教会" in shrines
    assert "この地域ならではのもの" in taboos
    assert all("該当なし" in p for p in prompts)  # nothing found → nothing made up

    prompts.clear()
    shitte = {"town": "尻手", "municipality": "神奈川県横浜市鶴見区", "country_code": "jp", "country": "日本"}
    llm.research_local_history("xn764e", (35.53, 139.68), [shitte], ["origin"])
    assert "神奈川県横浜市鶴見区尻手" in prompts[0] and "郷土資料館" in prompts[0] and "江戸" in prompts[0]

    prompts.clear()
    _mats, meta = llm.research_country_customs("フランス", ["money", "etiquette"])
    assert meta["themes"] == [k for k, _ in COUNTRY_RESEARCH_THEMES if k in ("money", "etiquette")]
    assert all("フランス" in p and "国全体" in p for p in prompts) and any("チップ" in p for p in prompts)


class Abroad(FakeLLM):
    """Researches a town in Paris and the manners of France."""

    def __init__(self):
        super().__init__()
        self.country_batches, self.generate_calls = [], []

    def research_local_history(self, cell, center, towns, themes=None, known=None):
        return [], {"model": "fake", "cost_usd": 0.0, "themes": themes, "found": {k: 0 for k in themes},
                    "prompt_version": "local-history-v3"}

    def research_country_customs(self, country, themes=None, known=None):
        self.country_batches.append((country, themes))
        return [{"kind": "web", "title": "チップ", "url": f"https://example.org/{themes[0]}", "publisher": "example.org",
                 "text": "フランスの飲食店ではサービス料が料金に含まれている。"}], {
            "model": "fake", "cost_usd": 0.01, "themes": themes, "found": {k: 1 for k in themes},
            "prompt_version": "local-history-v3"}

    def generate_items(self, cell, center, materials, already_told=None, country=None):
        self.generate_calls.append(country)
        lat, lon = center
        if country:
            title = {"taboos": "教会で帽子を取る理由", "table_manners": "パンを皿に置かないわけ"}[materials[0]["url"].rsplit("/", 1)[1]]
            return [_story(title, lat, lon)], {"model": "fake", "cost_usd": 0.0}
        return [_story("マレ地区の石畳", lat, lon, content_kind="local_tip", time_sensitive=True)], {
            "model": "fake", "cost_usd": 0.0}


def test_country_wide_manners_are_researched_once_per_country(app, monkeypatch):
    from localvoice.services import knowledge_gen

    fake = Abroad()
    app.extensions["lv_llm"] = fake
    town = {"kind": "osm", "title": "マレ地区（パリ）", "url": "https://www.openstreetmap.org/node/1",
            "publisher": "OpenStreetMap", "lat": PARIS[0], "lon": PARIS[1], "text": "町名: マレ地区",
            "town": "マレ地区", "municipality": "パリ", "country_code": "fr", "country": "フランス"}
    seen_country = []

    def collect(*a, country_code=None, **k):
        seen_country.append(country_code)
        return [{"kind": "wikipedia_fr", "title": "Le Marais", "url": "https://fr.wikipedia.org/wiki/Le_Marais",
                 "publisher": "Wikipedia (fr)", "text": "..."}]

    monkeypatch.setattr(knowledge_gen, "collect_materials", collect)
    monkeypatch.setattr(knowledge_gen, "town_materials", lambda *a, **k: [dict(town)])
    monkeypatch.setattr(knowledge_gen.geo, "geohash_center", lambda c: PARIS)
    with app.app_context():
        for cell in ("u09tvw", "u09tvx"):
            with session_scope(app) as db:
                knowledge_gen._generate(db, cell)
    assert seen_country == ["fr", "fr"]  # Wikipedia in French too
    per_job = app.config["LV"].COUNTRY_RESEARCH_THEMES_PER_JOB
    assert [b for _, b in fake.country_batches] == [["taboos", "etiquette"][:per_job], ["table_manners", "money"][:per_job]]
    assert {c for c, _ in fake.country_batches} == {"フランス"}
    with session_scope(app) as db:
        items = db.execute(select(KnowledgeItem)).scalars().all()
        wide = [i for i in items if i.metadata_json.get("scope") == "country"]
        local = [i for i in items if i.metadata_json.get("scope") != "country"]
        assert len(wide) == 2 and all(i.metadata_json["country"] == "fr" and i.metadata_json["audience"] == "visitors"
                                      and i.radius_m == 5000 and i.canonical_key.startswith("gen:country:fr:")
                                      for i in wide)
        assert [i.title for i in local] == ["マレ地区の石畳"]  # the second cell does not retell it
        tip = local[0]
        assert tip.metadata_json["country"] == "fr" and tip.metadata_json["story_quality"]["auto_eligible"]
        assert tip.valid_until is not None  # a shop or experience may close: it expires
        logs = db.execute(select(ApiUsageLog).where(ApiUsageLog.operation == "local_history_research")).scalars().all()
        assert ["country:fr"] in [log.details_json["towns"] for log in logs]


def test_country_wide_stories_only_for_travellers_from_elsewhere(app, client):
    lat, lon = PARIS
    add_item(app, "マレ地区の石畳", lat, lon, country="fr")
    add_item(app, "フランスのチップ", 48.0, 2.0, radius_m=5000, scope="country", country="fr", audience="visitors")
    add_item(app, "日本のチップ", lat, lon, radius_m=5000, scope="country", country="jp", audience="visitors")
    from localvoice.services.ranking import fetch_candidates

    with session_scope(app) as db, app.app_context():
        here, _ = fetch_candidates(db, lat, lon, "walking", home_country="jp")
        assert sorted(c.item.title for c in here) == ["フランスのチップ", "マレ地区の石畳"]
        wide = next(c for c in here if c.item.title == "フランスのチップ")
        assert wide.in_area and wide.relative_direction is None
        home, _ = fetch_candidates(db, lat, lon, "walking", home_country="fr")
        assert [c.item.title for c in home] == ["マレ地区の石畳"]
    # stories without a country are Japanese: Japan's country-wide stories reach a French traveller in Japan
    add_item(app, "尻手の話", 35.53, 139.68)
    with session_scope(app) as db, app.app_context():
        assert sorted(c.item.title for c in fetch_candidates(db, 35.53, 139.68, "walking", home_country="fr")[0]) == [
            "尻手の話", "日本のチップ"]
        assert [c.item.title for c in fetch_candidates(db, 35.53, 139.68, "walking", home_country="jp")[0]] == ["尻手の話"]


def test_home_country_preference(client):
    t = register(client)
    assert client.get("/api/v1/users/me/preferences", headers=auth(t)).get_json()["home_country"] == "jp"
    r = client.patch("/api/v1/users/me/preferences", headers=auth(t), json={"home_country": "FR"})
    assert r.status_code == 200 and r.get_json()["home_country"] == "fr"
    for bad in ("France", "f", 1):
        r = client.patch("/api/v1/users/me/preferences", headers=auth(t), json={"home_country": bad})
        assert r.status_code == 400


def test_local_time_follows_the_phone_time_zone(app, client):
    lat, lon = 35.53, 139.68
    add_item(app, "尻手の話", lat, lon)
    fake = FakeLLM("first")
    app.extensions["lv_llm"] = fake
    t = register(client)
    trip = _trip(client, t)
    body = ctx(lat, lon, observed_at=datetime.now(timezone.utc).isoformat())
    body["utc_offset_min"] = 540
    _send(client, t, trip, body)
    assert fake.calls[-1].local_time.endswith("+09:00")
