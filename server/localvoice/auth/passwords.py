"""ID/password rules (auth-design §3). Argon2id with OWASP minimum m=19MiB, t=2, p=1."""
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from flask import current_app

from ..errors import bad_request

_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
# Pre-computed hash used to equalize timing when the login ID does not exist.
_DUMMY_HASH = _hasher.hash("localvoice-dummy-password-for-timing")

LOGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")

# Small built-in deny list. A breached-password service can be plugged in later (auth-design §3).
COMMON_PASSWORDS = {
    "password", "password123", "passwordpassword", "123456789012345", "1234567890123456",
    "qwertyuiopasdfg", "qwertyuiopasdfgh", "iloveyouiloveyou", "aaaaaaaaaaaaaaa",
    "abcdefghijklmno", "abcdefghijklmnop", "000000000000000", "111111111111111",
    "passwordpassword1", "letmeinletmein1", "localvoicelocalvoice",
}


def normalize_login_id(login_id: str) -> str:
    return login_id.strip().lower()


def validate_login_id(login_id):
    if not isinstance(login_id, str) or not LOGIN_ID_RE.match(login_id.strip()):
        raise bad_request(
            "login_id must be 3-32 characters of letters, digits, '.', '_' or '-', starting with a letter or digit",
            {"field": "login_id"},
            code="invalid_login_id",
        )
    return login_id.strip()


def validate_password(password, login_id=None):
    cfg = current_app.config["LV"]
    if not isinstance(password, str):
        raise bad_request("password is required", {"field": "password"}, code="weak_password")
    if len(password) < cfg.PASSWORD_MIN_LEN:
        raise bad_request(
            f"password must be at least {cfg.PASSWORD_MIN_LEN} characters",
            {"field": "password", "min_length": cfg.PASSWORD_MIN_LEN},
            code="weak_password",
        )
    if len(password) > cfg.PASSWORD_MAX_LEN:
        raise bad_request(
            f"password must be at most {cfg.PASSWORD_MAX_LEN} characters",
            {"field": "password", "max_length": cfg.PASSWORD_MAX_LEN},
            code="weak_password",
        )
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(password)) < 4:
        raise bad_request("password is too common", {"field": "password"}, code="weak_password")
    if login_id and normalize_login_id(login_id) in lowered:
        raise bad_request("password must not contain the login ID", {"field": "password"}, code="weak_password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash, password) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
