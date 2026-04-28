from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt_raw, digest_raw = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(payload: dict[str, Any], *, secret: str, expires_in_seconds: int) -> str:
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str, *, secret: str) -> dict[str, Any] | None:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature_raw), expected):
            return None
        payload = json.loads(_b64decode(payload_raw))
        if not isinstance(payload, dict):
            return None
        expires_at = payload.get("exp")
        if not isinstance(expires_at, int) or expires_at < int(time.time()):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, TypeError):
        return None
