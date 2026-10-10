"""Browser sessions. The cookies hold the same opaque tokens as the app, not a second credential."""
import uuid

from flask import g, redirect, request, url_for
from sqlalchemy import select

from ..auth.sessions import refresh_session
from ..db import get_db
from ..errors import ApiError
from ..models import AuthSession, User
from ..util import now, sha256_hex

ACCESS_COOKIE = "lv_access"
REFRESH_COOKIE = "lv_refresh"


def _cfg():
    from flask import current_app

    return current_app.config["LV"]


def _secure():
    return bool(request.is_secure or _cfg().WEB_COOKIE_SECURE)


def attach_cookies(response, tokens):
    cfg = _cfg()
    secure = _secure()
    response.set_cookie(
        ACCESS_COOKIE, tokens["access_token"],
        max_age=cfg.ACCESS_TOKEN_TTL_SEC, httponly=True, samesite="Lax", secure=secure, path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE, tokens["refresh_token"],
        max_age=cfg.REFRESH_ABSOLUTE_TTL_SEC, httponly=True, samesite="Lax", secure=secure, path="/",
    )
    return response


def clear_cookies(response):
    secure = _secure()
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="Lax")
    return response


def redirect_logged_in(tokens):
    response = redirect(url_for("web.account"), code=303)
    return attach_cookies(response, tokens)


def _user_for_access(db, token):
    session = db.execute(
        select(AuthSession).where(AuthSession.access_token_hash == sha256_hex(token))
    ).scalar_one_or_none()
    t = now()
    if session is None or session.revoked_at is not None or session.expires_at <= t or session.access_expires_at <= t:
        return None
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        return None
    g.auth_session = session
    return user


def current_user():
    """The user for this browser request, refreshing the access cookie when it has expired."""
    if g.get("web_user_loaded"):
        return g.get("web_user")
    g.web_user_loaded = True
    g.web_user = None
    access = request.cookies.get(ACCESS_COOKIE)
    refresh = request.cookies.get(REFRESH_COOKIE)
    if not access and not refresh:
        return None
    db = get_db()
    if access:
        user = _user_for_access(db, access)
        if user is not None:
            g.web_user = user
            return user
    if not refresh:
        g.web_clear = True
        return None
    try:
        tokens = refresh_session(db, refresh)
    except ApiError:
        g.web_clear = True
        return None
    db.commit()
    g.web_tokens = tokens
    user = db.get(User, uuid.UUID(str(tokens["user"]["id"])))
    if user is None or user.status != "active":
        g.web_clear = True
        g.web_tokens = None
        return None
    g.auth_session = db.execute(
        select(AuthSession).where(AuthSession.access_token_hash == sha256_hex(tokens["access_token"]))
    ).scalar_one_or_none()
    g.web_user = user
    return user


def revoke_current(db):
    """End the browser session. Safe when the visitor is already signed out."""
    current_user()
    session = g.get("auth_session")
    if session is not None and session.revoked_at is None:
        session.revoked_at = now()
        db.commit()
    g.web_tokens = None
    g.web_clear = True
