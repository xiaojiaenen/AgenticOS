"""审计日志服务（M6-C）。

写入路径分两种（设计稿 4.3）：

- ``record()``   同步落库 —— 登录/登出、审批决策、管理 CRUD、权限变更等关键操作。
  这些事件丢了就等于没有审计，所以不能只靠队列。
- ``record_async()`` 走 arq 队列 —— 次要事件（如知识库文档上传）。
  队列不可用时**自动回落为同步写**，不静默丢事件。

脱敏
----
``redact_detail()`` 在落库前处理 detail：

1. 键名命中敏感词（password / token / secret / cookie / authorization / apikey ...）
   → 值替换为 ``"***"``；
2. 其余字符串超过 ``MAX_VALUE_LENGTH``（512）截断并加省略号；
3. 递归处理 dict / list，深度上限 6，超出部分丢弃（防深嵌套与自引用）。

保留策略：``purge_older_than()`` 删除 ``RETENTION_DAYS``（180）天前的记录，
注册为 arq cron（见 ``app/services/task_queue.py``），也可手动调用。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.timezone import app_now
from app.db.models import AuditLogModel, UserModel

logger = logging.getLogger(__name__)

RETENTION_DAYS = 180
MAX_VALUE_LENGTH = 512
MAX_DEPTH = 6
REDACTED = "***"

RESULT_ALLOW = "allow"
RESULT_DENY = "deny"
RESULT_ERROR = "error"

# 键名精确命中即脱敏（避免 "code" 这类短词误伤 status_code / error_code）
SENSITIVE_KEYS_EXACT: frozenset[str] = frozenset(
    {"code", "otp", "pwd", "token", "passwd", "password", "secret", "cookie", "credential"}
)

# 键名包含以下片段即脱敏（大小写不敏感）
SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "password",
    "passwd",
    "token",
    "secret",
    "cookie",
    "authorization",
    "auth_header",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "credential",
    "session_key",
    "refresh_token",
)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered in SENSITIVE_KEYS_EXACT:
        return True
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_detail(detail: Any, *, _depth: int = 0) -> Any:
    """脱敏 + 截断（纯函数，可单测）。"""
    if _depth > MAX_DEPTH:
        return "***truncated***"
    if isinstance(detail, dict):
        redacted: dict[str, Any] = {}
        for key, value in detail.items():
            key_str = str(key)
            if _is_sensitive(key_str):
                redacted[key_str] = REDACTED
            else:
                redacted[key_str] = redact_detail(value, _depth=_depth + 1)
        return redacted
    if isinstance(detail, (list, tuple)):
        return [redact_detail(item, _depth=_depth + 1) for item in detail]
    if isinstance(detail, str):
        if len(detail) > MAX_VALUE_LENGTH:
            return detail[:MAX_VALUE_LENGTH] + "...[truncated]"
        return detail
    if isinstance(detail, (int, float, bool)) or detail is None:
        return detail
    return redact_detail(str(detail), _depth=_depth + 1)


def record(
    db: Session,
    *,
    action: str,
    actor_id: int | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: Any = None,
    result: str = RESULT_ALLOW,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
    actor: UserModel | None = None,
) -> AuditLogModel:
    """同步写一条审计记录（关键操作）。

    ``actor`` 传入 UserModel 时自动带出 actor_id / actor_email，省得每个端点
    重复写两遍。审计写失败不应拖垮业务请求，因此异常只记日志不抛出。
    """
    if actor is not None:
        actor_id = actor.id if actor_id is None else actor_id
        actor_email = actor.email if actor_email is None else actor_email

    entry = AuditLogModel(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=None if resource_id is None else str(resource_id),
        result=result,
        ip=ip,
        user_agent=(user_agent or "")[:512] or None,
        detail_json=json.dumps(redact_detail(detail or {}), ensure_ascii=False, default=str),
        created_at=app_now(),
    )
    try:
        db.add(entry)
        db.commit()
    except Exception:  # noqa: BLE001 -- 审计失败不能影响主流程
        db.rollback()
        logger.exception("Failed to write audit log: action=%s resource=%s", action, resource_id)
        return entry
    db.refresh(entry)
    return entry


def record_request(
    db: Session,
    request: Any,
    *,
    action: str,
    actor: UserModel | None = None,
    **fields: Any,
) -> None:
    """带请求上下文（ip / UA）的审计写入，永不抛异常。

    端点里几乎每个写操作都要写审计，重复三行 request_context 容易漏；
    这个小封装统一「审计失败不拖垮业务」的语义。
    """
    ctx = request_context(request)
    try:
        record(db, action=action, actor=actor, ip=ctx["ip"], user_agent=ctx["user_agent"], **fields)
    except Exception:  # noqa: BLE001 -- 审计异常不得让管理操作失败
        logger.warning("audit %s failed", action, exc_info=True)


async def record_async(
    db: Session,
    *,
    action: str,
    actor: UserModel | None = None,
    resource_type: str | None = None,
    resource_id: Any = None,
    result: str = RESULT_ALLOW,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """入队写审计（次要操作）。Redis 不可用时回落为同步写。"""
    payload = {
        "action": action,
        "actor_id": actor.id if actor is not None else None,
        "actor_email": actor.email if actor is not None else None,
        "resource_type": resource_type,
        "resource_id": None if resource_id is None else str(resource_id),
        "result": result,
        "ip": ip,
        "user_agent": user_agent,
        "detail": redact_detail(detail or {}),
    }
    try:
        from app.services.task_queue import submit_audit_log

        await submit_audit_log(payload)
        return
    except Exception as exc:  # noqa: BLE001
        logger.info("arq audit enqueue failed (%s), falling back to synchronous write", exc)
        record(
            db,
            action=action,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            ip=ip,
            user_agent=user_agent,
            detail=detail,
        )


def request_context(request) -> dict[str, str | None]:
    """从 Starlette Request 提取审计上下文（ip / user-agent）。"""
    if request is None:
        return {"ip": None, "user_agent": None}
    client = getattr(request, "client", None)
    return {
        "ip": client.host if client else None,
        "user_agent": request.headers.get("user-agent") if hasattr(request, "headers") else None,
    }


def purge_older_than(db: Session, retention_days: int = RETENTION_DAYS) -> int:
    """删除保留期之前的审计记录，返回删除条数。"""
    cutoff = app_now() - timedelta(days=retention_days)
    result = db.execute(delete(AuditLogModel).where(AuditLogModel.created_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)


def query_logs(
    db: Session,
    *,
    actor_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLogModel], int]:
    """审计查询（管理端），返回 (本页记录, 总数)。"""
    from sqlalchemy import func, select

    conditions = []
    if actor_id is not None:
        conditions.append(AuditLogModel.actor_id == actor_id)
    if action:
        conditions.append(AuditLogModel.action == action)
    if resource_type:
        conditions.append(AuditLogModel.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLogModel.resource_id == str(resource_id))
    if result:
        conditions.append(AuditLogModel.result == result)

    total = db.scalar(select(func.count(AuditLogModel.id)).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(AuditLogModel)
            .where(*conditions)
            .order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return rows, int(total)
