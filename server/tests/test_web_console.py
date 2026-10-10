"""Browser console: LP login link, the three sign-in methods, usage, and the operator dashboard."""
import json
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from sqlalchemy import select

from localvoice.db import session_scope
from localvoice.models import NotificationHistory, TripSession, User, UserInterest
from localvoice.util import sha256_hex
from tests.conftest import PASSWORD, auth, register
from tests.helpers import MIYAJIMA, add_item


def _text(response):
    return response.get_data(as_text=True)


def test_landing_links_to_login(client):
    page = client.get("/", headers={"Accept-Language": "ja"})
    assert page.status_code == 200
    assert 'href="/login"' in _text(page)
    assert "ログイン" in _text(page)
    english = client.get("/?lang=en")
    assert "Log in" in _text(english)


def test_login_page_offers_the_same_three_methods(client):
    page = _text(client.get("/login"))
    assert "IDとパスワードでログイン" in page
    assert "accounts.google.com/gsi/client" in page
    assert 'href="/login/apple"' in page
    started = client.get("/login/apple")
    assert started.status_code == 302
    assert started.headers["Location"].startswith("https://appleid.apple.com/auth/authorize")


def test_password_login_shows_only_that_users_usage(app, client):
    alice = register(client, "alice")
    bob = register(client, "bob", display_name="ボブ")
    item = add_item(app, "宮島の鳥居", MIYAJIMA[0], MIYAJIMA[1])
    _deliver(app, alice["user"]["id"], item, "アリスの鳥居", "ja", spoken=True)
    _deliver(app, bob["user"]["id"], item, "ボブだけの話", "en")
    with session_scope(app) as db:
        db.add(UserInterest(user_id=UUID(alice["user"]["id"]), category="history", explicit_score=1, learned_score=0.4))

    denied = client.post("/login", data={"login_id": "alice", "password": "not-the-right-secret"})
    assert denied.status_code == 401
    assert "IDまたはパスワードが違います" in _text(denied)

    signed = client.post("/login", data={"login_id": "alice", "password": PASSWORD})
    assert signed.status_code == 303
    assert signed.headers["Location"].endswith("/account")
    cookies = signed.headers.getlist("Set-Cookie")
    assert any(item.startswith("lv_access=") and "HttpOnly" in item for item in cookies)

    page = client.get("/account")
    body = _text(page)
    assert page.status_code == 200
    assert "アリスの鳥居" in body
    assert "ボブだけの話" not in body
    assert 'data-language="ja" data-count="1"' in body
    assert "歴史・文化" in body
    assert 'href="/admin"' not in body

    client.delete_cookie("lv_access", path="/")
    refreshed = client.get("/account")
    assert refreshed.status_code == 200
    assert any(item.startswith("lv_access=") for item in refreshed.headers.getlist("Set-Cookie"))

    client.post("/logout")
    assert client.get("/account").status_code == 302


def test_google_admin_is_the_configured_address_only(app, client):
    owner = client.post("/login/google", json={"id_token": "google:owner:AKIRAFIRE001@gmail.com"})
    assert owner.status_code == 200
    assert owner.get_json()["redirect"].endswith("/account")
    account = _text(client.get("/account"))
    assert 'href="/admin"' in account
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert "管理ダッシュボード" in _text(dashboard)
    with session_scope(app) as db:
        user = db.execute(select(User).where(User.is_admin.is_(True))).scalar_one()
        assert user.display_name == "G User"

    client.post("/logout")
    other = client.post("/login/google", json={"id_token": "google:other:someone@example.com"})
    assert other.status_code == 200
    assert client.get("/admin").status_code == 403
    assert 'href="/admin"' not in _text(client.get("/account"))

    client.post("/logout")
    unverified = client.post(
        "/login/google", json={"id_token": "google:pretend:akirafire001@gmail.com:unverified"}
    )
    assert unverified.status_code == 200
    assert client.get("/admin").status_code == 403


def test_linking_the_admin_google_account_opens_the_dashboard(client):
    tokens = register(client, "ownerid", display_name="運営")
    linked = client.post(
        "/api/v1/users/me/auth/google",
        headers=auth(tokens),
        json={"id_token": "google:linked-admin:akirafire001@gmail.com"},
    )
    assert linked.status_code == 200, linked.get_json()
    client.post("/login", data={"login_id": "ownerid", "password": PASSWORD})
    assert client.get("/admin").status_code == 200


def test_admin_dashboard_counts_generated_guides_by_language_and_place(app, client):
    client.post("/login/google", json={"id_token": "google:map-admin:akirafire001@gmail.com"})
    add_item(app, "宮島A", MIYAJIMA[0], MIYAJIMA[1], origin="generated", translations={"zh": {"title": "宫岛"}})
    add_item(app, "宮島B", MIYAJIMA[0], MIYAJIMA[1], origin="generated")
    add_item(app, "パリ", 48.86, 2.35, origin="generated", en=False)
    add_item(app, "厳島の下書き", MIYAJIMA[0], MIYAJIMA[1], origin="curated")
    alice = register(client, "traveler")
    item = add_item(app, "届いた話", MIYAJIMA[0], MIYAJIMA[1], origin="curated")
    _deliver(app, alice["user"]["id"], item, "届いた話", "fr")

    page = client.get("/admin")
    body = _text(page)
    assert page.status_code == 200
    assert 'data-stat="generated">3<' in body
    assert 'data-stat="delivered">1<' in body
    assert 'data-generated-language="ja" data-count="3"' in body
    assert 'data-generated-language="en" data-count="2"' in body
    assert 'data-generated-language="zh" data-count="1"' in body
    assert 'data-delivered-language="fr" data-count="1"' in body
    points = json.loads(client.get("/admin").data.split(b'id="map-points" type="application/json">')[1].split(b"</script>")[0])
    assert sorted(point["count"] for point in points) == [1, 2]
    assert any(point["count"] == 2 and abs(point["lat"] - 34.3) < 0.05 and abs(point["lon"] - 132.3) < 0.05 for point in points)


def test_apple_web_callback_starts_a_browser_session(client):
    started = client.post("/api/v1/auth/apple/start", json={"platform": "web", "purpose": "login"})
    assert started.status_code == 201, started.get_json()
    body = started.get_json()
    nonce = parse_qs(urlparse(body["authorization_url"]).query)["nonce"][0]
    assert nonce == sha256_hex(body["nonce"])
    response = client.post(
        "/api/v1/auth/apple/callback",
        data={
            "state": body["state"],
            "code": f"code:web-user:{nonce}",
            "id_token": f"apple:web-user:{nonce}",
            "user": json.dumps({"name": {"firstName": "Web", "lastName": "User"}}),
        },
    )
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/account")
    page = _text(client.get("/account"))
    assert "Web User" in page
    assert 'href="/admin"' not in page


def _deliver(app, user_id, item_id, title, language, spoken=False):
    with session_scope(app) as db:
        trip = TripSession(user_id=UUID(user_id), language=language)
        db.add(trip)
        db.flush()
        db.add(NotificationHistory(
            trip_session_id=trip.id,
            knowledge_item_id=UUID(item_id),
            selection_mode="rule",
            language=language,
            title=title,
            spoken=spoken,
        ))
