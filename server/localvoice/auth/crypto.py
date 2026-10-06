"""Encryption for provider tokens that must be kept (Apple refresh tokens). Key lives outside the DB."""
import base64
import hashlib

from cryptography.fernet import Fernet
from flask import current_app


def _fernet():
    cfg = current_app.config["LV"]
    if not cfg.TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    key = cfg.TOKEN_ENCRYPTION_KEY.encode()
    try:
        return Fernet(key)
    except ValueError:
        # Accept any passphrase by deriving a Fernet key from it.
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))


def key_id():
    return current_app.config["LV"].TOKEN_ENCRYPTION_KEY_ID


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
