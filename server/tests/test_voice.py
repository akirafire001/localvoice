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


def test_personalized_speech_is_private(app, client):
    from .test_llm_and_generation import FakeLLM

    app.extensions["lv_llm"] = FakeLLM("first")
    a = register(client, "alice")
    g = _guide(app, client, a)
    assert g["selection_mode"] == "llm"
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(a), json={"voice_profile_id": "ja-default"}).get_json()
    from localvoice.db import session_scope
    from localvoice.models import AudioAsset
    import uuid

    with session_scope(app) as db:
        asset = db.get(AudioAsset, uuid.UUID(r["asset_id"]))
        assert asset.scope == "private" and str(asset.owner_user_id) == a["user"]["id"]


def test_tts_unavailable(app, client):
    app.config["LV"].TTS_PROVIDER = "none"
    t = register(client)
    g = _guide(app, client, t)
    r = client.post(f"/api/v1/guides/{g['history_id']}/speech", headers=auth(t), json={"voice_profile_id": "ja-default"})
    assert r.status_code == 503 and r.get_json()["code"] == "tts_unavailable"
