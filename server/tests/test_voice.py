from .conftest import auth, register
from .helpers import MIYAJIMA, add_item, ctx

LAT, LON = MIYAJIMA


def _guide(app, client, t, title="A"):
    add_item(app, title, LAT, LON)
    trip = client.post("/api/v1/trips", headers=auth(t), json={}).get_json()["trip_id"]
    return client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()["guide"]


def test_voices_list_and_sample(client):
    t = register(client)
    r = client.get("/api/v1/voices?language=ja", headers=auth(t)).get_json()
    assert {v["voice_profile_id"] for v in r["voices"]} == {"ja-default", "ja-bright"}
    s = client.post("/api/v1/voices/ja-default/sample", headers=auth(t))
    assert s.status_code == 200 and s.get_json()["status"] == "ready"
    audio = client.get(s.get_json()["audio_path"], headers=auth(t))
    assert audio.status_code == 200 and audio.data[:4] == b"RIFF"


def test_guide_speech_cache_and_access(app, client):
    a = register(client, "alice")
    b = register(client, "bob")
    g = _guide(app, client, a)
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(a), json={"voice_profile_id": "ja-default"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    again = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(a), json={"voice_profile_id": "ja-default"})
    assert again.get_json()["asset_id"] == body["asset_id"]  # cached, not regenerated
    assert client.get(body["audio_path"], headers=auth(a)).status_code == 200
    # another user who never received the guide cannot fetch it
    assert client.get(body["audio_path"], headers=auth(b)).status_code == 404
    bad = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(a), json={"voice_profile_id": "en-default"})
    assert bad.status_code == 400
    # wrong_info suspends the story → audio no longer served
    client.post(f"/api/v1/guides/{g['history_id']}/feedback", headers=auth(a), json={"action": "wrong_info"})
    assert client.get(body["audio_path"], headers=auth(a)).status_code == 410
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(a), json={"voice_profile_id": "ja-default"})
    assert r.status_code == 410


def test_llm_guide_plays_a_private_intro_before_the_shared_story(app, client):
    import uuid

    from localvoice.db import session_scope
    from localvoice.models import AudioAsset

    from .test_llm_and_generation import FakeLLM

    app.extensions["lv_llm"] = FakeLLM("first")
    add_item(app, "A", LAT, LON, speech={"ja": "語り版の本文です。"})
    speech = {}
    for name in ("alice", "bob"):
        t = register(client, name)
        trip = client.post("/api/v1/trips", headers=auth(t), json={}).get_json()["trip_id"]
        g = client.post(f"/api/v1/trips/{trip}/context", headers=auth(t), json=ctx(LAT, LON)).get_json()["guide"]
        assert g["selection_mode"] == "llm" and g["speech"]["intro"] == "歩きながらどうぞ。"
        assert g["speech"]["text"] == "歩きながらどうぞ。 語り版の本文です。"
        r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t), json={"voice_profile_id": "ja-default"})
        assert r.status_code == 200, r.get_json()
        speech[name] = (t, r.get_json())
    (ta, a), (tb, b) = speech["alice"], speech["bob"]
    assert a["asset_id"] == b["asset_id"]  # the story is synthesised once for everyone
    assert a["intro"]["asset_id"] != b["intro"]["asset_id"]
    assert client.get(a["intro"]["audio_path"], headers=auth(ta)).status_code == 200
    assert client.get(a["intro"]["audio_path"], headers=auth(tb)).status_code == 404
    with session_scope(app) as db:
        story = db.get(AudioAsset, uuid.UUID(a["asset_id"]))
        intro = db.get(AudioAsset, uuid.UUID(a["intro"]["asset_id"]))
        assert story.scope == "shared" and story.synthesis_settings_json["text"] == "語り版の本文です。"
        assert intro.scope == "private" and intro.synthesis_settings_json["text"] == "歩きながらどうぞ。"


def test_rule_guide_has_no_intro(app, client):
    t = register(client)
    g = _guide(app, client, t)
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t), json={"voice_profile_id": "ja-default"})
    assert r.status_code == 200 and r.get_json()["intro"] is None


def test_tts_unavailable(app, client):
    app.config["LV"].TTS_PROVIDER = "none"
    t = register(client)
    g = _guide(app, client, t)
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t), json={"voice_profile_id": "ja-default"})
    assert r.status_code == 503 and r.get_json()["code"] == "tts_unavailable"
