import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from localvoice.models import AuthSession, OAuthRevocationJob, OutboxMail
from localvoice.util import now

from .conftest import PASSWORD, auth, register


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def test_register_login_me(client):
    t = register(client, "Alice", display_name="アリス")
    assert t["token_type"] == "Bearer" and t["expires_in"] == 900
    me = client.get("/api/v1/users/me", headers=auth(t)).get_json()
    assert me["display_name"] == "アリス"
    assert me["login_methods"] == ["password"]
    # login ID is case-insensitive
    r = client.post("/api/v1/auth/login", json={"login_id": "alice", "password": PASSWORD})
    assert r.status_code == 200


def test_register_rules(client):
    r = client.post("/api/v1/auth/register", json={"login_id": "bob", "password": "short"})
    assert r.status_code == 400 and r.get_json()["code"] == "weak_password"
    r = client.post("/api/v1/auth/register", json={"login_id": "bob", "password": "passwordpassword"})
    assert r.get_json()["code"] == "weak_password"
    r = client.post("/api/v1/auth/register", json={"login_id": "b", "password": PASSWORD})
    assert r.get_json()["code"] == "invalid_login_id"
    register(client, "bob")
    r = client.post("/api/v1/auth/register", json={"login_id": "BOB", "password": PASSWORD})
    assert r.status_code == 409


def test_login_failure_is_generic_and_rate_limited(client):
    register(client, "carol")
    r1 = client.post("/api/v1/auth/login", json={"login_id": "carol", "password": "wrong password!!!"})
    r2 = client.post("/api/v1/auth/login", json={"login_id": "nobody", "password": "wrong password!!!"})
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json() == r2.get_json()
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"login_id": "carol", "password": "wrong password!!!"})
    r = client.post("/api/v1/auth/login", json={"login_id": "carol", "password": PASSWORD})
    assert r.status_code == 429


def test_requires_auth(client):
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client):
    t = register(client)
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r.status_code == 200
    t2 = r.get_json()
    assert t2["refresh_token"] != t["refresh_token"]
    # old access token no longer valid
    assert client.get("/api/v1/users/me", headers=auth(t)).status_code == 401
    assert client.get("/api/v1/users/me", headers=auth(t2)).status_code == 200
    # reuse of consumed refresh token revokes the whole session
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r.status_code == 401 and r.get_json()["code"] == "token_reused"
    assert client.get("/api/v1/users/me", headers=auth(t2)).status_code == 401


def test_access_token_expiry(app, client):
    t = register(client)
    from localvoice.db import session_scope

    with session_scope(app) as db:
        for s in db.execute(select(AuthSession)).scalars():
            s.access_expires_at = now() - timedelta(seconds=1)
    r = client.get("/api/v1/users/me", headers=auth(t))
    assert r.status_code == 401 and r.get_json()["code"] == "token_expired"


def test_logout(client):
    t = register(client)
    assert client.post("/api/v1/auth/logout", headers=auth(t)).status_code == 204
    assert client.get("/api/v1/users/me", headers=auth(t)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_google_login_creates_and_reuses_user(client):
    r = client.post("/api/v1/auth/google", json={"id_token": "google:g-1"})
    assert r.status_code == 201
    uid = r.get_json()["user"]["id"]
    r = client.post("/api/v1/auth/google", json={"id_token": "google:g-1"})
    assert r.status_code == 200 and r.get_json()["user"]["id"] == uid
    assert client.post("/api/v1/auth/google", json={"id_token": "bad"}).status_code == 401


def _reauth_password(client, t):
    r = client.post("/api/v1/auth/reauthenticate", headers=auth(t), json={"password": PASSWORD})
    assert r.status_code == 200, r.get_json()


def _expire_reauth(app):
    from localvoice.db import session_scope

    with session_scope(app) as db:
        for s in db.execute(select(AuthSession)).scalars():
            s.last_reauthenticated_at = now() - timedelta(minutes=10)


def test_link_google_requires_reauth_and_rejects_other_users(app, client):
    t = register(client)
    _expire_reauth(app)
    r = client.post("/api/v1/users/me/auth/google", headers=auth(t), json={"id_token": "google:g-9"})
    assert r.status_code == 403 and r.get_json()["code"] == "reauthentication_required"
    _reauth_password(client, t)
    r = client.post("/api/v1/users/me/auth/google", headers=auth(t), json={"id_token": "google:g-9"})
    assert r.status_code == 200 and set(r.get_json()["login_methods"]) == {"password", "google"}
    # same Google account → same user
    g = client.post("/api/v1/auth/google", json={"id_token": "google:g-9"}).get_json()
    assert g["user"]["id"] == t["user"]["id"]
    # another user cannot link the same Google subject
    t2 = register(client, "dave")
    r = client.post("/api/v1/users/me/auth/google", headers=auth(t2), json={"id_token": "google:g-9"})
    assert r.status_code == 409


def test_cannot_unlink_last_method(client):
    g = client.post("/api/v1/auth/google", json={"id_token": "google:only"}).get_json()
    r = client.delete("/api/v1/users/me/auth/google", headers=auth(g))
    assert r.status_code == 409 and r.get_json()["code"] == "last_login_method"


def test_google_reauth_must_be_fresh(client):
    g = client.post("/api/v1/auth/google", json={"id_token": "google:fresh"}).get_json()
    r = client.post("/api/v1/auth/reauthenticate", headers=auth(g), json={"google_id_token": "google:fresh:1000"})
    assert r.status_code == 401 and r.get_json()["code"] == "stale_provider_token"
    r = client.post("/api/v1/auth/reauthenticate", headers=auth(g), json={"google_id_token": "google:fresh"})
    assert r.status_code == 200


def _apple_start(client, platform="ios", purpose="login", headers=None, verifier="v" * 43):
    body = {"platform": platform, "purpose": purpose}
    if platform == "android" or verifier:
        body["app_code_challenge"] = _sha(verifier)
    r = client.post("/api/v1/auth/apple/start", json=body, headers=headers or {})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_apple_ios_login_and_nonce_check(app, client):
    ch = _apple_start(client)
    nh = _sha(ch["nonce"])
    body = {
        "challenge_id": ch["challenge_id"],
        "id_token": f"apple:a-1:{nh}",
        "authorization_code": f"code:a-1:{nh}",
        "code_verifier": "v" * 43,
        "display_name": "Apple User",
    }
    r = client.post("/api/v1/auth/apple", json=body)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["user"]["display_name"] == "Apple User"
    # challenge is one-time
    assert client.post("/api/v1/auth/apple", json=body).status_code == 400
    # wrong nonce rejected
    ch = _apple_start(client)
    body = {
        "challenge_id": ch["challenge_id"],
        "id_token": "apple:a-1:wrong",
        "authorization_code": "code:a-1:wrong",
        "code_verifier": "v" * 43,
    }
    assert client.post("/api/v1/auth/apple", json=body).status_code == 401
    # second login without name keeps the stored name
    ch = _apple_start(client)
    nh = _sha(ch["nonce"])
    r = client.post(
        "/api/v1/auth/apple",
        json={"challenge_id": ch["challenge_id"], "id_token": f"apple:a-1:{nh}",
              "authorization_code": f"code:a-1:{nh}", "code_verifier": "v" * 43},
    )
    assert r.status_code == 200 and r.get_json()["user"]["display_name"] == "Apple User"


def test_apple_android_handoff(app, client):
    verifier = "x" * 50
    ch = _apple_start(client, platform="android", verifier=verifier)
    assert "authorization_url" in ch
    qs = parse_qs(urlparse(ch["authorization_url"]).query)
    nh = qs["nonce"][0]
    assert nh == _sha(ch["nonce"])
    r = client.post(
        "/api/v1/auth/apple/callback",
        data={"state": ch["state"], "code": f"code:a-2:{nh}", "id_token": f"apple:a-2:{nh}"},
    )
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert loc.startswith("intent://callback?") and "scheme=signinwithapple" in loc
    params = parse_qs(urlparse(loc.split("#")[0]).query)
    handoff = params["code"][0]
    assert "a-2" not in loc  # no Apple/LocalVoice tokens in the URL
    bad = client.post(
        "/api/v1/auth/apple/complete",
        json={"challenge_id": ch["challenge_id"], "handoff_code": handoff, "code_verifier": "wrong"},
    )
    assert bad.status_code == 400
    r = client.post(
        "/api/v1/auth/apple/complete",
        json={"challenge_id": ch["challenge_id"], "handoff_code": handoff, "code_verifier": verifier},
    )
    assert r.status_code == 201, r.get_json()
    # handoff is one-time
    r = client.post(
        "/api/v1/auth/apple/complete",
        json={"challenge_id": ch["challenge_id"], "handoff_code": handoff, "code_verifier": verifier},
    )
    assert r.status_code == 400


def test_apple_link_and_unlink_with_revoke_queue(app, client):
    t = register(client)
    _reauth_password(client, t)
    ch = _apple_start(client, purpose="link", headers=auth(t))
    nh = _sha(ch["nonce"])
    r = client.post(
        "/api/v1/users/me/auth/apple",
        headers=auth(t),
        json={"challenge_id": ch["challenge_id"], "id_token": f"apple:a-3:{nh}",
              "authorization_code": f"code:a-3:{nh}", "code_verifier": "v" * 43},
    )
    assert r.status_code == 200, r.get_json()
    assert "apple" in r.get_json()["login_methods"]
    # login challenge cannot be used for link
    ch2 = _apple_start(client, purpose="login")
    nh2 = _sha(ch2["nonce"])
    r = client.post(
        "/api/v1/users/me/auth/apple",
        headers=auth(t),
        json={"challenge_id": ch2["challenge_id"], "id_token": f"apple:a-3:{nh2}",
              "authorization_code": f"code:a-3:{nh2}", "code_verifier": "v" * 43},
    )
    assert r.status_code == 400
    app.extensions["lv_apple"].fail_revoke = True
    r = client.delete("/api/v1/users/me/auth/apple", headers=auth(t))
    assert r.status_code == 202 and r.get_json()["revocation"] == "pending_revocation"
    from localvoice.db import session_scope

    with session_scope(app) as db:
        assert db.execute(select(OAuthRevocationJob)).scalars().first() is not None


def test_password_change_revokes_sessions(client):
    t = register(client)
    _reauth_password(client, t)
    r = client.put("/api/v1/users/me/auth/password", headers=auth(t), json={"password": "another long passphrase 42"})
    assert r.status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(t)).status_code == 401
    r = client.post("/api/v1/auth/login", json={"login_id": "alice", "password": "another long passphrase 42"})
    assert r.status_code == 200


def test_google_user_adds_password(client):
    g = client.post("/api/v1/auth/google", json={"id_token": "google:g-add"}).get_json()
    r = client.put("/api/v1/users/me/auth/password", headers=auth(g), json={"login_id": "gee", "password": PASSWORD})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={"login_id": "gee", "password": PASSWORD})
    assert r.status_code == 200


def test_recovery_email_and_password_reset(app, client):
    t = register(client, recovery_email="alice@example.com")
    from localvoice.db import session_scope

    def last_token():
        with session_scope(app) as db:
            m = db.execute(select(OutboxMail).order_by(OutboxMail.created_at.desc())).scalars().first()
            return m.body.split("token=")[1]

    # unverified email: reset-request still 202 but sends nothing
    with session_scope(app) as db:
        n_before = len(db.execute(select(OutboxMail)).scalars().all())
    assert client.post("/api/v1/auth/password/reset-request", json={"login_id": "alice"}).status_code == 202
    with session_scope(app) as db:
        assert len(db.execute(select(OutboxMail)).scalars().all()) == n_before
    assert client.post("/api/v1/auth/email/verify", json={"token": last_token()}).status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(t)).get_json()["recovery_email_verified"]
    assert client.post("/api/v1/auth/password/reset-request", json={"login_id": "alice"}).status_code == 202
    assert client.post("/api/v1/auth/password/reset-request", json={"login_id": "ghost"}).status_code == 202
    token = last_token()
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "brand new passphrase 77"})
    assert r.status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(t)).status_code == 401
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "brand new passphrase 88"})
    assert r.status_code == 400
    assert client.post("/api/v1/auth/login", json={"login_id": "alice", "password": "brand new passphrase 77"}).status_code == 200


def test_delete_account(app, client):
    t = register(client)
    _expire_reauth(app)
    assert client.delete("/api/v1/users/me", headers=auth(t)).status_code == 403
    _reauth_password(client, t)
    r = client.delete("/api/v1/users/me", headers=auth(t))
    assert r.status_code == 200
    assert client.post("/api/v1/auth/login", json={"login_id": "alice", "password": PASSWORD}).status_code == 401
