"""安全原语回归（docs/design/系统改造总方案.md 战线 B1/B2）。

覆盖「自研归位」改造后的两条契约：

- **JWT（PyJWT）**：与旧手写实现的线上格式兼容（存量令牌不失效）；
  算法白名单拒绝 ``alg=none`` / ``alg=RS256`` 伪造；过期拒绝。
- **密码哈希（Argon2id）**：新哈希为 argon2 格式；存量 pbkdf2 双验通过；
  ``needs_rehash`` 只对存量弱哈希返回 True（登录后无缝升级的依据）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    is_legacy_hash,
    needs_rehash,
    verify_password,
)

SECRET = "unit-test-secret-that-is-at-least-32-bytes-long"


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


# ── JWT ───────────────────────────────────────────────────────────────


def test_token_roundtrip_and_payload_integrity():
    token = create_access_token({"sub": "42", "role": "admin"}, secret=SECRET, expires_in_seconds=600)
    payload = decode_access_token(token, secret=SECRET)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    # iat/exp 由签发方注入且为整数（旧实现契约）
    assert isinstance(payload["iat"], int) and isinstance(payload["exp"], int)
    assert payload["exp"] - payload["iat"] == 600


def test_legacy_handwritten_token_still_accepted():
    """升级兼容：旧手写 HS256 实现签的令牌，PyJWT 校验必须继续通过。"""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    body = {"sub": "7", "iat": now, "exp": now + 300}
    signing_input = ".".join(
        [
            _b64e(json.dumps(header, separators=(",", ":")).encode()),
            _b64e(json.dumps(body, separators=(",", ":")).encode()),
        ]
    )
    signature = hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    legacy_token = f"{signing_input}.{_b64e(signature)}"
    payload = decode_access_token(legacy_token, secret=SECRET)
    assert payload is not None and payload["sub"] == "7"


def test_alg_none_forgery_rejected():
    """算法白名单：header.alg=none 的伪造令牌必须被拒绝（旧实现会接受）。"""
    body = {"sub": "9", "exp": int(time.time()) + 300}
    forged = f"{_b64e(json.dumps({'alg': 'none', 'typ': 'JWT'}).encode())}.{_b64e(json.dumps(body).encode())}."
    assert decode_access_token(forged, secret=SECRET) is None


def test_alg_rs256_forgery_rejected():
    body = {"sub": "9", "exp": int(time.time()) + 300}
    forged = (
        f"{_b64e(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())}."
        f"{_b64e(json.dumps(body).encode())}.{_b64e(b'attacker-controlled')}"
    )
    assert decode_access_token(forged, secret=SECRET) is None


def test_expired_token_rejected():
    token = create_access_token({"sub": "1"}, secret=SECRET, expires_in_seconds=-10)
    assert decode_access_token(token, secret=SECRET) is None


def test_wrong_secret_and_malformed_rejected():
    token = create_access_token({"sub": "1"}, secret=SECRET, expires_in_seconds=60)
    assert decode_access_token(token, secret="another-secret-also-32-bytes-long!") is None
    assert decode_access_token("not-a-jwt", secret=SECRET) is None
    assert decode_access_token("", secret=SECRET) is None


def test_missing_exp_rejected():
    """exp 必填：没有 exp 的令牌按旧实现语义视为无效。"""
    payload = _b64e(json.dumps({"sub": "1"}).encode())
    token = f"{_b64e(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())}.{payload}."
    assert decode_access_token(token, secret=SECRET) is None


# ── 密码哈希 ──────────────────────────────────────────────────────────


def test_hash_password_uses_argon2id():
    digest = hash_password("correct horse battery staple")
    assert digest.startswith("$argon2id$"), digest[:20]
    assert not is_legacy_hash(digest)
    assert verify_password("correct horse battery staple", digest)
    assert not verify_password("wrong password", digest)


def test_legacy_pbkdf2_hash_still_verified():
    """存量 pbkdf2 哈希（升级前的 hash_password 产物）双验必须通过。"""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", "legacy-pw".encode(), salt, 200_000)
    legacy = f"pbkdf2_sha256$200000${_b64e(salt)}${_b64e(digest)}"
    assert is_legacy_hash(legacy)
    assert verify_password("legacy-pw", legacy)
    assert not verify_password("legacy-pw ", legacy)
    assert not verify_password("nope", legacy)


def test_needs_rehash_flags_only_legacy_and_weak():
    fresh = hash_password("any-pw")
    assert needs_rehash(fresh) is False
    legacy = f"pbkdf2_sha256$200000${_b64e(os.urandom(16))}${_b64e(os.urandom(32))}"
    assert needs_rehash(legacy) is True
    assert needs_rehash(None) is False
    assert needs_rehash("") is False
    assert needs_rehash("garbage-not-a-hash") is False


def test_hash_is_salted_and_non_deterministic():
    assert hash_password("same") != hash_password("same")


def test_verify_password_garbage_input_safe():
    assert verify_password("pw", "") is False
    assert verify_password("pw", None) is False  # type: ignore[arg-type]
    assert verify_password("pw", "not$a$hash") is False


@pytest.mark.parametrize("bad", ["pbkdf2_sha256$bad$bad$bad", "argon2$broken", "pbkdf2_sha256$abc$!$!"])
def test_verify_password_malformed_hash_safe(bad):
    assert verify_password("pw", bad) is False
