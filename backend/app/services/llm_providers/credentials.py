"""企业网关提供商的账号池与登录态管理。

四个不变量，改这个文件时必须守住：

1. **密码与 Cookie 只以密文落库**，任何返回给上层的结构都不含明文；
2. **过期判定不信任 ``status``**：``status=active`` 只是「上次登录成功」的
   记录，真正能不能用要同时看过期时间。只查 status 会让 Cookie 过期后仍被
   当作可用，每次请求都在上游撞 401 再触发重登；
3. **账号池是系统级资源**（不按终端用户存），但**一个提供商下可以有多条**：
   企业网关普遍按账号限配额，全压在一个号上会被限流甚至锁定；
4. **坏号必须能自动退出轮换**：连续失败达到阈值后不再被选中，否则「选号
   策略」会把流量持续导向一个已经挂掉的账号，表现为「大部分对话都失败」。

选号策略是 ``priority`` 升序 + ``last_used_at`` 最久未用优先。前者给运维
留出「主力号/备用号」的表达能力，后者让配额在池内均匀摊开。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import decrypt_safe, encrypt
from app.core.timezone import app_now
from app.db.models import LlmProviderCredentialModel
from app.db.session import create_db_session
from app.services.llm_providers.spec import invalidate_cache

logger = logging.getLogger("agenticos.llm.credentials")

STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_FAILED = "failed"

# 连续失败多少次后把该账号移出候选池
MAX_CONSECUTIVE_FAILURES = 3


@dataclass
class AccountLease:
    """一次「借出一个账号」的结果。

    带上 ``credential_id`` 是必须的：多账号池里，401 之后要知道**是谁**挂了，
    只拿到 provider_id 会把整个池子标记成失效。
    """

    credential_id: int
    cookie: str
    label: str


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def _first_account(db: Session, provider_id: int) -> LlmProviderCredentialModel | None:
    """默认账号 = priority 最小、id 最小的一条。"""
    return db.scalar(
        select(LlmProviderCredentialModel)
        .where(LlmProviderCredentialModel.provider_id == provider_id)
        .order_by(LlmProviderCredentialModel.priority, LlmProviderCredentialModel.id)
        .limit(1)
    )


def get_credential(db: Session, provider_id: int) -> LlmProviderCredentialModel | None:
    """取默认账号。保留单条语义是为了兼容既有调用方（编辑凭据、状态展示）。"""
    return _first_account(db, provider_id)


def list_credentials(db: Session, provider_id: int) -> list[LlmProviderCredentialModel]:
    return list(
        db.scalars(
            select(LlmProviderCredentialModel)
            .where(LlmProviderCredentialModel.provider_id == provider_id)
            .order_by(LlmProviderCredentialModel.priority, LlmProviderCredentialModel.id)
        ).all()
    )


def get_by_id(db: Session, credential_id: int) -> LlmProviderCredentialModel | None:
    return db.get(LlmProviderCredentialModel, credential_id)


def ensure_credential(db: Session, provider_id: int) -> LlmProviderCredentialModel:
    row = _first_account(db, provider_id)
    if row is None:
        row = LlmProviderCredentialModel(
            provider_id=provider_id,
            label="",
            username="",
            password_encrypted="",
            cookie_encrypted="",
            login_url=None,
            status=STATUS_PENDING,
            auto_refresh=True,
            priority=100,
            failure_count=0,
            disabled=False,
        )
        db.add(row)
        db.flush()
    return row


def add_account(
    db: Session,
    provider_id: int,
    *,
    label: str = "",
    username: str = "",
    password: str | None = None,
    login_url: str | None = None,
    priority: int = 100,
) -> LlmProviderCredentialModel:
    """新增一个账号。用于「一个企业网关下挂多个账号分摊配额」。"""
    row = LlmProviderCredentialModel(
        provider_id=provider_id,
        label=(label or "").strip(),
        username=(username or "").strip(),
        password_encrypted=encrypt(password) if password else "",
        cookie_encrypted="",
        login_url=(login_url or "").strip() or None,
        status=STATUS_PENDING,
        auto_refresh=True,
        priority=max(1, int(priority or 100)),
        failure_count=0,
        disabled=False,
    )
    db.add(row)
    db.flush()
    invalidate_cache()
    return row


def delete_account(db: Session, credential_id: int) -> bool:
    row = db.get(LlmProviderCredentialModel, credential_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    invalidate_cache()
    return True


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------


def save_credentials(
    db: Session,
    provider_id: int,
    *,
    username: str,
    password: str | None = None,
    login_url: str | None = None,
    auto_refresh: bool | None = None,
    credential_id: int | None = None,
    label: str | None = None,
    priority: int | None = None,
) -> LlmProviderCredentialModel:
    """写入账号密码。

    ``password`` 为 ``None`` 或空串表示**保持原密码**（前端编辑不回显密码，
    不能一保存就把密码清空）。要清空请走 ``clear_credentials``。

    ``credential_id`` 省略时写默认账号 —— 单账号场景的所有既有调用方不受影响。
    """
    row = get_by_id(db, credential_id) if credential_id else _first_account(db, provider_id)
    if row is None:
        row = ensure_credential(db, provider_id)
    row.username = (username or "").strip()
    if label is not None:
        row.label = (label or "").strip()
    if priority is not None:
        row.priority = max(1, int(priority))
    if password:
        row.password_encrypted = encrypt(password)
    if login_url is not None:
        row.login_url = (login_url or "").strip() or None
    if auto_refresh is not None:
        row.auto_refresh = bool(auto_refresh)
    # 改了账号密码，之前那份 Cookie 就作废了：它承载的是旧身份
    if password:
        row.cookie_encrypted = ""
        row.status = STATUS_PENDING
        row.expire_at = None
        row.last_error = None
        row.failure_count = 0
    db.flush()
    invalidate_cache()
    return row


def clear_credentials(db: Session, provider_id: int, *, credential_id: int | None = None) -> LlmProviderCredentialModel:
    row = get_by_id(db, credential_id) if credential_id else _first_account(db, provider_id)
    if row is None:
        row = ensure_credential(db, provider_id)
    row.username = ""
    row.password_encrypted = ""
    row.cookie_encrypted = ""
    row.status = STATUS_PENDING
    row.expire_at = None
    row.last_error = None
    row.failure_count = 0
    db.flush()
    invalidate_cache()
    return row


def default_cookie_expire_at() -> datetime:
    """没有可解析过期时间时的保守估计。

    上游未必在 Cookie 上给出可信的 exp；按「宁可早刷新」的思路，给一个偏短
    的默认值，让定时任务在真正失效前先换一次。
    """
    return app_now() + timedelta(hours=get_settings().llm_provider_cookie_default_ttl_hours)


def save_manual_cookie(
    db: Session,
    provider_id: int,
    *,
    cookie: str,
    expire_at: datetime | None = None,
    credential_id: int | None = None,
) -> LlmProviderCredentialModel:
    """手动粘贴 Cookie 兜底。

    自动登录失效（上游改版、验证码、SSO 多次跳转）时，管理员可以从浏览器
    复制 Cookie 直接填进来，不必等修好 Playwright 脚本。
    """
    normalized = (cookie or "").strip()
    if not normalized:
        raise ValueError("Cookie 不能为空")
    if "=" not in normalized:
        raise ValueError("Cookie 格式不正确，应形如 name=value; name2=value2")

    row = get_by_id(db, credential_id) if credential_id else _first_account(db, provider_id)
    if row is None:
        row = ensure_credential(db, provider_id)
    row.cookie_encrypted = encrypt(normalized)
    row.status = STATUS_ACTIVE
    row.expire_at = expire_at or default_cookie_expire_at()
    row.last_login_at = app_now()
    row.last_error = None
    row.failure_count = 0
    db.flush()
    invalidate_cache()
    return row


def apply_login_result(
    credential_id: int,
    *,
    success: bool,
    cookie: str | None = None,
    expire_at: datetime | None = None,
    error: str | None = None,
) -> None:
    """把自动登录结果写回。独立开 session —— 调用方通常在请求作用域之外。"""
    now = app_now()
    with create_db_session() as db:
        row = db.get(LlmProviderCredentialModel, credential_id)
        if row is None:
            return
        if success and cookie:
            row.cookie_encrypted = encrypt(cookie)
            row.status = STATUS_ACTIVE
            row.expire_at = expire_at or default_cookie_expire_at()
            row.last_login_at = now
            row.last_error = None
            row.failure_count = 0
        else:
            # 之前成功过就标 expired，从未成功过就标 failed —— 两者排查方向不同
            row.status = STATUS_EXPIRED if row.status == STATUS_ACTIVE else STATUS_FAILED
            row.last_error = (error or "自动登录失败")[:500]
            row.last_login_at = now
            row.failure_count = min(row.failure_count + 1, 99)
        db.commit()
    invalidate_cache()


def mark_cookie_invalid(credential_id: int, reason: str) -> None:
    """上游返回 401/403 时标记该账号失效，避免继续拿废 Cookie 反复请求。

    连续失败累计到阈值后，账号自动退出轮换（``failure_count >= 阈值``），
    但要保留数据 —— 运维可能只是临时网络问题，恢复后重置计数即可复活。
    """
    with create_db_session() as db:
        row = db.get(LlmProviderCredentialModel, credential_id)
        if row is None:
            return
        row.failure_count = min(row.failure_count + 1, 99)
        if row.failure_count >= MAX_CONSECUTIVE_FAILURES:
            row.status = STATUS_EXPIRED
        row.last_error = (reason or "上游返回未授权")[:500]
        db.commit()
    invalidate_cache()


# ---------------------------------------------------------------------------
# 选号
# ---------------------------------------------------------------------------


def _usable():
    return (
        LlmProviderCredentialModel.status == STATUS_ACTIVE,
        LlmProviderCredentialModel.disabled.is_(False),
        LlmProviderCredentialModel.failure_count < MAX_CONSECUTIVE_FAILURES,
        LlmProviderCredentialModel.cookie_encrypted != "",
    )


def acquire(provider_id: int) -> AccountLease | None:
    """借出一个可用账号，并推进它的 ``last_used_at``。

    独立开 session：调用点在「构建 LLM」的热路径上，手上没有 db session。
    并发下两个请求可能选到同一个号 —— 这里不做锁，因为选号的目的是摊配额
    而不是严格互斥，多写一次 ``last_used_at`` 的代价远小于加锁。
    """
    if not provider_id:
        return None
    now = app_now()
    try:
        with create_db_session() as db:
            row = db.scalar(
                select(LlmProviderCredentialModel)
                .where(
                    LlmProviderCredentialModel.provider_id == provider_id,
                    *_usable(),
                    (LlmProviderCredentialModel.expire_at.is_(None))
                    | (LlmProviderCredentialModel.expire_at > now),
                )
                .order_by(
                    # 跨方言的 NULLS FIRST：MySQL 不支持该语法，用 CASE 表达。
                    # 排序意图是「最久未用优先」，priority 只在「都没用过」时
                    # 决定首次挑谁 —— 企业网关多开账号的目的是摊配额，如果让
                    # priority 一路压过 last_used_at，备用号就永远不会被用到。
                    case((LlmProviderCredentialModel.last_used_at.is_(None), 0), else_=1),
                    LlmProviderCredentialModel.last_used_at,
                    LlmProviderCredentialModel.priority,
                    LlmProviderCredentialModel.id,
                )
                .limit(1)
            )
            if row is None:
                return None
            cookie = decrypt_safe(row.cookie_encrypted or "", default="")
            if not cookie:
                return None
            row.last_used_at = now
            lease = AccountLease(
                credential_id=row.id,
                cookie=cookie,
                label=row.label or row.username or f"#{row.id}",
            )
            db.commit()
            return lease
    except Exception as exc:  # noqa: BLE001 —— 选号失败不应让对话 500
        logger.warning("选取账号失败 provider=%s: %s", provider_id, exc)
        return None


def get_active_cookie(provider_id: int) -> str | None:
    """只读地取一个可用 Cookie（不推进 ``last_used_at``）。

    与 ``acquire`` 的区别是**没有副作用**，供状态展示与测试使用。
    """
    if not provider_id:
        return None
    now = app_now()
    try:
        with create_db_session() as db:
            row = db.scalar(
                select(LlmProviderCredentialModel)
                .where(
                    LlmProviderCredentialModel.provider_id == provider_id,
                    *_usable(),
                    (LlmProviderCredentialModel.expire_at.is_(None))
                    | (LlmProviderCredentialModel.expire_at > now),
                )
                .order_by(LlmProviderCredentialModel.priority, LlmProviderCredentialModel.id)
                .limit(1)
            )
            if row is None:
                return None
            return decrypt_safe(row.cookie_encrypted or "", default="") or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取提供商 Cookie 失败 provider=%s: %s", provider_id, exc)
        return None


def read_login_material(
    provider_id: int, credential_id: int | None = None
) -> dict[str, Any] | None:
    """读取自动登录所需的账号密码（明文只在内存里短暂存在）。

    不指定账号时选「有账号密码」里的第一条 —— 未登录成功过、或已过期的那条
    优先，这样「池里有 3 个号、只有 1 个挂了」时点一次登录修的是挂掉的那个。
    """
    with create_db_session() as db:
        row = db.get(LlmProviderCredentialModel, credential_id) if credential_id else None
        if row is None:
            row = db.scalar(
                select(LlmProviderCredentialModel)
                .where(
                    LlmProviderCredentialModel.provider_id == provider_id,
                    LlmProviderCredentialModel.password_encrypted != "",
                )
                .order_by(
                    LlmProviderCredentialModel.status != STATUS_ACTIVE,
                    LlmProviderCredentialModel.priority,
                    LlmProviderCredentialModel.id,
                )
                .limit(1)
            )
        if row is None:
            return None
        password = decrypt_safe(row.password_encrypted or "", default="")
        if not row.username or not password:
            return None
        return {
            "credential_id": row.id,
            "username": row.username,
            "password": password,
            "login_url": row.login_url,
            "auto_refresh": bool(row.auto_refresh),
        }


def needs_refresh(provider_id: int) -> bool:
    """定时任务用：判断这个提供商是否有账号该提前换新。"""
    buffer = timedelta(hours=get_settings().llm_provider_cookie_refresh_buffer_hours)
    with create_db_session() as db:
        rows = list(
            db.scalars(
                select(LlmProviderCredentialModel).where(
                    LlmProviderCredentialModel.provider_id == provider_id
                )
            ).all()
        )
    for row in rows:
        if not row.auto_refresh or row.disabled:
            continue
        if not row.password_encrypted:
            # 没有账号密码就没有登录的原料，跳过而不是每 20 分钟失败一次
            continue
        if not row.cookie_encrypted or row.status != STATUS_ACTIVE:
            return True
        if row.expire_at is not None and row.expire_at - buffer <= app_now():
            return True
    return False


def list_refresh_candidates() -> list[tuple[int, int]]:
    """返回 ``[(provider_id, credential_id)]``，供定时任务逐个续期。

    逐个而不是按提供商：一个池里可能只有某个号过期了，全池重登会浪费掉
    其它号当前完全有效的登录态。
    """
    buffer = timedelta(hours=get_settings().llm_provider_cookie_refresh_buffer_hours)
    now = app_now()
    with create_db_session() as db:
        rows = list(
            db.scalars(
                select(LlmProviderCredentialModel).where(
                    LlmProviderCredentialModel.auto_refresh.is_(True),
                    LlmProviderCredentialModel.disabled.is_(False),
                    LlmProviderCredentialModel.password_encrypted != "",
                )
            ).all()
        )
    result: list[tuple[int, int]] = []
    for row in rows:
        if not row.cookie_encrypted or row.status != STATUS_ACTIVE:
            result.append((row.provider_id, row.id))
        elif row.expire_at is not None and row.expire_at - buffer <= now:
            result.append((row.provider_id, row.id))
    return result


def credential_summary(provider_id: int) -> dict[str, Any]:
    """服务层内部用的精简状态（端点侧请用 spec.credential_status_dict）。"""
    with create_db_session() as db:
        rows = list_credentials(db, provider_id)
        if not rows:
            return {"exists": False, "status": STATUS_PENDING, "account_count": 0}
        active = [row for row in rows if row.status == STATUS_ACTIVE and not row.disabled]
        return {
            "exists": True,
            "status": rows[0].status,
            "account_count": len(rows),
            "active_count": len(active),
            "has_password": any(row.password_encrypted for row in rows),
            "has_cookie": any(row.cookie_encrypted for row in rows),
            "last_error": next((row.last_error for row in rows if row.last_error), None),
        }
