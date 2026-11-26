"""后台运维 API（战线 E-P1，系统改造总方案 8.3/8.5）。

- **批量操作**：用户批量启停/删除、API Key 批量吊销/启停 —— 消除
  「13+ 面板只能逐个点」的运营负担；删除类高危操作叠加 ``system:dangerous``
  能力（8.6 红线：require_admin + CAP_DANGEROUS）。
- **配额管理**：每日全局 Token 配额的读取与调整（存 system_settings，
  不再只能改环境变量）；``check_daily_quota`` 优先读数据库配置。
- **统一审批中心**：聚合网站部署 / 作品发布 / 智能体工具审批三类待办
  （原先分散在部署页/发布页/会话内，无统一视图与计数）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_capability, require_perm
from app.core.roles import CAP_DANGEROUS, CAP_USER_MANAGE
from app.core.timezone import app_now
from app.db.models import (
    AgentUsageEventModel,
    ApprovalModel,
    SystemSettingModel,
    UserModel,
)
from app.services import audit_service

logger = logging.getLogger("agenticos.admin_ops")

router = APIRouter(prefix="/admin", tags=["admin-ops"])

#: system_settings 里的配额键
# 配额配置读写实现在服务层（quota_service），端点层只做 HTTP 形态
from app.services.quota_service import QUOTA_KEY, get_daily_quota_config  # noqa: E402


@router.get("/quota/overview", summary="配额概览：当前配置 + 今日按用户用量 Top + 超限用户")
def quota_overview(
    top: int = 20,
    _: UserModel = Depends(require_perm("settings:edit")),
) -> dict[str, Any]:
    """后台配额看板（8.5.2）：配置值 + 今日用量分布 + 超限名单（一键放行的数据源）。

    「一键放行」的运营语义 = 临时调高配额或关掉配额（PUT /admin/quota），
    不做按用户豁免表（保持数据模型最小）。
    """
    from sqlalchemy import func

    from app.core.timezone import app_now as _now
    from app.db.session import SessionLocal
    from app.services.quota_service import is_admin_like

    with SessionLocal() as db:
        config = get_daily_quota_config(db)
        quota = int(config["daily_token_quota"])
        today = _now().date()

        used_expr = func.coalesce(AgentUsageEventModel.input_tokens, 0) + func.coalesce(
            AgentUsageEventModel.output_tokens, 0
        )
        rows = db.execute(
            select(
                AgentUsageEventModel.user_id,
                func.sum(used_expr).label("used"),
                func.count(AgentUsageEventModel.id).label("events"),
            )
            .where(func.date(AgentUsageEventModel.created_at) == today)
            .group_by(AgentUsageEventModel.user_id)
            .order_by(func.sum(used_expr).desc())
            .limit(min(max(top, 1), 100))
        ).all()

        users = {
            u.id: u
            for u in db.execute(
                select(UserModel).where(
                    UserModel.id.in_([r.user_id for r in rows if r.user_id is not None])
                )
            ).scalars().all()
        }

        per_user = []
        for r in rows:
            user = users.get(r.user_id)
            used = int(r.used or 0)
            per_user.append(
                {
                    "user_id": r.user_id,
                    "user_name": getattr(user, "name", None) or (f"用户 #{r.user_id}" if r.user_id else "匿名"),
                    "user_email": getattr(user, "email", None),
                    "role": getattr(user, "role", None),
                    "exempt": bool(user and is_admin_like(getattr(user, "role", ""))),
                    "used_tokens": used,
                    "events": int(r.events or 0),
                    "quota": quota,
                    "ratio": (round(used / quota, 3) if quota > 0 else None),
                    "exceeded": bool(quota > 0 and used >= quota and user and not is_admin_like(getattr(user, "role", ""))),
                }
            )
        return {
            "config": config,
            "today": str(today),
            "per_user": per_user,
            "exceeded_count": sum(1 for p in per_user if p["exceeded"]),
        }


# ── 配额管理 ──────────────────────────────────────────────────────────


@router.get("/quota", summary="读取每日 Token 配额配置")
def read_quota(_: UserModel = Depends(require_perm("settings:edit"))) -> dict[str, Any]:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        return get_daily_quota_config(db)


class QuotaUpdateRequest(BaseModel):
    daily_token_quota: int = Field(ge=0, le=10_000_000_000, description="0 = 关闭配额")


@router.put("/quota", summary="调整每日 Token 配额（0 = 关闭）")
def update_quota(
    payload: QuotaUpdateRequest,
    current_user: UserModel = Depends(require_perm("settings:edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(SystemSettingModel, QUOTA_KEY)
    if row is None:
        row = SystemSettingModel(key=QUOTA_KEY, value=str(payload.daily_token_quota))
        db.add(row)
    else:
        row.value = str(payload.daily_token_quota)
        row.updated_at = app_now()
    db.commit()
    audit_service.record(
        db,
        action="admin.quota.update",
        actor=current_user,
        resource_type="system_setting",
        resource_id=QUOTA_KEY,
        detail={"daily_token_quota": payload.daily_token_quota},
    )
    return {"source": "database", "daily_token_quota": payload.daily_token_quota}


# ── 批量操作 ──────────────────────────────────────────────────────────


class UserBatchRequest(BaseModel):
    action: str = Field(pattern="^(enable|disable|delete)$")
    user_ids: list[int] = Field(min_length=1, max_length=200)


class UserBatchResult(BaseModel):
    succeeded: list[int]
    failed: list[dict[str, Any]]


@router.post("/users/batch", summary="批量启停/删除用户")
async def batch_users(
    payload: UserBatchRequest,
    http_request: Request,
    current_user: UserModel = Depends(require_capability(CAP_USER_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # 自身保护先于能力校验：无论有没有 capability 都不能删/停自己
    if current_user.id in payload.user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能批量删除或停用当前登录账号")
    if payload.action == "delete":
        # 高危：删账号叠加 system:dangerous（8.6 红线）
        from app.core.roles import has_capability

        if not has_capability(current_user.role, CAP_DANGEROUS):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="批量删除需要 system:dangerous 能力")

    succeeded: list[int] = []
    failed: list[dict[str, Any]] = []
    for user_id in payload.user_ids:
        # 每行一个 savepoint：单条失败只回滚它自己，不把此前 succeeded 的
        # 修改一并回滚（原实现 rollback() 会让返回值谎报成功但库里全没变）。
        nested = db.begin_nested()
        try:
            user = db.get(UserModel, user_id)
            if user is None:
                failed.append({"user_id": user_id, "reason": "用户不存在"})
                nested.commit()
                continue
            if payload.action == "enable":
                user.is_active = True
            elif payload.action == "disable":
                user.is_active = False
            else:  # delete
                if user.role == "superadmin":
                    failed.append({"user_id": user_id, "reason": "不能删除 superadmin"})
                    nested.commit()
                    continue
                user.is_active = False
                user.email = f"deleted-{user.id}@deleted.local"
                user.name = f"deleted-{user.id}"
                db.flush()
            nested.commit()
            succeeded.append(user_id)
        except Exception as exc:  # noqa: BLE001 —— 单条失败不拖垮整批
            nested.rollback()
            failed.append({"user_id": user_id, "reason": str(exc)[:120]})
    db.commit()

    audit_service.record_request(
        db,
        http_request,
        action="admin.users.batch",
        actor=current_user,
        resource_type="user",
        detail={"action": payload.action, "succeeded": succeeded, "failed": failed},
    )
    return {"action": payload.action, "succeeded": succeeded, "failed": failed}


class ApiKeyBatchRequest(BaseModel):
    action: str = Field(pattern="^(revoke|enable|disable)$")
    key_ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/api-keys/batch", summary="批量吊销/启停 API Key")
async def batch_api_keys(
    payload: ApiKeyBatchRequest,
    http_request: Request,
    current_user: UserModel = Depends(require_perm("settings:edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.db.models import ApiKeyModel

    succeeded: list[int] = []
    failed: list[dict[str, Any]] = []
    for key_id in payload.key_ids:
        key = db.get(ApiKeyModel, key_id)
        if key is None:
            failed.append({"key_id": key_id, "reason": "API Key 不存在"})
            continue
        if payload.action == "revoke":
            # 与 api_key_service.revoke_api_key 语义一致：吊销 = 删除记录
            # （key_hash 唯一索引即刻失效，无孤儿行）
            db.delete(key)
        else:
            key.enabled = {"enable": True, "disable": False}[payload.action]
            key.updated_at = app_now()
        succeeded.append(key_id)
    db.commit()
    audit_service.record_request(
        db,
        http_request,
        action="admin.api_keys.batch",
        actor=current_user,
        resource_type="api_key",
        detail={"action": payload.action, "succeeded": succeeded, "failed": failed},
    )
    return {"action": payload.action, "succeeded": succeeded, "failed": failed}


# ── 统一审批中心（8.5.4）──────────────────────────────────────────────


@router.get("/approvals/pending", summary="统一审批中心：三类待办聚合（服务端分页）")
async def unified_pending_approvals(
    limit: int = Query(8, ge=1, le=100, description="每类待办每页条数"),
    offset: int = Query(0, ge=0),
    _: UserModel = Depends(require_perm("settings:edit")),
) -> dict[str, Any]:
    """聚合网站部署 / 作品发布 / 智能体工具审批的待办与计数。

    三类各自按 limit/offset 服务端分页；counts 始终为**全量**计数（不受
    分页影响），pagination 给出每类的 total/pages/current，供前端统一
    <Pagination> 组件使用。数据量大时不再一次性返回全部。
    """
    from app.services.published_item_service import PublishedItemService
    from app.services.website_deploy_service import WebsiteDeployService

    def _load_db() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        deploys = WebsiteDeployService().list_pending()
        published = PublishedItemService().list_pending()
        return deploys, published

    import asyncio

    all_deploys, all_published = await asyncio.to_thread(_load_db)

    def _load_tool_approvals() -> list[dict[str, Any]]:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            rows = db.scalars(
                select(ApprovalModel)
                .where(ApprovalModel.status == "pending")
                .order_by(ApprovalModel.created_at.desc())
            ).all()
            return [
                {
                    "approval_id": row.approval_id,
                    "session_id": row.session_id,
                    "tool_name": row.tool_name,
                    "arguments": row.arguments_json,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    all_tools = await asyncio.to_thread(_load_tool_approvals)

    # 全量计数（分页前）
    counts = {
        "website_deploys": len(all_deploys),
        "published_items": len(all_published),
        "tool_approvals": len(all_tools),
        "total": len(all_deploys) + len(all_published) + len(all_tools),
    }
    # 服务端切片
    end = offset + limit
    deploys = all_deploys[offset:end]
    published = all_published[offset:end]
    tool_approvals = all_tools[offset:end]

    import math

    pagination = {
        key: {
            "total": counts[key],
            "pages": max(1, math.ceil(counts[key] / limit)),
            "current": min(offset // limit + 1, max(1, math.ceil(counts[key] / limit))),
            "page_size": limit,
        }
        for key in ("website_deploys", "published_items", "tool_approvals")
    }
    return {
        "counts": counts,
        "pagination": pagination,
        "website_deploys": deploys,
        "published_items": published,
        "tool_approvals": tool_approvals,
    }
