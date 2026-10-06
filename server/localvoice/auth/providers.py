"""External identity providers. Both are replaceable through app.extensions for tests.

- app.extensions["lv_google"]: object with verify(id_token) -> claims
- app.extensions["lv_apple"]:  object with verify_id_token(token, audience, nonce),
                                exchange_code(code, client_id, redirect_uri) -> {"id_token", "refresh_token"},
                                revoke(client_id, token)
"""
import time

import jwt
import requests
from flask import current_app

from ..errors import ApiError

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
APPLE_AUTHORIZE_URL = "https://appleid.apple.com/auth/authorize"


class ProviderTokenInvalid(Exception):
    pass


class ProviderUnavailable(Exception):
    pass


class GoogleVerifier:
    def verify(self, token):
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token as g_id_token

        cfg = current_app.config["LV"]
        if not cfg.GOOGLE_CLIENT_IDS:
            raise ProviderUnavailable("Google sign-in is not configured")
        try:
            claims = g_id_token.verify_oauth2_token(token, g_requests.Request(), audience=None)
        except ValueError as e:
            raise ProviderTokenInvalid(str(e))
        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ProviderTokenInvalid("bad issuer")
        if claims.get("aud") not in cfg.GOOGLE_CLIENT_IDS:
            raise ProviderTokenInvalid("bad audience")
        return claims


class AppleClient:
    def __init__(self):
        self._jwks = jwt.PyJWKClient(APPLE_KEYS_URL, cache_keys=True)

    def verify_id_token(self, token, audience, nonce_hash=None):
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=audience, issuer=APPLE_ISSUER
            )
        except jwt.PyJWKClientError as e:
            raise ProviderUnavailable(str(e))
        except jwt.PyJWTError as e:
            raise ProviderTokenInvalid(str(e))
        return claims

    def _client_secret(self, client_id):
        cfg = current_app.config["LV"]
        if not (cfg.APPLE_TEAM_ID and cfg.APPLE_KEY_ID and cfg.APPLE_PRIVATE_KEY):
            raise ProviderUnavailable("Sign in with Apple is not configured")
        t = int(time.time())
        return jwt.encode(
            {"iss": cfg.APPLE_TEAM_ID, "iat": t, "exp": t + 300, "aud": APPLE_ISSUER, "sub": client_id},
            cfg.APPLE_PRIVATE_KEY,
            algorithm="ES256",
            headers={"kid": cfg.APPLE_KEY_ID},
        )

    def exchange_code(self, code, client_id, redirect_uri=None):
        data = {
            "client_id": client_id,
            "client_secret": self._client_secret(client_id),
            "code": code,
            "grant_type": "authorization_code",
        }
        if redirect_uri:
            data["redirect_uri"] = redirect_uri
        try:
            r = requests.post(APPLE_TOKEN_URL, data=data, timeout=10)
        except requests.RequestException as e:
            raise ProviderUnavailable(str(e))
        if r.status_code == 400:
            raise ProviderTokenInvalid(r.text[:200])
        if r.status_code != 200:
            raise ProviderUnavailable(f"apple token endpoint {r.status_code}")
        return r.json()

    def revoke(self, client_id, token):
        try:
            r = requests.post(
                APPLE_REVOKE_URL,
                data={
                    "client_id": client_id,
                    "client_secret": self._client_secret(client_id),
                    "token": token,
                    "token_type_hint": "refresh_token",
                },
                timeout=10,
            )
        except requests.RequestException as e:
            raise ProviderUnavailable(str(e))
        if r.status_code != 200:
            raise ProviderUnavailable(f"apple revoke {r.status_code}")


def google():
    return current_app.extensions.setdefault("lv_google", GoogleVerifier())


def apple():
    ext = current_app.extensions
    if "lv_apple" not in ext:
        ext["lv_apple"] = AppleClient()
    return ext["lv_apple"]


def provider_error(e):
    if isinstance(e, ProviderUnavailable):
        return ApiError(503, "provider_unavailable", "identity provider unavailable")
    return ApiError(401, "invalid_provider_token", "identity token rejected")
