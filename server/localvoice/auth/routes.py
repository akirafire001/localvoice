"""Authentication & account endpoints (api-design 認証, auth-design)."""
import json
import logging
from datetime import timedelta
from urllib.parse import urlencode

from flask import Blueprint, current_app, g, jsonify, redirect, request
from sqlalchemy import delete, func, select

from ..db import get_db
from ..errors import ApiError, bad_request, conflict, unauthorized
from ..mail import send_mail
from ..models import (
    AppleCredential,
    AuthActionToken,
    AuthChallenge,
    AuthIdentity,
    AuthSession,
    LoginAttempt,
    OAuthRevocationJob,
    PasswordCredential,
    User,
)
from ..util import json_body, now, parse_uuid, random_token, require_str, sha256_hex
from . import crypto
from .passwords import (
    hash_password,
    normalize_login_id,
    validate_login_id,
    validate_password,
    verify_password,
)
from .providers import (
    APPLE_AUTHORIZE_URL,
    ProviderTokenInvalid,
    ProviderUnavailable,
    apple,
    google,
    provider_error,
)
from .sessions import (
    authenticate_request,
    issue_session,
    mark_reauthenticated,
    refresh_session,
    require_auth,
    require_recent_reauth,
    revoke_all_sessions,
)

log = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)


def _cfg():
    return current_app.config["LV"]


# ---------------------------------------------------------------- helpers


def _rate_keys(login_id_normalized):
    keys = [sha256_hex("ip:" + (request.remote_addr or "?"))]
    if login_id_normalized:
        keys.append(sha256_hex("id:" + login_id_normalized))
    return keys


def _check_rate(db, keys):
    cfg = _cfg()
    since = now() - timedelta(seconds=cfg.LOGIN_RATE_WINDOW_SEC)
    for k in keys:
        n = db.execute(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.key == k, LoginAttempt.created_at >= since
            )
        ).scalar_one()
        if n >= cfg.LOGIN_RATE_LIMIT:
            raise ApiError(429, "rate_limited", "too many attempts", headers={"Retry-After": str(cfg.LOGIN_RATE_WINDOW_SEC)})


def _record_failure(db, keys):
    for k in keys:
        db.add(LoginAttempt(key=k))
    db.commit()


def _login_methods(db, user_id):
    methods = []
    if db.get(PasswordCredential, user_id) is not None:
        methods.append("password")
    for ident in db.execute(
        select(AuthIdentity).where(AuthIdentity.user_id == user_id, AuthIdentity.status == "active")
    ).scalars():
        methods.append(ident.provider)
    return methods


def _validate_email(email):
    if not isinstance(email, str) or "@" not in email or len(email) > 254 or " " in email:
        raise bad_request("invalid email", {"field": "email"}, code="invalid_email")
    return email.strip()


def _send_email_verification(db, user, email):
    db.execute(
        delete(AuthActionToken).where(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == "verify_email",
            AuthActionToken.consumed_at.is_(None),
        )
    )
    token = random_token()
    db.add(
        AuthActionToken(
            user_id=user.id,
            purpose="verify_email",
            token_hash=sha256_hex(token),
            target_email=email,
            expires_at=now() + timedelta(seconds=_cfg().ACTION_TOKEN_TTL_SEC),
        )
    )
    link = f"{_cfg().APP_PUBLIC_URL}/verify-email?token={token}"
    send_mail(db, email, "LocalVoice 復旧用メールの確認 / Verify your recovery email", link)


def _me(db, user):
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "login_methods": _login_methods(db, user.id),
        "login_id": (db.get(PasswordCredential, user.id) or PasswordCredential(login_id=None)).login_id,
        "recovery_email": user.recovery_email,
        "recovery_email_verified": user.recovery_email_verified_at is not None,
        "created_at": user.created_at.isoformat(),
    }


# ---------------------------------------------------------------- ID / password


@bp.post("/auth/register")
def register():
    db = get_db()
    data = json_body()
    login_id = validate_login_id(data.get("login_id"))
    password = data.get("password")
    validate_password(password, login_id)
    display_name = require_str(data, "display_name", max_len=100, required=False)
    recovery_email = data.get("recovery_email")
    if recovery_email:
        recovery_email = _validate_email(recovery_email)
    norm = normalize_login_id(login_id)
    if db.execute(select(PasswordCredential).where(PasswordCredential.login_id_normalized == norm)).first():
        raise conflict("login_id is already taken", "login_id_taken")
    user = User(display_name=display_name or login_id, locale=data.get("locale") or "ja")
    db.add(user)
    db.flush()
    db.add(
        PasswordCredential(
            user_id=user.id, login_id=login_id, login_id_normalized=norm, password_hash=hash_password(password)
        )
    )
    if recovery_email:
        user.recovery_email = recovery_email
        _send_email_verification(db, user, recovery_email)
    resp = issue_session(db, user, "password")
    db.commit()
    return jsonify(resp), 201


@bp.post("/auth/login")
def login():
    db = get_db()
    data = json_body()
    login_id = data.get("login_id")
    password = data.get("password")
    if not isinstance(login_id, str) or not isinstance(password, str):
        raise unauthorized("invalid credentials", "invalid_credentials")
    norm = normalize_login_id(login_id)
    keys = _rate_keys(norm)
    _check_rate(db, keys)
    cred = db.execute(
        select(PasswordCredential).where(PasswordCredential.login_id_normalized == norm)
    ).scalar_one_or_none()
    ok = verify_password(cred.password_hash if cred else None, password)
    user = db.get(User, cred.user_id) if (ok and cred) else None
    if not ok or user is None or user.status != "active":
        _record_failure(db, keys)
        raise unauthorized("invalid credentials", "invalid_credentials")
    resp = issue_session(db, user, "password")
    db.commit()
    return jsonify(resp)


@bp.post("/auth/refresh")
def refresh():
    db = get_db()
    token = json_body().get("refresh_token")
    if not isinstance(token, str):
        raise unauthorized("invalid refresh token", "invalid_token")
    resp = refresh_session(db, token)
    db.commit()
    return jsonify(resp)


@bp.post("/auth/logout")
def logout():
    db = get_db()
    session = None
    if request.headers.get("Authorization"):
        try:
            authenticate_request()
            session = g.auth_session
        except ApiError:
            session = None
    if session is None:
        token = json_body().get("refresh_token")
        if isinstance(token, str):
            from ..models import AuthRefreshToken

            rt = db.execute(
                select(AuthRefreshToken).where(AuthRefreshToken.token_hash == sha256_hex(token))
            ).scalar_one_or_none()
            if rt is not None:
                session = db.get(AuthSession, rt.auth_session_id)
    if session is None:
        raise unauthorized()
    if session.revoked_at is None:
        session.revoked_at = now()
    db.commit()
    return "", 204


# ---------------------------------------------------------------- Google


def _verify_google(token):
    if not isinstance(token, str) or not token:
        raise bad_request("id_token is required", {"field": "id_token"})
    try:
        claims = google().verify(token)
    except (ProviderTokenInvalid, ProviderUnavailable) as e:
        raise provider_error(e)
    if not claims.get("sub"):
        raise ApiError(401, "invalid_provider_token", "identity token rejected")
    return claims


@bp.post("/auth/google")
def google_login():
    db = get_db()
    claims = _verify_google(json_body().get("id_token"))
    ident = db.execute(
        select(AuthIdentity).where(AuthIdentity.provider == "google", AuthIdentity.subject == claims["sub"])
    ).scalar_one_or_none()
    status = 200
    if ident is None:
        # Never merge by email (auth-design §4): a new Google subject is a new user.
        user = User(display_name=(claims.get("name") or "")[:100] or None, locale="ja")
        db.add(user)
        db.flush()
        db.add(AuthIdentity(user_id=user.id, provider="google", subject=claims["sub"]))
        status = 201
    else:
        if ident.status != "active":
            raise unauthorized("invalid credentials", "invalid_credentials")
        user = db.get(User, ident.user_id)
        if user is None or user.status != "active":
            raise unauthorized("invalid credentials", "invalid_credentials")
    resp = issue_session(db, user, "google")
    db.commit()
    return jsonify(resp), status


# ---------------------------------------------------------------- Apple

PURPOSES = {"login", "link", "reauthenticate"}


def _apple_audience(platform):
    cfg = _cfg()
    return cfg.APPLE_BUNDLE_ID if platform == "ios" else cfg.APPLE_SERVICES_ID


@bp.post("/auth/apple/start")
def apple_start():
    db = get_db()
    data = json_body()
    platform = data.get("platform")
    purpose = data.get("purpose", "login")
    if platform not in ("ios", "android"):
        raise bad_request("platform must be ios or android", {"field": "platform"})
    if purpose not in PURPOSES:
        raise bad_request("invalid purpose", {"field": "purpose"})
    app_code_challenge = data.get("app_code_challenge")
    if platform == "android" and not (isinstance(app_code_challenge, str) and len(app_code_challenge) == 64):
        raise bad_request("app_code_challenge (SHA-256 hex) is required", {"field": "app_code_challenge"})
    user_id = None
    if purpose in ("link", "reauthenticate"):
        authenticate_request()
        user_id = g.user.id
    audience = _apple_audience(platform)
    if not audience:
        raise ApiError(503, "provider_unavailable", "Sign in with Apple is not configured")
    nonce = random_token(24)
    state = random_token(24) if platform == "android" else None
    ch = AuthChallenge(
        purpose=purpose,
        user_id=user_id,
        client_kind=platform,
        expected_audience=audience,
        nonce_hash=sha256_hex(nonce),
        state_hash=sha256_hex(state) if state else None,
        app_code_challenge=app_code_challenge.lower() if isinstance(app_code_challenge, str) else None,
        expires_at=now() + timedelta(seconds=_cfg().APPLE_CHALLENGE_TTL_SEC),
    )
    db.add(ch)
    db.commit()
    # The app passes SHA-256(nonce) to Apple; Apple echoes it in the ID token's nonce claim.
    resp = {"challenge_id": str(ch.id), "nonce": nonce, "expires_at": ch.expires_at.isoformat()}
    if state:
        resp["state"] = state
        resp["client_id"] = audience
        resp["redirect_uri"] = _cfg().APPLE_REDIRECT_URI
        resp["authorization_url"] = APPLE_AUTHORIZE_URL + "?" + urlencode(
            {
                "client_id": audience,
                "redirect_uri": _cfg().APPLE_REDIRECT_URI,
                "response_type": "code id_token",
                "response_mode": "form_post",
                "scope": "name email",
                "state": state,
                "nonce": sha256_hex(nonce),
            }
        )
    return jsonify(resp), 201


def _load_challenge(db, challenge_id, purpose=None, lock=True):
    ch = db.get(AuthChallenge, parse_uuid(challenge_id, "challenge_id"), with_for_update=lock)
    if ch is None or ch.consumed_at is not None or ch.expires_at <= now():
        raise ApiError(400, "invalid_challenge", "challenge is invalid or expired")
    if purpose and ch.purpose != purpose:
        raise ApiError(400, "invalid_challenge", "challenge purpose mismatch")
    return ch


def _verify_apple_tokens(ch, id_token, authorization_code, redirect_uri=None):
    """Verify the native/web ID token, exchange the code once, verify the returned token too."""
    client = apple()
    try:
        native = client.verify_id_token(id_token, ch.expected_audience) if id_token else None
        if native is not None and native.get("nonce") != ch.nonce_hash:
            raise ProviderTokenInvalid("nonce mismatch")
        tokens = client.exchange_code(authorization_code, ch.expected_audience, redirect_uri)
        exchanged = client.verify_id_token(tokens["id_token"], ch.expected_audience)
    except (ProviderTokenInvalid, ProviderUnavailable) as e:
        raise provider_error(e)
    if native is not None and native.get("sub") != exchanged.get("sub"):
        raise ApiError(401, "invalid_provider_token", "identity token rejected")
    if exchanged.get("nonce") not in (None, ch.nonce_hash):
        raise ApiError(401, "invalid_provider_token", "identity token rejected")
    if native is None and exchanged.get("nonce") != ch.nonce_hash:
        raise ApiError(401, "invalid_provider_token", "identity token rejected")
    return {
        "sub": exchanged["sub"],
        "refresh_token": tokens.get("refresh_token"),
        "client_id": ch.expected_audience,
        "is_private_email": exchanged.get("is_private_email"),
    }


def _store_apple_credential(db, ident, result):
    if not result.get("refresh_token"):
        return
    cred = db.get(AppleCredential, ident.id)
    if cred is None:
        cred = AppleCredential(auth_identity_id=ident.id)
        db.add(cred)
    elif cred.refresh_token_ciphertext:
        # replaced token: revoke the old one in the background
        _queue_revocation(db, cred.apple_client_id, cred.refresh_token_ciphertext, cred.encryption_key_id)
    cred.apple_client_id = result["client_id"]
    cred.refresh_token_ciphertext = crypto.encrypt(result["refresh_token"])
    cred.encryption_key_id = crypto.key_id()
    cred.last_verified_at = now()


def _queue_revocation(db, client_id, ciphertext, key_id):
    db.add(
        OAuthRevocationJob(provider="apple", client_id=client_id, token_ciphertext=ciphertext, encryption_key_id=key_id)
    )


def _apply_apple(db, ch, result, display_name=None):
    ch.consumed_at = now()
    ident = db.execute(
        select(AuthIdentity).where(AuthIdentity.provider == "apple", AuthIdentity.subject == result["sub"])
    ).scalar_one_or_none()
    if ch.purpose == "login":
        status = 200
        if ident is None:
            user = User(display_name=(display_name or "")[:100] or None, locale="ja")
            db.add(user)
            db.flush()
            ident = AuthIdentity(user_id=user.id, provider="apple", subject=result["sub"])
            db.add(ident)
            db.flush()
            status = 201
        else:
            if ident.status != "active":
                raise unauthorized("invalid credentials", "invalid_credentials")
            user = db.get(User, ident.user_id)
            if user is None or user.status != "active":
                raise unauthorized("invalid credentials", "invalid_credentials")
            if display_name and not user.display_name:
                user.display_name = display_name[:100]
        _store_apple_credential(db, ident, result)
        resp = issue_session(db, user, "apple")
        db.commit()
        return jsonify(resp), status

    # link / reauthenticate: the current LocalVoice user must match the challenge
    authenticate_request()
    if g.user.id != ch.user_id:
        raise ApiError(403, "challenge_user_mismatch", "challenge belongs to another user")
    if ch.purpose == "link":
        require_recent_reauth()
        if ident is not None and ident.user_id != g.user.id:
            raise conflict("this Apple account is linked to another user", "identity_in_use")
        existing = db.execute(
            select(AuthIdentity).where(AuthIdentity.user_id == g.user.id, AuthIdentity.provider == "apple")
        ).scalar_one_or_none()
        if existing is not None and existing.subject != result["sub"]:
            raise conflict("another Apple account is already linked", "provider_already_linked")
        if ident is None:
            ident = AuthIdentity(user_id=g.user.id, provider="apple", subject=result["sub"])
            db.add(ident)
            db.flush()
        _store_apple_credential(db, ident, result)
        db.commit()
        return jsonify(_me(db, g.user)), 200
    # reauthenticate
    if ident is None or ident.user_id != g.user.id or ident.status != "active":
        raise unauthorized("reauthentication failed", "reauthentication_failed")
    _store_apple_credential(db, ident, result)
    mark_reauthenticated(db)
    db.commit()
    return jsonify({"reauthenticated_at": g.auth_session.last_reauthenticated_at.isoformat()})


def _check_verifier(ch, code_verifier):
    if ch.app_code_challenge is None:
        return
    if not isinstance(code_verifier, str) or sha256_hex(code_verifier) != ch.app_code_challenge:
        raise ApiError(400, "invalid_challenge", "code_verifier mismatch")


def _apple_native(data, purpose):
    db = get_db()
    ch = _load_challenge(db, data.get("challenge_id"), purpose)
    if ch.client_kind != "ios":
        raise ApiError(400, "invalid_challenge", "challenge was issued for another platform")
    _check_verifier(ch, data.get("code_verifier"))
    code = require_str(data, "authorization_code")
    id_token = require_str(data, "id_token")
    result = _verify_apple_tokens(ch, id_token, code)
    return _apply_apple(db, ch, result, data.get("display_name"))


@bp.post("/auth/apple")
def apple_login():
    return _apple_native(json_body(), "login")


@bp.post("/auth/apple/callback")
def apple_callback():
    """Android: Apple form_post. Only a one-time handoff code is passed back to the app."""
    db = get_db()
    state = request.form.get("state")
    if not state:
        raise bad_request("state is required")
    ch = db.execute(
        select(AuthChallenge).where(AuthChallenge.state_hash == sha256_hex(state)).with_for_update()
    ).scalar_one_or_none()
    if ch is None or ch.consumed_at is not None or ch.expires_at <= now() or ch.result_ciphertext:
        raise ApiError(400, "invalid_challenge", "challenge is invalid or expired")
    if request.form.get("error"):
        ch.consumed_at = now()
        db.commit()
        return redirect(_android_return({"error": request.form.get("error"), "state": state}))
    code = request.form.get("code")
    if not code:
        raise bad_request("code is required")
    result = _verify_apple_tokens(ch, request.form.get("id_token"), code, _cfg().APPLE_REDIRECT_URI)
    try:
        user_json = json.loads(request.form.get("user") or "{}")
        name = user_json.get("name") or {}
        result["display_name"] = " ".join(x for x in (name.get("firstName"), name.get("lastName")) if x) or None
    except (ValueError, AttributeError):
        result["display_name"] = None
    handoff = random_token()
    ch.result_ciphertext = crypto.encrypt(json.dumps(result))
    ch.handoff_code_hash = sha256_hex(handoff)
    db.commit()
    return redirect(_android_return({"code": handoff, "state": state}))


def _android_return(params):
    base = _cfg().APPLE_ANDROID_APP_RETURN_URI
    if base.startswith("intent://"):
        # sign_in_with_apple's Android flow: intent://callback?<params>#Intent;package=...;scheme=signinwithapple;end
        head, _, tail = base.partition("#")
        return f"{head}?{urlencode(params)}#{tail}"
    sep = "&" if "?" in base else "?"
    return base + sep + urlencode(params)


@bp.post("/auth/apple/complete")
def apple_complete():
    db = get_db()
    data = json_body()
    ch = _load_challenge(db, data.get("challenge_id"))
    if ch.client_kind != "android" or not ch.result_ciphertext or not ch.handoff_code_hash:
        raise ApiError(400, "invalid_challenge", "challenge is not ready")
    handoff = data.get("handoff_code")
    if not isinstance(handoff, str) or sha256_hex(handoff) != ch.handoff_code_hash:
        raise ApiError(400, "invalid_challenge", "handoff code mismatch")
    _check_verifier(ch, data.get("code_verifier"))
    result = json.loads(crypto.decrypt(ch.result_ciphertext))
    ch.result_ciphertext = None
    return _apply_apple(db, ch, result, result.get("display_name"))


# ---------------------------------------------------------------- reauthenticate


@bp.post("/auth/reauthenticate")
@require_auth
def reauthenticate():
    db = get_db()
    data = json_body()
    if "password" in data:
        keys = _rate_keys(None) + [sha256_hex("reauth:" + str(g.user.id))]
        _check_rate(db, keys)
        cred = db.get(PasswordCredential, g.user.id)
        if cred is None or not verify_password(cred.password_hash, data.get("password") or ""):
            _record_failure(db, keys)
            raise unauthorized("reauthentication failed", "reauthentication_failed")
    elif "google_id_token" in data:
        claims = _verify_google(data["google_id_token"])
        _require_fresh_google(claims)
        ident = db.execute(
            select(AuthIdentity).where(AuthIdentity.provider == "google", AuthIdentity.subject == claims["sub"])
        ).scalar_one_or_none()
        if ident is None or ident.user_id != g.user.id or ident.status != "active":
            raise unauthorized("reauthentication failed", "reauthentication_failed")
    elif "challenge_id" in data:
        return _apple_native(data, "reauthenticate")
    else:
        raise bad_request("password, google_id_token or Apple credentials required")
    mark_reauthenticated(db)
    db.commit()
    return jsonify({"reauthenticated_at": g.auth_session.last_reauthenticated_at.isoformat()})


def _require_fresh_google(claims):
    iat = claims.get("iat")
    if not isinstance(iat, (int, float)) or now().timestamp() - iat > _cfg().REAUTH_WINDOW_SEC:
        raise ApiError(401, "stale_provider_token", "a fresh Google sign-in is required")


# ---------------------------------------------------------------- me / linking


@bp.get("/users/me")
@require_auth
def get_me():
    return jsonify(_me(get_db(), g.user))


@bp.patch("/users/me")
@require_auth
def patch_me():
    db = get_db()
    data = json_body()
    if "display_name" in data:
        g.user.display_name = require_str(data, "display_name", max_len=100, required=False)
    db.commit()
    return jsonify(_me(db, g.user))


@bp.post("/users/me/auth/google")
@require_auth
def link_google():
    db = get_db()
    require_recent_reauth()
    claims = _verify_google(json_body().get("id_token"))
    ident = db.execute(
        select(AuthIdentity).where(AuthIdentity.provider == "google", AuthIdentity.subject == claims["sub"])
    ).scalar_one_or_none()
    if ident is not None and ident.user_id != g.user.id:
        raise conflict("this Google account is linked to another user", "identity_in_use")
    existing = db.execute(
        select(AuthIdentity).where(AuthIdentity.user_id == g.user.id, AuthIdentity.provider == "google")
    ).scalar_one_or_none()
    if existing is not None and existing.subject != claims["sub"]:
        raise conflict("another Google account is already linked", "provider_already_linked")
    if ident is None:
        db.add(AuthIdentity(user_id=g.user.id, provider="google", subject=claims["sub"]))
    db.commit()
    return jsonify(_me(db, g.user))


def _unlink(provider):
    db = get_db()
    require_recent_reauth()
    ident = db.execute(
        select(AuthIdentity).where(AuthIdentity.user_id == g.user.id, AuthIdentity.provider == provider)
    ).scalar_one_or_none()
    if ident is None:
        raise ApiError(404, "not_linked", f"{provider} is not linked")
    if len(_login_methods(db, g.user.id)) <= 1:
        raise conflict("cannot remove the last login method", "last_login_method")
    pending = False
    if provider == "apple":
        pending = _revoke_apple_identity(db, ident)
    db.delete(ident)
    # End sessions that were authenticated with this provider
    for s in db.execute(
        select(AuthSession).where(
            AuthSession.user_id == g.user.id,
            AuthSession.authenticated_via == provider,
            AuthSession.revoked_at.is_(None),
            AuthSession.id != g.auth_session.id,
        )
    ).scalars():
        s.revoked_at = now()
    db.commit()
    body = _me(db, g.user)
    if pending:
        body["revocation"] = "pending_revocation"
        return jsonify(body), 202
    return jsonify(body)


def _revoke_apple_identity(db, ident):
    """Try Apple revoke now; on failure keep the encrypted token in the retry queue. Returns pending?"""
    cred = db.get(AppleCredential, ident.id)
    if cred is None:
        return False
    try:
        apple().revoke(cred.apple_client_id, crypto.decrypt(cred.refresh_token_ciphertext))
        pending = False
    except (ProviderUnavailable, ProviderTokenInvalid, Exception):  # noqa: BLE001
        log.warning("apple revoke failed; queued for retry")
        _queue_revocation(db, cred.apple_client_id, cred.refresh_token_ciphertext, cred.encryption_key_id)
        pending = True
    db.delete(cred)
    db.flush()
    return pending


@bp.delete("/users/me/auth/google")
@require_auth
def unlink_google():
    return _unlink("google")


@bp.post("/users/me/auth/apple")
@require_auth
def link_apple():
    return _apple_native(json_body(), "link")


@bp.delete("/users/me/auth/apple")
@require_auth
def unlink_apple():
    return _unlink("apple")


@bp.put("/users/me/auth/password")
@require_auth
def put_password():
    db = get_db()
    require_recent_reauth()
    data = json_body()
    cred = db.get(PasswordCredential, g.user.id)
    password = data.get("password")
    if cred is None:
        login_id = validate_login_id(data.get("login_id"))
        validate_password(password, login_id)
        norm = normalize_login_id(login_id)
        if db.execute(select(PasswordCredential).where(PasswordCredential.login_id_normalized == norm)).first():
            raise conflict("login_id is already taken", "login_id_taken")
        db.add(
            PasswordCredential(
                user_id=g.user.id, login_id=login_id, login_id_normalized=norm, password_hash=hash_password(password)
            )
        )
    else:
        if data.get("login_id") and normalize_login_id(data["login_id"]) != cred.login_id_normalized:
            raise bad_request("changing login_id is not supported", {"field": "login_id"})
        validate_password(password, cred.login_id)
        cred.password_hash = hash_password(password)
        cred.updated_at = now()
    revoke_all_sessions(db, g.user.id)
    db.commit()
    return jsonify({"status": "ok", "sessions_revoked": True})


# ---------------------------------------------------------------- recovery email / reset


@bp.post("/users/me/recovery-email")
@require_auth
def set_recovery_email():
    db = get_db()
    require_recent_reauth()
    email = _validate_email(json_body().get("email"))
    g.user.recovery_email = email
    g.user.recovery_email_verified_at = None
    _send_email_verification(db, g.user, email)
    db.commit()
    return jsonify({"status": "verification_sent"}), 202


@bp.post("/auth/email/verify")
def verify_email():
    db = get_db()
    token = json_body().get("token")
    if not isinstance(token, str):
        raise bad_request("token is required")
    at = db.execute(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == sha256_hex(token), AuthActionToken.purpose == "verify_email"
        ).with_for_update()
    ).scalar_one_or_none()
    if at is None or at.consumed_at is not None or at.expires_at <= now():
        raise ApiError(400, "invalid_token", "token is invalid or expired")
    user = db.get(User, at.user_id)
    if user is None or user.recovery_email != at.target_email:
        raise ApiError(400, "invalid_token", "token is invalid or expired")
    at.consumed_at = now()
    user.recovery_email_verified_at = now()
    db.commit()
    return jsonify({"status": "verified"})


@bp.post("/auth/password/reset-request")
def reset_request():
    db = get_db()
    login_id = json_body().get("login_id")
    # Always 202: never reveal whether the ID exists or has a verified email (api-design).
    if isinstance(login_id, str):
        keys = _rate_keys(normalize_login_id(login_id))
        try:
            _check_rate(db, keys)
        except ApiError:
            return jsonify({"status": "accepted"}), 202
        _record_failure(db, keys)  # count requests to limit mail flooding
        cred = db.execute(
            select(PasswordCredential).where(PasswordCredential.login_id_normalized == normalize_login_id(login_id))
        ).scalar_one_or_none()
        user = db.get(User, cred.user_id) if cred else None
        if user and user.recovery_email and user.recovery_email_verified_at and user.status == "active":
            token = random_token()
            db.add(
                AuthActionToken(
                    user_id=user.id,
                    purpose="password_reset",
                    token_hash=sha256_hex(token),
                    target_email=user.recovery_email,
                    expires_at=now() + timedelta(seconds=_cfg().ACTION_TOKEN_TTL_SEC),
                )
            )
            link = f"{_cfg().APP_PUBLIC_URL}/reset-password?token={token}"
            send_mail(db, user.recovery_email, "LocalVoice パスワード再設定 / Reset your password", link)
            db.commit()
    return jsonify({"status": "accepted"}), 202


@bp.post("/auth/password/reset")
def reset_password():
    db = get_db()
    data = json_body()
    token = data.get("token")
    if not isinstance(token, str):
        raise bad_request("token is required")
    at = db.execute(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == sha256_hex(token), AuthActionToken.purpose == "password_reset"
        ).with_for_update()
    ).scalar_one_or_none()
    if at is None or at.consumed_at is not None or at.expires_at <= now():
        raise ApiError(400, "invalid_token", "token is invalid or expired")
    cred = db.get(PasswordCredential, at.user_id)
    if cred is None:
        raise ApiError(400, "invalid_token", "token is invalid or expired")
    validate_password(data.get("new_password"), cred.login_id)
    cred.password_hash = hash_password(data["new_password"])
    cred.updated_at = now()
    at.consumed_at = now()
    revoke_all_sessions(db, at.user_id)
    db.commit()
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------- delete account


@bp.delete("/users/me")
@require_auth
def delete_me():
    db = get_db()
    require_recent_reauth()
    user = g.user
    revoke_all_sessions(db, user.id)
    pending = False
    for ident in db.execute(
        select(AuthIdentity).where(AuthIdentity.user_id == user.id, AuthIdentity.provider == "apple")
    ).scalars():
        pending = _revoke_apple_identity(db, ident) or pending
    from ..services.voice import delete_user_audio_files

    delete_user_audio_files(db, user.id)
    db.delete(user)  # cascades trips, snapshots, history, credentials
    db.commit()
    if pending:
        return jsonify({"status": "deleted", "revocation": "pending_revocation"}), 202
    return jsonify({"status": "deleted"})
