"""Fernet symmetric encryption for external system credentials.

Key source priority:
1. EXTERNAL_SYSTEM_ENCRYPTION_KEY env var (explicit, recommended for production)
2. Derived from AUTH_SECRET_KEY via PBKDF2 (convenient for dev, deterministic)
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_key_from_secret(secret: str) -> bytes:
    """Derive a valid Fernet key from an arbitrary secret string via PBKDF2."""
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), b"agenticos-ext-sys", 100_000)
    return base64.urlsafe_b64encode(dk)


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    from app.core.config import get_settings

    settings = get_settings()
    explicit_key = settings.external_system_encryption_key.strip()

    if explicit_key:
        # If it's already a valid Fernet key, use directly
        try:
            _fernet = Fernet(explicit_key.encode("utf-8"))
            return _fernet
        except Exception:
            pass
        # Otherwise derive from it
        key = _derive_key_from_secret(explicit_key)
    else:
        key = _derive_key_from_secret(settings.auth_secret_key)

    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returns a URL-safe base64 string."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a string. Raises InvalidToken on bad key or corrupted data."""
    return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def decrypt_safe(ciphertext: str, default: str = "") -> str:
    """Decrypt without raising — returns *default* on failure."""
    try:
        return decrypt(ciphertext)
    except (InvalidToken, Exception):
        return default
