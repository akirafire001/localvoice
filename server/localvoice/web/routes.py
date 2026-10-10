"""HTML screens for the browser console."""
from flask import current_app, g, jsonify, redirect, render_template, request, url_for

from ..auth.routes import _verify_google, login_with_google, login_with_password, start_apple_challenge
from ..db import get_db
from ..errors import ApiError
from . import bp
from .session import attach_cookies, clear_cookies, current_user, redirect_logged_in, revoke_current
from .stats import admin_overview, user_usage

_ERRORS = {
    "invalid_credentials": "IDまたはパスワードが違います。",
    "rate_limited": "試行が多すぎます。しばらくしてからもう一度お試しください。",
    "invalid_provider_token": "ログインを確認できませんでした。もう一度お試しください。",
    "provider_unavailable": "外部ログインをいま利用できません。",
    "apple": "Appleでのログインに失敗しました。",
    "apple_cancelled": "Appleでのログインがキャンセルされました。",
}


def _message(error):
    if isinstance(error, ApiError):
        return _ERRORS.get(error.code, "ログインに失敗しました。")
    if not error:
        return None
    return _ERRORS.get(error, "ログインに失敗しました。")


def _login_context(error=None):
    cfg = current_app.config["LV"]
    return {
        "user": None,
        "error": _message(error),
        "google_client_id": cfg.GOOGLE_WEB_CLIENT_ID,
        "apple_ready": bool(cfg.APPLE_SERVICES_ID and cfg.APPLE_REDIRECT_URI),
    }


def _login_page(error=None, status=200):
    return render_template("web/login.html", **_login_context(error)), status


@bp.after_request
def _persist_browser_session(response):
    if request.endpoint in ("web.account", "web.admin"):
        response.headers["Cache-Control"] = "no-store"
    if g.get("web_clear"):
        return clear_cookies(response)
    tokens = g.get("web_tokens")
    if tokens:
        attach_cookies(response, tokens)
    return response


def _require_user():
    user = current_user()
    if user is None:
        return None, redirect(url_for("web.login"))
    return user, None


@bp.get("/login")
def login():
    if current_user() is not None:
        return redirect(url_for("web.account"))
    page, status = _login_page(request.args.get("error"))
    return page, status


@bp.post("/login")
def login_password():
    db = get_db()
    try:
        tokens = login_with_password(db, request.form.get("login_id"), request.form.get("password"))
    except ApiError as error:
        page, status = _login_page(error, error.status)
        return page, status
    return redirect_logged_in(tokens)


@bp.post("/login/google")
def login_google():
    db = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        claims = _verify_google(payload.get("id_token"))
        tokens, _status = login_with_google(db, claims, payload)
    except ApiError as error:
        return jsonify({"message": _message(error)}), error.status
    response = jsonify({"redirect": url_for("web.account")})
    return attach_cookies(response, tokens)


@bp.get("/login/apple")
def login_apple():
    db = get_db()
    try:
        started = start_apple_challenge(db, "web", "login")
    except ApiError as error:
        context = _login_context(error)
        status = error.status
        if error.code == "provider_unavailable":
            context["error"] = "Appleログインはサーバー側の設定が済んでから使えます。"
            context["apple_ready"] = False
            status = 503
        return render_template("web/login.html", **context), status
    return redirect(started["authorization_url"])


@bp.post("/logout")
def logout():
    revoke_current(get_db())
    return redirect(url_for("web.login"))


@bp.get("/account")
def account():
    user, bounce = _require_user()
    if bounce is not None:
        return bounce
    usage = user_usage(get_db(), user)
    return render_template("web/account.html", user=user, usage=usage)


@bp.get("/admin")
def admin():
    user, bounce = _require_user()
    if bounce is not None:
        return bounce
    if not user.is_admin:
        return render_template("web/forbidden.html", user=user), 403
    return render_template("web/admin.html", user=user, stats=admin_overview(get_db()))
