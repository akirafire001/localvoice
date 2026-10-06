"""LocalVoice login sessions: opaque access/refresh tokens stored as SHA-256 hashes (auth-design §5)."""
from datetime import timedelta
from functools import wraps

from flask import current_app, g, request
from sqlalchemy import select, update

from ..db import get_db
from ..errors import ApiError, forbidden, unauthorized
from ..models import AuthRefreshToken, AuthSession, User
from ..util import now, random_token, sha256_hex


def _cfg():
    return current_app.config["LV"]


def issue_session(db, user, via, reauthenticated=True):
    cfg = _cfg()
    t = now()
    access = random_token()
    refresh = random_token()
    s = AuthSession(
        user_id=user.id,
        access_token_hash=sha256_hex(access),
        access_expires_at=t + timedelta(seconds=cfg.ACCESS_TOKEN_TTL_SEC),
        authenticated_via=via,
        last_reauthenticated_at=t if reauthenticated else None,
        expires_at=t + timedelta(seconds=cfg.REFRESH_ABSOLUTE_TTL_SEC),
    )
    db.add(s)
    db.flush()
    db.add(AuthRefreshToken(auth_session_id=s.id, token_hash=sha256_hex(refresh), expires_at=s.expires_at))
    return token_response(user, access, refresh)


def token_response(user, access, refresh):
    return {
        "user": {"id": str(user.id), "display_name": user.display_name},
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": _cfg().ACCESS_TOKEN_TTL_SEC,
        "refresh_token": refresh,
    }


def refresh_session(db, refresh_token):
    """One-time refresh exchange; reuse of a consumed token revokes the whole session."""
    t = now()
    rt = db.execute(
        select(AuthRefreshToken)
        .where(AuthRefreshToken.token_hash == sha256_hex(refresh_token))
        .with_for_update()
    ).scalar_one_or_none()
    if rt is None:
        raise unauthorized("invalid refresh token", "invalid_token")
    s = db.get(AuthSession, rt.auth_session_id, with_for_update=True)
    if s is None or s.revoked_at is not None or s.expires_at <= t:
        raise unauthorized("session expired", "session_expired")
    if rt.consumed_at is not None:
        s.revoked_at = t
        db.commit()
        raise unauthorized("refresh token reuse detected", "token_reused")
    user = db.get(User, s.user_id)
    if user is None or user.status != "active":
        raise unauthorized("session expired", "session_expired")
    access = random_token()
    new_refresh = random_token()
    s.access_token_hash = sha256_hex(access)
    s.access_expires_at = t + timedelta(seconds=_cfg().ACCESS_TOKEN_TTL_SEC)
    new_rt = AuthRefreshToken(auth_session_id=s.id, token_hash=sha256_hex(new_refresh), expires_at=s.expires_at)
    db.add(new_rt)
    db.flush()
    rt.consumed_at = t
    rt.replaced_by = new_rt.id
    return token_response(user, access, new_refresh)


def revoke_all_sessions(db, user_id, except_session_id=None):
    q = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_session_id is not None:
        q = q.where(AuthSession.id != except_session_id)
    db.execute(q.values(revoked_at=now()))


def _bearer():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    return h[len("Bearer "):].strip() or None


def authenticate_request(optional=False):
    token = _bearer()
    if token is None:
        if optional:
            return None
        raise unauthorized()
    db = get_db()
    s = db.execute(
        select(AuthSession).where(AuthSession.access_token_hash == sha256_hex(token))
    ).scalar_one_or_none()
    t = now()
    if s is None or s.revoked_at is not None or s.expires_at <= t:
        raise unauthorized("invalid token", "invalid_token")
    if s.access_expires_at <= t:
        raise unauthorized("access token expired", "token_expired")
    user = db.get(User, s.user_id)
    if user is None or user.status != "active":
        raise unauthorized("invalid token", "invalid_token")
    g.user = user
    g.auth_session = s
    return user


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        authenticate_request()
        return fn(*args, **kwargs)

    return wrapper


def require_recent_reauth():
    s = g.auth_session
    window = timedelta(seconds=_cfg().REAUTH_WINDOW_SEC)
    if s.last_reauthenticated_at is None or now() - s.last_reauthenticated_at > window:
        raise ApiError(403, "reauthentication_required", "recent reauthentication required")


def mark_reauthenticated(db):
    g.auth_session.last_reauthenticated_at = now()
    db.flush()
