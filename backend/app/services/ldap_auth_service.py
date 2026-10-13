"""通用 LDAP 认证服务（协议级实现，基于 ldap3）。

与旧版（HTTP 网关 ``/v2/ldap/auth``）的区别：
- 直连 LDAP/AD 服务器（LDAP v3 协议），不依赖任何内部网关；
- 服务器地址、绑定账号、用户过滤器、属性映射全部在管理后台
  「系统设置 → LDAP」配置（``system_settings`` 表 ``ldap.*`` 键），
  绑定密码加密存储，支持一键连接测试；
- 认证方式：服务账号搜索用户 DN → 以用户 DN + 密码二次 bind 验证；
- 部门同步：直接读取用户条目上可配置的部门属性，不再猜网关字段。

首次部署可用 ``LDAP_ENABLED`` 环境变量引导开关；完整配置以数据库为准。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decrypt_credential, encrypt_credential
from app.db.models import SystemSettingModel, UserEmailCredentialsModel

logger = logging.getLogger("agenticos.ldap")

# system_settings 中 LDAP 配置的键前缀
KEY_PREFIX = "ldap."

# 各配置项的默认值
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "server_url": "",             # 形如 ldap://dc.corp.com:389 / ldaps://dc.corp.com:636
    "start_tls": False,           # 普通连接上升级 TLS（ldap:// + STARTTLS）
    "bind_dn": "",                # 服务账号 DN，如 cn=svc,dc=corp,dc=com
    "bind_password": "",          # 加密存储
    "base_dn": "",                # 用户搜索基线，如 dc=corp,dc=com
    "user_filter": "(sAMAccountName={username})",  # {username} 占位符，自动转义
    "attr_username": "sAMAccountName",
    "attr_email": "mail",
    "attr_name": "displayName",
    "attr_department": "department",
    "auto_create_users": False,   # LDAP 用户首次登录自动建号
    "default_role": "user",       # 自动建号时的默认角色
    "department_sync": False,     # 登录时同步本人部门
    "email_domain": "",           # 条目无 mail 属性时补全邮箱用
    "email_auto_configure": False,  # 登录时自动写入邮箱 IMAP/SMTP 凭据
    "imap_host": "",
    "imap_port": 993,
    "smtp_host": "",
    "smtp_port": 465,
}

# 布尔型键（DB 字符串 ↔ bool）
_BOOL_KEYS = {
    "enabled", "start_tls", "auto_create_users",
    "department_sync", "email_auto_configure",
}
_INT_KEYS = {"imap_port", "smtp_port"}
# 不回显前端的敏感键
_SECRET_KEYS = {"bind_password"}
# 取值为 DN 而非名称的部门属性（AD 常见）
_DN_VALUED_ATTRS = {"dn", "distinguishedname", "distinguishedname;"}


class LdapConfigError(Exception):
    """LDAP 配置不完整或非法（管理员需要修正配置）。"""


class LdapAuthError(Exception):
    """LDAP 认证失败（用户不存在 / 密码错误 / 服务器不可达）。"""


@dataclass
class LdapConfig:
    """LDAP 连接配置（已解密，供服务内部使用）。"""

    enabled: bool = False
    server_url: str = ""
    start_tls: bool = False
    bind_dn: str = ""
    bind_password: str = ""
    base_dn: str = ""
    user_filter: str = DEFAULTS["user_filter"]
    attr_username: str = "sAMAccountName"
    attr_email: str = "mail"
    attr_name: str = "displayName"
    attr_department: str = "department"
    auto_create_users: bool = False
    default_role: str = "user"
    department_sync: bool = False
    email_domain: str = ""
    email_auto_configure: bool = False
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465

    # -- 校验 -------------------------------------------------------------
    def validate(self) -> None:
        """配置完整性校验；不合法时抛 LdapConfigError（消息面向管理员）。"""
        missing: list[str] = []
        if not self.server_url.strip():
            missing.append("服务器地址")
        if not self.bind_dn.strip():
            missing.append("绑定账号 DN")
        if not self.base_dn.strip():
            missing.append("用户搜索基线 DN")
        if not self.bind_password:
            missing.append("绑定账号密码")
        if "{username}" not in self.user_filter:
            missing.append("用户过滤器（必须包含 {username} 占位符）")
        if missing:
            raise LdapConfigError("LDAP 配置不完整：" + "、".join(missing))

    @property
    def search_attributes(self) -> list[str]:
        attrs = [self.attr_username, self.attr_email, self.attr_name, self.attr_department]
        return [a for a in attrs if a]


# ---------------------------------------------------------------------------
# 配置读写（system_settings 表，键前缀 ldap.）
# ---------------------------------------------------------------------------

def _coerce(key: str, raw: str) -> Any:
    if key in _BOOL_KEYS:
        return raw.strip().lower() in ("true", "1", "yes")
    if key in _INT_KEYS:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULTS[key]
    return raw


def _secret(settings: Settings | None) -> str:
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    return settings.auth_secret_key


def load_config(db: Session, settings: Settings | None = None) -> LdapConfig:
    """从数据库加载 LDAP 配置；无记录时用默认值 + 环境变量引导开关。"""
    rows = db.scalars(
        select(SystemSettingModel).where(SystemSettingModel.key.like(f"{KEY_PREFIX}%"))
    ).all()
    stored = {row.key[len(KEY_PREFIX):]: row.value for row in rows}

    values: dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        values[key] = _coerce(key, stored[key]) if key in stored else default

    # 环境变量引导：数据库从未配置过开关时，回退到 LDAP_ENABLED
    if "enabled" not in stored and settings is not None:
        values["enabled"] = bool(settings.ldap_enabled)

    # 绑定密码解密（加密存储，明文只在内存中短暂存在）
    if values.get("bind_password"):
        try:
            values["bind_password"] = decrypt_credential(
                values["bind_password"], secret=_secret(settings)
            )
        except Exception:  # noqa: BLE001 -- 密钥轮换后旧密文解不开时按未配置处理
            logger.warning("LDAP bind password decrypt failed (secret rotated?); treating as unset")
            values["bind_password"] = ""

    return LdapConfig(**values)


def save_config(db: Session, payload: dict[str, Any], settings: Settings | None = None) -> LdapConfig:
    """保存管理员提交的配置（绑定密码加密后入库）。"""
    secret = _secret(settings)
    for key, value in payload.items():
        if key not in DEFAULTS:
            continue  # 忽略未知键，防止把任意数据写进 settings 表
        if key in _BOOL_KEYS:
            db_value = "true" if value else "false"
        elif key in _SECRET_KEYS:
            # 空字符串表示“不修改”；非空则加密后存储
            if not str(value).strip():
                continue
            db_value = encrypt_credential(str(value), secret=secret)
        else:
            db_value = str(value)
        full_key = f"{KEY_PREFIX}{key}"
        row = db.scalar(select(SystemSettingModel).where(SystemSettingModel.key == full_key))
        if row is None:
            db.add(SystemSettingModel(key=full_key, value=db_value))
        else:
            row.value = db_value
    db.commit()
    return load_config(db, settings)


def config_to_response(config: LdapConfig) -> dict[str, Any]:
    """序列化为可安全返回前端的配置（密码只返回是否已设置）。"""
    return {
        "enabled": config.enabled,
        "server_url": config.server_url,
        "start_tls": config.start_tls,
        "bind_dn": config.bind_dn,
        "bind_password_set": bool(config.bind_password),
        "base_dn": config.base_dn,
        "user_filter": config.user_filter,
        "attr_username": config.attr_username,
        "attr_email": config.attr_email,
        "attr_name": config.attr_name,
        "attr_department": config.attr_department,
        "auto_create_users": config.auto_create_users,
        "default_role": config.default_role,
        "department_sync": config.department_sync,
        "email_domain": config.email_domain,
        "email_auto_configure": config.email_auto_configure,
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
    }


# ---------------------------------------------------------------------------
# LDAP 协议操作（ldap3，同步 API —— 调用方需放在线程池中执行）
# ---------------------------------------------------------------------------

def _connect(config: LdapConfig, *, bind: bool = True):
    """建立 LDAP 连接并（可选）以服务账号 bind。返回 connection。"""
    from ldap3 import Connection, Server

    url = config.server_url.strip()
    use_ssl = url.lower().startswith("ldaps://")
    server = Server(url, use_ssl=use_ssl, connect_timeout=10)

    conn = Connection(
        server,
        user=config.bind_dn if bind else None,
        password=config.bind_password if bind else None,
        auto_bind=False,
        receive_timeout=15,
    )
    if not conn.open():
        raise LdapAuthError(f"无法连接 LDAP 服务器 {url}")
    if config.start_tls and not use_ssl:
        if not conn.start_tls():
            raise LdapAuthError(f"STARTTLS 协商失败：{conn.result.get('message')}")
    if bind and not conn.bind():
        raise LdapAuthError(f"服务账号绑定失败：{conn.result.get('message')}")
    return conn


def _close(conn: Any) -> None:
    try:
        conn.unbind()
    except Exception:  # noqa: BLE001 -- 关闭连接的异常无实质影响
        pass


def _first(entry: Any, attr: str) -> str | None:
    """从 ldap3 条目取单值属性（多值取第一个；不存在返回 None）。"""
    if not attr:
        return None
    try:
        value = entry[attr].value
    except Exception:  # noqa: BLE001 -- 属性不存在时 ldap3 抛 LDAPKeyError
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def test_connection(config: LdapConfig) -> dict[str, Any]:
    """连接测试：bind 服务账号 + 探测用户过滤器可用性。

    返回 {ok, message, ...}；不抛异常（错误信息面向管理员展示）。
    """
    from ldap3 import SUBTREE

    try:
        config.validate()
    except LdapConfigError as exc:
        return {"ok": False, "message": str(exc)}

    conn = None
    try:
        conn = _connect(config)
        # 用通配符探测用户过滤器是否可执行（不暴露任何真实用户）
        probe_filter = config.user_filter.replace("{username}", "*")
        if not conn.search(
            search_base=config.base_dn,
            search_filter=probe_filter,
            search_scope=SUBTREE,
            attributes=config.search_attributes,
            size_limit=1,
        ):
            return {
                "ok": False,
                "message": f"搜索失败：{conn.result.get('message')}",
                "hint": "请检查用户搜索基线 DN 与用户过滤器语法",
            }
        entries = len(conn.entries)
        # 服务端信息（厂商/版本，便于识别 AD / OpenLDAP）
        info: dict[str, Any] = {}
        try:
            vendor = getattr(conn.server, "info", None)
            if vendor is not None and getattr(vendor, "vendor_name", None):
                info["vendor"] = str(vendor.vendor_name)
                if getattr(vendor, "version", None):
                    info["version"] = str(vendor.version)
        except Exception:  # noqa: BLE001 -- 服务端信息缺失不影响测试结论
            pass
        return {
            "ok": True,
            "message": f"连接成功，用户过滤器可执行（探测到 {entries} 条样例）",
            "tls": config.server_url.lower().startswith("ldaps://") or config.start_tls,
            "server_info": info,
            "sample_entries": entries,
        }
    except LdapAuthError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- 网络/协议错误统一转为可读信息
        logger.warning("LDAP test_connection failed: %s", exc)
        return {"ok": False, "message": f"连接测试失败：{exc}"}
    finally:
        if conn is not None:
            _close(conn)


def authenticate(config: LdapConfig, username: str, password: str) -> dict[str, str]:
    """LDAP 认证：服务账号搜索用户 → 用户 DN + 密码二次 bind。

    Returns:
        {"username", "email", "name", "department_dn", "department_name"}

    Raises:
        LdapAuthError: 用户不存在 / 密码错误 / 服务器不可达。
    """
    from ldap3 import SUBTREE, Connection
    from ldap3.utils.conv import escape_filter_chars

    if not username or not password:
        raise LdapAuthError("用户名或密码为空")

    config.validate()

    # 服务账号连接 + 搜索用户 DN
    try:
        conn = _connect(config)
    except LdapAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LdapAuthError(f"LDAP 服务器连接失败：{exc}") from exc

    try:
        search_filter = config.user_filter.replace("{username}", escape_filter_chars(username))
        if not conn.search(
            search_base=config.base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=config.search_attributes,
            size_limit=2,  # >1 说明过滤器不唯一，拒绝认证
        ):
            raise LdapAuthError(f"LDAP 搜索失败：{conn.result.get('message')}")
        if len(conn.entries) == 0:
            raise LdapAuthError("LDAP 用户不存在，请检查用户名")
        if len(conn.entries) > 1:
            raise LdapAuthError("LDAP 用户过滤器匹配到多条记录，请联系管理员检查配置")

        entry = conn.entries[0]
        user_dn = entry.entry_dn

        # 以用户 DN + 明文密码二次 bind 验证密码
        user_conn = Connection(conn.server, user=user_dn, password=password, auto_bind=False)
        try:
            if not user_conn.open():
                raise LdapAuthError("LDAP 服务器连接失败")
            if not user_conn.bind():
                logger.info("LDAP bind failed for %s: %s", username, user_conn.result.get("message"))
                raise LdapAuthError("用户名或密码错误")
        finally:
            _close(user_conn)
    finally:
        _close(conn)

    # 归一化用户信息
    email = _first(entry, config.attr_email)
    if not email and config.email_domain:
        email = f"{username}@{config.email_domain.lstrip('@')}"
    name = _first(entry, config.attr_name) or username

    # 部门属性：普通属性取值为部门名；DN 型属性（dn / distinguishedName）同时作为 ldap_dn
    dept_raw = _first(entry, config.attr_department) or ""
    dept_dn = ""
    dept_name = dept_raw
    if config.attr_department.strip().lower() in _DN_VALUED_ATTRS and dept_raw:
        dept_dn = dept_raw
        dept_name = dept_raw.split(",")[0].split("=")[-1] if "=" in dept_raw else dept_raw

    return {
        "username": username,
        "email": email or username,
        "name": name,
        "department_dn": dept_dn,
        "department_name": dept_name,
    }


def lookup_user(config: LdapConfig, username: str) -> dict[str, str] | None:
    """服务账号仅搜索（不验证密码）：返回与 authenticate 相同结构的用户信息。

    供管理员触发的全量部门同步使用——该场景拿不到用户明文密码，
    无法走"用户 DN 二次 bind"的认证路径。用户不存在时返回 None。
    """
    from ldap3 import SUBTREE
    from ldap3.utils.conv import escape_filter_chars

    config.validate()

    try:
        conn = _connect(config)
    except Exception as exc:  # noqa: BLE001
        raise LdapAuthError(f"LDAP 服务器连接失败：{exc}") from exc

    try:
        search_filter = config.user_filter.replace("{username}", escape_filter_chars(username))
        if not conn.search(
            search_base=config.base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=config.search_attributes,
            size_limit=1,
        ):
            raise LdapAuthError(f"LDAP 搜索失败：{conn.result.get('message')}")
        if not conn.entries:
            return None
        entry = conn.entries[0]
    finally:
        _close(conn)

    email = _first(entry, config.attr_email)
    if not email and config.email_domain:
        email = f"{username}@{config.email_domain.lstrip('@')}"
    name = _first(entry, config.attr_name) or username

    dept_raw = _first(entry, config.attr_department) or ""
    dept_dn = ""
    dept_name = dept_raw
    if config.attr_department.strip().lower() in _DN_VALUED_ATTRS and dept_raw:
        dept_dn = dept_raw
        dept_name = dept_raw.split(",")[0].split("=")[-1] if "=" in dept_raw else dept_raw

    return {
        "username": username,
        "email": email or username,
        "name": name,
        "department_dn": dept_dn,
        "department_name": dept_name,
    }


# ---------------------------------------------------------------------------
# 登录后的本地副作用：邮箱自动配置 + 部门同步
# ---------------------------------------------------------------------------

def _write_email_credentials(
    config: LdapConfig,
    db: Session,
    user_id: int,
    email_address: str,
    password: str,
) -> None:
    """写入/更新用户的邮箱 IMAP/SMTP 凭据（密码加密存储）。"""
    encrypted_pw = encrypt_credential(password, secret=_secret(None))
    existing = db.scalar(
        select(UserEmailCredentialsModel).where(UserEmailCredentialsModel.user_id == user_id)
    )
    if existing:
        existing.email_address = email_address
        existing.password = ""
        existing.password_encrypted = encrypted_pw
        existing.imap_host = config.imap_host
        existing.imap_port = config.imap_port
        existing.imap_ssl = True
        existing.smtp_host = config.smtp_host
        existing.smtp_port = config.smtp_port
        existing.smtp_ssl = True
    else:
        db.add(
            UserEmailCredentialsModel(
                user_id=user_id,
                email_address=email_address,
                password="",
                password_encrypted=encrypted_pw,
                imap_host=config.imap_host,
                imap_port=config.imap_port,
                imap_ssl=True,
                smtp_host=config.smtp_host,
                smtp_port=config.smtp_port,
                smtp_ssl=True,
            )
        )
    db.commit()
    logger.info("Auto-configured email credentials for user %d (%s)", user_id, email_address)


def apply_department(
    db: Session,
    user: Any,
    department_dn: str | None,
    department_name: str | None,
) -> bool:
    """把 LDAP 部门信息应用到用户（按 ldap_dn 匹配已有部门，否则按名创建）。

    同步路径（不依赖网络），供登录同步与后续全量同步共用。
    """
    from app.db.models import DepartmentModel
    from app.services.department_service import (
        DepartmentError,
        assign_user_department,
        create_department,
        get_department_by_name,
    )

    dn = (department_dn or "").strip() or None
    name = (department_name or "").strip() or None
    if not dn and not name:
        return False

    dept: DepartmentModel | None = None
    if dn:
        dept = db.scalar(select(DepartmentModel).where(DepartmentModel.ldap_dn == dn))
    if dept is None and name:
        dept = get_department_by_name(db, name)
        if dept is not None and not dept.ldap_dn:
            dept.ldap_dn = dn
            db.add(dept)

    if dept is None:
        if not name:
            logger.info("LDAP department DN %s has no local counterpart and no name; skipped", dn)
            return False
        try:
            dept = create_department(db, name=name, ldap_dn=dn)
            logger.info("Auto-created department %s from LDAP (dn=%s)", dept.name, dn)
        except DepartmentError:
            return False

    if user.department_id == dept.id:
        return False

    assign_user_department(db, user, dept.id)
    logger.info("Synced user %s into department %s", user.id, dept.name)
    return True


# ---------------------------------------------------------------------------
# 兼容层：auth.py 登录路径使用的薄封装
# ---------------------------------------------------------------------------

class LdapAuthService:
    """auth.py 登录路径的入口：DB 配置 → LDAP 认证 → 本地副作用。"""

    def __init__(self, settings: Settings, db: Session) -> None:
        self.settings = settings
        self.db = db
        self.config = load_config(db, settings)

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    async def authenticate(self, username: str, password: str) -> dict[str, str]:
        """异步认证（ldap3 为同步 API，放线程池避免阻塞事件循环）。"""
        import asyncio

        return await asyncio.to_thread(authenticate, self.config, username, password)

    def sync_department(self, user: Any, ldap_user: dict[str, str]) -> bool:
        """登录时同步本人部门（未开启时跳过）。失败不阻断登录。"""
        if not self.config.department_sync:
            return False
        try:
            return apply_department(
                self.db, user,
                ldap_user.get("department_dn"),
                ldap_user.get("department_name"),
            )
        except Exception:  # noqa: BLE001 -- 部门同步失败不阻断登录
            logger.warning("department sync failed for user %s", user.id, exc_info=True)
            return False

    def configure_email(self, user_id: int, ldap_user: dict[str, str], password: str) -> None:
        """登录时自动配置邮箱凭据（未开启时跳过）。失败不阻断登录。"""
        if not self.config.email_auto_configure:
            return
        email = ldap_user.get("email") or ""
        if not email or not self.config.imap_host or not self.config.smtp_host:
            return
        try:
            _write_email_credentials(self.config, self.db, user_id, email, password)
        except Exception:  # noqa: BLE001 -- 邮箱配置失败不阻断登录
            logger.warning("email auto-configure failed for user %s", user_id, exc_info=True)
