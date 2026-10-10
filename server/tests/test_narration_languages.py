"""Narration in several languages, one after another, in the user's order (the screen keeps one language)."""
import uuid

from localvoice.db import session_scope
from localvoice.models import ApiUsageLog, AudioAsset, KnowledgeItem
from sqlalchemy import func, select

from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx
from .test_llm_and_generation import FakeLLM

LAT, LON = MIYAJIMA


class TranslatingLLM(FakeLLM):
    def __init__(self, behaviour="first"):
        super().__init__(behaviour)
        self.translations = []

    def select(self, inp):
        sel = super().select(inp)
        if sel.action == "speak" and not sel.error:
            sel.intros = {lang: {"ja": "歩きながらどうぞ。", "en": "Here is one for the walk."}.get(lang, "Hi.")
                          for lang in inp.narration_languages}
        return sel

    def translate_story(self, story, language):
        self.translations.append((story["source_language"], language))
        return {"title": f"[{language}] {story['title']}", "short": f"[{language}] short", "body": f"[{language}] body",
                "speech": f"[{language}] speech"}, {"model": "fake", "cost_usd": 0.001, "latency_ms": 3}


def _prefs(client, t, **body):
    return client.patch("/api/v1/users/me/preferences", headers=auth(t), json=body)


def _trip_guide(client, t):
    trip = client.post("/api/v1/trips", headers=auth(t), json={}).get_json()["trip_id"]
    r = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()
    return {**r["guide"], "trip_id": trip}


def _speech(client, t, g, language, voice):
    return client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t),
                       json={"voice_profile_id": voice, "language": language})


def test_language_catalog_and_preferences(client):
    t = register(client)
    cat = client.get("/api/v1/languages", headers=auth(t)).get_json()
    assert [lang["code"] for lang in cat["ui"]] == ["ja", "en", "zh", "ko", "es", "fr"]
    assert {"ja", "en", "ko", "zh"} <= {lang["code"] for lang in cat["narration"]}
    # every narration language has a voice
    voices = client.get("/api/v1/voices", headers=auth(t)).get_json()["voices"]
    assert {lang["code"] for lang in cat["narration"]} <= {v["language"] for v in voices}

    p = client.get("/api/v1/users/me/preferences", headers=auth(t)).get_json()
    assert p["narration_languages"] == ["ja"]  # follows the screen language until chosen
    assert _prefs(client, t, language="en").get_json()["narration_languages"] == ["en"]
    p = _prefs(client, t, narration_languages=["en", "ja"], language="ja").get_json()
    assert p["narration_languages"] == ["en", "ja"] and p["language"] == "ja"
    # keeps the order and survives other voice settings
    p = _prefs(client, t, voice={"enabled": True, "voices": {"ko": "ko-default"}}).get_json()
    assert p["narration_languages"] == ["en", "ja"] and p["voice"]["voices"] == {"ko": "ko-default"}
    for bad in ([], ["ja", "ja"], ["xx"], ["ja", "en", "ko", "zh", "fr"], "ja"):
        assert _prefs(client, t, narration_languages=bad).status_code == 400
    assert _prefs(client, t, language="ko").status_code == 200
    assert _prefs(client, t, language="de").status_code == 400


def test_new_account_languages_follow_the_device(client):
    def prefs(login_id, tag):
        tokens = register(client, login_id, device_language=tag)
        return client.get("/api/v1/users/me/preferences", headers=auth(tokens)).get_json()

    ja = prefs("device-ja", "ja-JP")
    assert ja["language"] == "ja" and ja["narration_languages"] == ["ja"]
    zh = prefs("device-zh", "zh-Hans-CN")
    assert zh["language"] == "zh" and zh["narration_languages"] == ["zh"]
    de = prefs("device-de", "de_DE")
    assert de["language"] == "en" and de["narration_languages"] == ["en"]
    # a later sign-in must not replace a language the user already saved
    tokens = client.post(
        "/api/v1/auth/google", json={"id_token": "google:device-lang", "device_language": "fr-FR"}
    ).get_json()
    created = client.get("/api/v1/users/me/preferences", headers=auth(tokens)).get_json()
    assert created["language"] == "fr" and created["narration_languages"] == ["fr"]
    assert _prefs(client, tokens, language="ja", narration_languages=["ja"]).status_code == 200
    again = client.post(
        "/api/v1/auth/google", json={"id_token": "google:device-lang", "device_language": "ko-KR"}
    )
    assert again.status_code == 200
    kept = client.get("/api/v1/users/me/preferences", headers=auth(again.get_json())).get_json()
    assert kept["language"] == "ja" and kept["narration_languages"] == ["ja"]


def test_story_is_told_in_each_language_in_order(app, client):
    app.extensions["lv_llm"] = TranslatingLLM()
    add_item(app, "A", LAT, LON, speech={"ja": "語り版です。", "en": "The spoken story."})
    t = register(client)
    _prefs(client, t, narration_languages=["en", "ja"])
    g = _trip_guide(client, t)
    assert g["language"] == "ja"  # the screen
    narr = g["speech"]["narrations"]
    assert [n["language"] for n in narr] == ["en", "ja"]
    assert narr[0]["text"] == "Here is one for the walk. The spoken story."
    assert narr[0]["voice_profile_id"] == "en-default" and narr[1]["voice_profile_id"] == "ja-default"
    en = _speech(client, t, g, "en", "en-default")
    ja = _speech(client, t, g, "ja", "ja-default")
    assert en.status_code == 200 and ja.status_code == 200
    assert en.get_json()["asset_id"] != ja.get_json()["asset_id"] and en.get_json()["intro"] is not None
    assert client.get(en.get_json()["audio_path"], headers=auth(t)).status_code == 200
    # a language the guide is not told in, or a voice of another language
    assert _speech(client, t, g, "ko", "ko-default").status_code == 400
    assert _speech(client, t, g, "en", "ja-default").status_code == 400
    with session_scope(app) as db:
        texts = {a.language: a.synthesis_settings_json["text"]
                 for a in db.execute(select(AudioAsset).where(AudioAsset.scope == "shared")).scalars()}
        assert texts == {"en": "The spoken story.", "ja": "語り版です。"}


def test_other_languages_are_translated_once_and_reused(app, client):
    llm = TranslatingLLM()
    app.extensions["lv_llm"] = llm
    kid = add_item(app, "A", LAT, LON, speech={"ja": "語り版です。"})
    bodies = []
    for name in ("alice", "bob"):
        t = register(client, name)
        _prefs(client, t, narration_languages=["ja", "ko"])
        g = _trip_guide(client, t)
        ko = g["speech"]["narrations"][1]
        assert ko["language"] == "ko" and (name == "bob" or ko["text"] is None)  # not translated yet for alice
        r = _speech(client, t, g, "ko", "ko-default")
        assert r.status_code == 200, r.get_json()
        bodies.append(r.get_json()["asset_id"])
        # the history now carries the translated speech (device TTS fallback, history screen)
        h = client.get(f"/api/v1/trips/{g['trip_id']}/history", headers=auth(t)).get_json()["items"][0]
        assert h["speech"]["narrations"][1]["text"] == "Hi. [ko] speech"
    assert llm.translations == [("ja", "ko")]
    assert bodies[0] == bodies[1]  # one shared audio for everyone
    with session_scope(app) as db:
        item = db.get(KnowledgeItem, uuid.UUID(kid))
        assert item.metadata_json["translations"]["ko"]["speech"] == "[ko] speech"
        n = db.execute(select(func.count()).select_from(ApiUsageLog)
                       .where(ApiUsageLog.operation == "translate_story")).scalar_one()
        assert n == 1


def test_untranslatable_language_is_skipped_without_llm(app, client):
    add_item(app, "A", LAT, LON)
    t = register(client)
    _prefs(client, t, narration_languages=["ko", "ja"])
    g = _trip_guide(client, t)
    r = _speech(client, t, g, "ko", "ko-default")
    assert r.status_code == 503 and r.get_json()["code"] == "translation_unavailable"
    assert _speech(client, t, g, "ja", "ja-default").status_code == 200
    # apps that send no language get the screen language as before
    old = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t), json={"voice_profile_id": "ja-default"})
    assert old.status_code == 200
