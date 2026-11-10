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
import socket
import time
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
    # LDAP 用户首次登录自动建号（JIT）。
    # 默认开启：LDAP bind 成功 = 身份已验证，再要求管理员预先建号只是多一道人工
    # 门槛，既拦不住真实的越权（认证已经过了），又会让新同事进不来。
    # 关掉后行为退回「白名单模式」：未建号的 LDAP 用户会被拒绝。
    "auto_create_users": True,
    "default_role": "user",       # 自动建号时的默认角色
    "email_domain": "",           # 条目无 mail 属性时补全邮箱用
    "email_auto_configure": False,  # 登录时自动写入邮箱 IMAP/SMTP 凭据
    "imap_host": "",
    "imap_port": 993,
    "smtp_host": "",
    "smtp_port": 465,
}

# 布尔型键（DB 字符串 ↔ bool）
_BOOL_KEYS = {
    "enabled", "start_tls", "auto_create_users", "email_auto_configure",
}
_INT_KEYS = {"port", "imap_port", "smtp_port"}
# 不回显前端的敏感键
_SECRET_KEYS = {"bind_password"}


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
    auto_create_users: bool = True
    default_role: str = "user"
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

        # 地址格式提前校验：等到 _connect 时才由 ldap3 报
        # `port must be an integer`，管理员根本看不出是格式问题。
        _normalize_ldap_url(self.server_url)

    @property
    def search_attributes(self) -> list[str]:
        attrs = [self.attr_username, self.attr_email, self.attr_name]
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
        "auto_create_users": config.auto_create_users,
        "default_role": config.default_role,
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

def _normalize_ldap_url(raw: str) -> str:
    """把管理员填的服务器地址清洗成 ldap3 能吃下的形态。

    ldap3 的 ``Server(url)`` 内部会 ``int(port)``，任何非纯数字的端口都会
    抛 ``port must be an integer`` —— 而这个报错完全看不出是格式问题。
    实测最常见的三种输入：

    - ``ldap://dc.corp.com:389/``  尾部斜杠 → 端口被解析成 ``389/``
    - ``ldap://dc.corp.com:389:389`` 重复端口
    - ``dc.corp.com:389``          缺协议头

    这里统一修成 ``scheme://host:port``，并把明显不合理的形态直接说清楚，
    而不是让 ldap3 抛一句无法定位的错误。
    """
    url = (raw or "").strip()
    if not url:
        raise LdapConfigError("LDAP 配置不完整：服务器地址")

    # 缺协议头时补 ldap://（管理员常只填 host:port）
    if "://" not in url:
        url = "ldap://" + url

    # 去掉尾部斜杠与路径：LDAP 的 Server 不需要路径
    scheme, _, rest = url.partition("://")
    rest = rest.strip().rstrip("/")
    # 去掉误带的路径部分（例如 ldap://host:389/ou=xxx）
    rest = rest.split("/", 1)[0]
    url = f"{scheme.lower()}://{rest}"

    # 校验端口段：host:port 或仅 host
    host_part, sep, port_part = rest.rpartition(":")
    if sep:
        # 处理 host:389:389 这类重复端口：只保留最后一段，前一段并回 host
        if ":" in host_part and not host_part.startswith("["):
            host_only, _, first_port = host_part.rpartition(":")
            if first_port.isdigit() and port_part.isdigit():
                raise LdapConfigError(
                    f"LDAP 服务器地址里的端口重复了：{raw.strip()}。"
                    "请只写一个端口，例如 ldap://dc.corp.com:389"
                )
        if not port_part.isdigit():
            raise LdapConfigError(
                f"LDAP 服务器地址的端口不是数字：{raw.strip()!r}。"
                "正确写法例如 ldap://dc.corp.com:389 或 ldaps://dc.corp.com:636"
                "（不要带尾部斜杠或路径）"
            )
        port_num = int(port_part)
        if not 1 <= port_num <= 65535:
            raise LdapConfigError(
                f"LDAP 端口超出范围：{port_num}（应在 1-65535）"
            )
    return url


def _split_host_port(url: str, default_port: int) -> tuple[str, int]:
    """从 ``scheme://host[:port]`` 取出 (host, port)。"""
    rest = url.split("://", 1)[-1].rstrip("/")
    # IPv6 字面量形如 [::1]:389
    if rest.startswith("["):
        host, _, tail = rest.partition("]")
        host = host.lstrip("[")
        port = tail.lstrip(":")
        return host, int(port) if port.isdigit() else default_port
    if ":" in rest:
        host, _, port = rest.rpartition(":")
        return host, int(port) if port.isdigit() else default_port
    return rest, default_port


def _connect(config: LdapConfig, *, bind: bool = True):
    """建立 LDAP 连接并（可选）以服务账号 bind。返回 connection。"""
    from ldap3 import Connection, Server

    url = _normalize_ldap_url(config.server_url)
    use_ssl = url.lower().startswith("ldaps://")

    # ldap3 的 Server 只解析地址；真正的网络错误在 bind() 时才暴露，
    # 而它默认把原因吞进 socket 异常里，管理员只看到「无法连接」。
    # 这里先自己做一次 TCP 探测，把「解析失败 / 拒绝连接 / 超时」区分开。
    host, port = _split_host_port(url, 636 if use_ssl else 389)
    try:
        with socket.create_connection((host, port), timeout=10):
            pass
    except socket.gaierror as exc:
        raise LdapAuthError(
            f"LDAP 服务器地址无法解析：{host}（{exc}）。请检查主机名拼写或 DNS 配置"
        ) from exc
    except ConnectionRefusedError as exc:
        raise LdapAuthError(
            f"LDAP 服务器拒绝连接：{host}:{port}。"
            f"端口没有服务在监听，或服务端只接受 ldaps（试 {636}）"
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LdapAuthError(
            f"连接 LDAP 服务器超时：{host}:{port}（10 秒内无响应）。"
            f"通常是网络不通或被防火墙拦截，请在容器内执行 "
            f"`timeout 5 bash -c '</dev/tcp/{host}/{port}'` 验证"
        ) from exc
    except OSError as exc:
        raise LdapAuthError(
            f"无法连接 LDAP 服务器 {host}:{port}：{exc}"
        ) from exc

    server = Server(url, use_ssl=use_ssl, connect_timeout=10)

    # ldap3 的 Connection **没有** open() 方法 —— 只有 bind/unbind/start_tls。
    # 早先这里写的是 `if not conn.open()`，必然 AttributeError，又被外层
    # `except Exception` 包成「无法连接 LDAP 服务器」，于是 TCP 明明能通
    # （nc 和 /dev/tcp 都 OK）却永远连不上。连接是在构造 Connection 时按需
    # 建立的，所以这里直接用 bind() 验证：bind=False 时用匿名 bind 探活。
    conn = Connection(
        server,
        user=config.bind_dn if bind else None,
        password=config.bind_password if bind else None,
        auto_bind=False,
        receive_timeout=15,
    )

    if config.start_tls and not use_ssl:
        try:
            if not conn.start_tls():
                raise LdapAuthError(f"STARTTLS 协商失败：{conn.result.get('message')}")
        except LdapAuthError:
            raise
        except Exception as exc:  # noqa: BLE001 -- ldap3 协议异常统一转可读信息
            raise LdapAuthError(f"STARTTLS 协商失败：{exc}") from exc

    # bind 在 ldap3 里是「发 bindRequest + 等响应」，网络中断、超时、
    # 服务端提前断开都会抛异常（LDAPSessionTerminatedByServerError 等），
    # 不捕获的话会一路冒到 test_connection 的兜底分支，报成一句笼统的
    # 「无法连接」—— 而真正原因（超时 / 被服务端断开）就丢了。
    try:
        if bind:
            if not conn.bind():
                raise LdapAuthError(f"服务账号绑定失败：{conn.result.get('message')}")
        else:
            # 不绑定服务账号时也要确认服务真的在说 LDAP：做一次匿名 bind。
            # 很多目录禁止匿名 bind 并返回 invalidCredentials —— 那也证明
            # 服务是活的、协议是对的，因此只把「连不上/协议错」当成失败。
            if not conn.bind():
                result = conn.result or {}
                code = result.get("result")
                # 49 = invalidCredentials（服务在，只是不许匿名）
                if code not in (49,):
                    raise LdapAuthError(
                        f"无法连接 LDAP 服务器 {url}：{result.get('message') or result}"
                    )
    except LdapAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LdapAuthError(
            f"LDAP 绑定过程失败（{host}:{port}）：{exc}。"
            f"若为超时，通常是端口可达但服务端未响应 bind 请求"
        ) from exc
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


def _stage(stage_name: str, ok: bool, started: float, **detail: Any) -> dict[str, Any]:
    """构造一个阶段结果。

    第一个形参刻意叫 ``stage_name`` 而不是 ``name``：阶段细节里本身就有
    ``name`` 这个键（用户的显示名），用 ``name`` 会和它撞参数名。
    """
    return {
        "stage": stage_name,
        "ok": ok,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **{k: v for k, v in detail.items() if v is not None},
    }


def test_connection(
    config: LdapConfig,
    *,
    probe_username: str = "",
    probe_password: str = "",
) -> dict[str, Any]:
    """连接测试：服务可达 → 服务账号可绑定 → 用户过滤器可执行 →（可选）某个用户能登录。

    返回 {ok, message, stages, ...}；不抛异常（错误信息面向管理员展示）。

    分阶段而不是「一次性给个结论」是刻意的：LDAP 配错通常错在四处之一
    （地址/端口、服务账号、搜索基线 DN、过滤器语法），合成一句话会让人
    把四处全改一遍。传了 ``probe_username`` / ``probe_password`` 时再追加
    一步「这个账号能不能真的登录」—— 那是唯一能验证属性映射对不对的检查。
    """
    from ldap3 import SUBTREE

    stages: list[dict[str, Any]] = []

    try:
        config.validate()
    except LdapConfigError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "hint": "先补全服务器地址、绑定账号 DN/密码、用户搜索基线 DN",
            "stages": stages,
        }

    conn = None
    started = time.monotonic()
    try:
        # 直接带服务账号 bind：既验证了「服务可达」，也验证了「凭据可用」。
        # 早先用 bind=False 只是探活，但 ldap3 的 Connection 没有 open()，
        # 那条路径必然 AttributeError，被包成「无法连接」—— 网络明明通的
        # 情况下永远连不上，排查方向全被带偏。
        conn = _connect(config, bind=True)
    except LdapAuthError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "hint": "检查地址与端口（ldaps:// 636 / ldap:// 389）、网络可达性、"
                    "绑定账号 DN 是否写成完整路径、密码是否与该账号一致",
            "stages": [_stage("server", False, started, message=str(exc))],
        }
    except Exception as exc:  # noqa: BLE001 -- 网络/协议错误统一转为可读信息
        logger.warning("LDAP test_connection open failed: %s", exc)
        return {
            "ok": False,
            "message": f"无法连接 LDAP 服务器：{exc}",
            "hint": "检查地址与端口、DNS、以及是否处于可访问该服务器的网络",
            "stages": [_stage("server", False, started, message=str(exc)[:300])],
        }

    tls = config.server_url.lower().startswith("ldaps://") or config.start_tls
    stages.append(_stage("server", True, started, url=config.server_url, tls=tls))

    try:
        # 1) 服务账号绑定 —— _connect(bind=True) 已经完成 bind，
        # 这里不再重复 bind（会多发一次请求，且部分目录会因此重置会话）。
        # 直接把这一步记为通过，服务端凭据已在建连时验证过。
        started = time.monotonic()
        if not getattr(conn, "bound", False):
            if not conn.bind():
                message = f"服务账号绑定失败：{conn.result.get('message') or conn.result}"
                return {
                    "ok": False,
                    "message": message,
                    "hint": "DN 要写完整路径（cn=svc,ou=Service,dc=corp,dc=com），不是登录名；密码需与该账号一致",
                    "tls": tls,
                    "stages": stages + [_stage("bind", False, started, message=message)],
                }
        stages.append(_stage("bind", True, started, dn=config.bind_dn))

        # 2) 用户过滤器（用通配符探测，不暴露任何真实用户）
        started = time.monotonic()
        probe_filter = config.user_filter.replace("{username}", "*")
        if not conn.search(
            search_base=config.base_dn,
            search_filter=probe_filter,
            search_scope=SUBTREE,
            attributes=config.search_attributes,
            size_limit=1,
        ):
            message = f"搜索失败：{conn.result.get('message')}"
            return {
                "ok": False,
                "message": message,
                "hint": "检查用户搜索基线 DN 与用户过滤器语法（必须含 {username}）",
                "tls": tls,
                "stages": stages + [_stage("filter", False, started, message=message)],
            }
        entries = len(conn.entries)
        stages.append(_stage("filter", True, started, sample_entries=entries))

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

        # 3) 可选：真实用户登录（验证属性映射）
        if probe_username.strip() and probe_password:
            started = time.monotonic()
            try:
                profile = authenticate(config, probe_username.strip(), probe_password)
                stages.append(
                    _stage(
                        "user", True, started,
                        username=profile.get("username"),
                        email=profile.get("email"),
                        name=profile.get("name"),
                    )
                )
                return {
                    "ok": True,
                    "message": (
                        f"全部通过：服务账号可绑定、过滤器命中 {entries} 条、"
                        f"账号 {profile.get('username')} 可登录"
                    ),
                    "tls": tls,
                    "server_info": info,
                    "sample_entries": entries,
                    "profile": profile,
                    "stages": stages,
                }
            except Exception as exc:  # noqa: BLE001
                message = f"用户登录验证失败：{exc}"
                return {
                    "ok": False,
                    "message": message,
                    "hint": (
                        "前两步已通过，说明连接与服务账号没问题；"
                        "这里失败通常是用户名格式（要登录名不是邮箱）、密码错，"
                        "或属性映射（用户名/邮箱字段）写错"
                    ),
                    "tls": tls,
                    "server_info": info,
                    "sample_entries": entries,
                    "stages": stages + [_stage("user", False, started, message=str(exc)[:300])],
                }

        return {
            "ok": True,
            "message": f"连接成功，用户过滤器可执行（探测到 {entries} 条样例）",
            "tls": tls,
            "server_info": info,
            "sample_entries": entries,
            "stages": stages,
        }
    except LdapAuthError as exc:
        return {"ok": False, "message": str(exc), "tls": tls, "stages": stages}
    except Exception as exc:  # noqa: BLE001 -- 网络/协议错误统一转为可读信息
        logger.warning("LDAP test_connection failed: %s", exc)
        return {"ok": False, "message": f"连接测试失败：{exc}", "tls": tls, "stages": stages}
    finally:
        if conn is not None:
            _close(conn)


def authenticate(config: LdapConfig, username: str, password: str) -> dict[str, str]:
    """LDAP 认证：服务账号搜索用户 → 用户 DN + 密码二次 bind。

    Returns:
        {"username", "email", "name"}

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

        # 以用户 DN + 明文密码二次 bind 验证密码。
        # 注意：ldap3 的 Connection **没有** open() 方法（只有 bind/unbind/
        # start_tls），早先这里写的 `user_conn.open()` 必然 AttributeError，
        # 被下面 except 兜住后报成「用户登录验证失败」—— 于是测试页前三步
        # 全绿、最后一步永远失败，真实登录也一并失效。
        user_conn = Connection(conn.server, user=user_dn, password=password, auto_bind=False)
        try:
            if not user_conn.bind():
                logger.info("LDAP bind failed for %s: %s", username, user_conn.result.get("message"))
                raise LdapAuthError("用户名或密码错误")
        except LdapAuthError:
            raise
        except Exception as exc:  # noqa: BLE001 -- 网络/协议异常转可读信息
            raise LdapAuthError(f"LDAP 用户绑定过程失败：{exc}") from exc
        finally:
            _close(user_conn)
    finally:
        _close(conn)

    # 归一化用户信息
    email = _first(entry, config.attr_email)
    if not email and config.email_domain:
        email = f"{username}@{config.email_domain.lstrip('@')}"
    name = _first(entry, config.attr_name) or username

    return {
        "username": username,
        "email": email or username,
        "name": name,
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
