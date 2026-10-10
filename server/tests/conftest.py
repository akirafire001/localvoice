import os
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

os.environ.setdefault("TESTING", "1")
# Real keys on a developer machine must not change provider defaults (model, prices) in tests.
for _key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LOCALVOICE_ANTHROPIC_API_KEY", "LOCALVOICE_OPENAI_API_KEY",
             "LLM_PROVIDER", "LLM_MODEL", "LLM_REALTIME_MODEL",
             "LLM_BACKGROUND_MODEL", "LLM_PRICES", "LLM_PRICE_INPUT_PER_MTOK", "LLM_PRICE_OUTPUT_PER_MTOK"):
    os.environ.pop(_key, None)

from localvoice import create_app  # noqa: E402
from localvoice.auth.providers import ProviderTokenInvalid  # noqa: E402
from localvoice.config import Config  # noqa: E402
from localvoice.db import Base, create_schema, drop_schema  # noqa: E402

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/localvoice_test"
)
PASSWORD = "correct horse battery staple"


class FakeGoogle:
    """id_token format for tests: 'google:<sub>[:<iat>][:<email>][:unverified]'.

    A segment containing @ is the verified email. The literal segment 'unverified' clears email_verified.
    """

    def verify(self, token):
        if not token.startswith("google:"):
            raise ProviderTokenInvalid("bad token")
        parts = token.split(":")
        import time

        iat = int(time.time())
        email = None
        verified = True
        for part in parts[2:]:
            if part == "unverified":
                verified = False
            elif "@" in part:
                email = part
            elif part.isdigit():
                iat = int(part)
        claims = {"sub": parts[1], "iat": iat, "name": "G User", "email_verified": verified}
        if email:
            claims["email"] = email
        return claims


class FakeApple:
    """id_token format: 'apple:<sub>:<nonce_hash>'; authorization code 'code:<sub>:<nonce_hash>'."""

    def __init__(self):
        self.revoked = []
        self.fail_revoke = False

    def verify_id_token(self, token, audience, nonce_hash=None):
        if not token.startswith("apple:"):
            raise ProviderTokenInvalid("bad token")
        _, sub, nonce = token.split(":", 2)
        return {"sub": sub, "nonce": nonce, "aud": audience}

    def exchange_code(self, code, client_id, redirect_uri=None):
        if not code.startswith("code:"):
            raise ProviderTokenInvalid("bad code")
        _, sub, nonce = code.split(":", 2)
        return {"id_token": f"apple:{sub}:{nonce}", "refresh_token": f"rt-{sub}-{uuid.uuid4().hex[:6]}"}

    def revoke(self, client_id, token):
        from localvoice.auth.providers import ProviderUnavailable

        if self.fail_revoke:
            raise ProviderUnavailable("down")
        self.revoked.append(token)


def make_config(**kw):
    base = dict(
        DATABASE_URL=TEST_DB,
        TESTING=True,
        APPLE_BUNDLE_ID="com.example.localvoice",
        APPLE_SERVICES_ID="com.example.localvoice.web",
        APPLE_REDIRECT_URI="https://api.example/api/v1/auth/apple/callback",
        APPLE_ANDROID_APP_RETURN_URI="intent://callback#Intent;package=com.example.localvoice;scheme=signinwithapple;end",
        TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        GOOGLE_CLIENT_IDS=["test"],
        LLM_PROVIDER="disabled",
        SOURCE_FETCH_ENABLED=False,
        TTS_PROVIDER="silent",
    )
    base.update(kw)
    return Config(**base)


@pytest.fixture(scope="session")
def _schema():
    app = create_app(make_config())
    drop_schema(app)
    create_schema(app)
    yield


@pytest.fixture
def app(_schema, tmp_path):
    app = create_app(make_config(AUDIO_STORE_DIR=str(tmp_path / "audio")))
    app.extensions["lv_google"] = FakeGoogle()
    app.extensions["lv_apple"] = FakeApple()
    yield app
    engine = app.extensions["lv_engine"]
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, login_id="alice", password=PASSWORD, **kw):
    r = client.post("/api/v1/auth/register", json={"login_id": login_id, "password": password, **kw})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}
