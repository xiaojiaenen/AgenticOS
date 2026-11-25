"""安全原语：JWT 签发/校验、密码哈希、凭据加密。

## 自研归位（docs/design/系统改造总方案.md 战线 B）

- **JWT**：原先手写 base64+HMAC，未校验 header.alg（alg 混淆攻击面）、无
  标准校验链。现改用 **PyJWT**（BSD，标准实现），固定 ``algorithms=["HS256"]``
  白名单 —— 伪造 ``none``/``RS256`` header 的令牌直接拒绝。签名/载荷格式
  与旧实现兼容（同为 HS256 紧凑序列化），存量令牌在升级后仍然有效。
- **密码哈希**：PBKDF2-SHA256(200k) → **Argon2id**（OWASP 2025 首选，
  argon2-cffi MIT 零 CVE）。存量 pbkdf2 哈希走「双验过渡」：``verify_password``
  按哈希前缀分派，登录成功后由 ``needs_rehash`` 提示服务层无缝升级为 argon2。
  passlib 已停维护，不引入。
- **凭据加密**：Fernet（cryptography）不变 —— 这本来就是标准库用法。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import jwt as pyjwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet

# ── 凭据加密（Fernet）──────────────────────────────────────────────────


def _derive_fernet_key(secret: str) -> bytes:
    """从 AUTH_SECRET_KEY 派生 Fernet 对称加密密钥。"""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def encrypt_credential(plaintext: str, *, secret: str) -> str:
    """加密凭据（如邮箱密码），返回 Fernet 密文。"""
    f = Fernet(_derive_fernet_key(secret))
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_credential(ciphertext: str, *, secret: str) -> str:
    """解密凭据，返回明文。"""
    f = Fernet(_derive_fernet_key(secret))
    return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")


# ── 密码哈希：Argon2id 主方案 + PBKDF2 存量双验 ────────────────────────

#: OWASP 2025 推荐参数（argon2-cffi 默认值即 v19 参数集，显式写出便于审计）
_ARGON2_HASHER = PasswordHasher()

#: 存量哈希前缀（迁移前 hash_password 的产物）
LEGACY_PBKDF2_PREFIX = "pbkdf2_sha256$"


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _verify_pbkdf2(password: str, password_hash: str) -> bool:
    """存量 PBKDF2 哈希校验（只读，不再产生新哈希）。"""
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


def is_legacy_hash(password_hash: str | None) -> bool:
    """是否存量 PBKDF2 哈希（尚未升级到 argon2）。"""
    return isinstance(password_hash, str) and password_hash.startswith(LEGACY_PBKDF2_PREFIX)


def hash_password(password: str) -> str:
    """Argon2id 哈希。新用户/改密一律走这里。"""
    return _ARGON2_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """双验入口：按哈希格式分派到 argon2 或存量 pbkdf2。

    登录链路在成功后配合 :func:`needs_rehash` 无缝升级存量哈希，
    用户无感知，也不需要任何「改密码才升级」的运营动作。
    """
    if not isinstance(password_hash, str) or not password_hash:
        return False
    if is_legacy_hash(password_hash):
        return _verify_pbkdf2(password, password_hash)
    try:
        return _ARGON2_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str | None) -> bool:
    """该哈希是否应升级：存量 pbkdf2 → True；argon2 参数过时 → True。

    供登录成功路径调用（见 auth_service.login），失败登录不应升级。
    """
    if not isinstance(password_hash, str) or not password_hash:
        return False
    if is_legacy_hash(password_hash):
        return True
    try:
        return _ARGON2_HASHER.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


# ── JWT（PyJWT，算法白名单）───────────────────────────────────────────

#: 算法白名单：decode 显式传入，伪造 header.alg=none / RS256 的令牌直接拒绝
_JWT_ALGORITHMS = ["HS256"]


def create_access_token(payload: dict[str, Any], *, secret: str, expires_in_seconds: int) -> str:
    """签发 HS256 JWT（与旧手写实现的线上格式兼容，存量令牌不失效）。"""
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return pyjwt.encode(body, secret, algorithm="HS256")


def decode_access_token(token: str, *, secret: str) -> dict[str, Any] | None:
    """校验并解码 JWT；任何失败（签名/过期/算法不符/格式坏）返回 None。

    与旧实现语义对齐：``exp`` 必填且必须未过期；返回的 payload 含 iat/exp。
    """
    try:
        return pyjwt.decode(
            token,
            secret,
            algorithms=_JWT_ALGORITHMS,
            options={"require": ["exp"]},
        )
    except pyjwt.PyJWTError:
        return None
