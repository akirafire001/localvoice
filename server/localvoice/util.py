import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from flask import request

from .errors import bad_request


def now():
    return datetime.now(timezone.utc)


def random_token(nbytes=32):
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_body():
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise bad_request("JSON object expected")
    return data


def require_str(data, key, max_len=None, required=True):
    v = data.get(key)
    if v is None or v == "":
        if required:
            raise bad_request(f"{key} is required", {"field": key})
        return None
    if not isinstance(v, str):
        raise bad_request(f"{key} must be a string", {"field": key})
    if max_len and len(v) > max_len:
        raise bad_request(f"{key} is too long", {"field": key})
    return v


def parse_uuid(value, field="id"):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise bad_request(f"{field} must be a UUID", {"field": field})


def parse_datetime(value, field):
    if not isinstance(value, str):
        raise bad_request(f"{field} must be an ISO 8601 string", {"field": field})
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise bad_request(f"{field} must be ISO 8601", {"field": field})
    if dt.tzinfo is None:
        raise bad_request(f"{field} must include a UTC offset", {"field": field})
    return dt


def iso(dt):
    return dt.isoformat() if dt else None


def choice(data, key, allowed, default=None):
    v = data.get(key, default)
    if v is None:
        return None
    if v not in allowed:
        raise bad_request(f"{key} must be one of {sorted(allowed)}", {"field": key})
    return v
