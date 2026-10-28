"""AI 提供商管理（仅管理员）。

把「用哪个大模型后端」从环境变量变成可运营的配置：

- ``openai_compatible``：填地址 + Key + 模型即可，换厂商只改配置；
- ``enterprise_cookie``：企业内网网关，靠浏览器登录态，支持**多账号池**、
  自动登录与手贴兜底。

三条安全约束贯穿本文件：

1. **密钥只进不出**。任何响应都只回答 ``has_api_key`` / ``has_cookie``，
   不返回密文、明文或尾部片段 —— 尾部片段也足够做撞库验证。
2. **所有写操作留审计**，且 ``detail`` 只记字段名与开关状态。
3. **凭据按账号寻址**。多账号池里「标记谁失效」「让谁重新登录」都必须带
   ``credential_id``，只传 provider_id 会把整个池子当一条处理。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.db.models import UserModel
from app.services import audit_service
from app.services.llm_providers import (
    auto_login,
    catalog,
    credentials,
    discovery,
    presets,
    runtime,
)
from app.services.llm_providers import spec as provider_spec

logger = logging.getLogger("agenticos.llm_providers.api")

router = APIRouter(prefix="/settings/llm-providers", tags=["AI Providers"])

_ENTERPRISE = provider_spec.PROVIDER_TYPE_ENTERPRISE_COOKIE


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProviderCreatePayload(BaseModel):
    name: str = Field(..., max_length=120)
    slug: str = Field(..., max_length=64)
    provider_type: str = Field(default=provider_spec.PROVIDER_TYPE_OPENAI)
    base_url: str = Field(default="", max_length=512)
    model: str = Field(default="", max_length=128)
    # 留空表示不配置 Key（企业网关类通常不需要）
    api_key: str | None = Field(default=None, max_length=2048)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_tokens: int | None = Field(default=None, ge=1)
    extra: dict = Field(default_factory=dict)
    # 厂商预设：给定后用它补全地址/模型/登录动作，显式传入的值优先
    preset: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    is_default: bool = False


class ProviderUpdatePayload(BaseModel):
    """局部更新。

    ``api_key`` 三态语义：不传 = 保持不变；传空串 = 清空；传值 = 覆盖。
    """

    name: str | None = Field(default=None, max_length=120)
    provider_type: str | None = None
    base_url: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=2048)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    max_tokens: int | None = Field(default=None, ge=1)
    extra: dict | None = None
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class CredentialPayload(BaseModel):
    username: str = Field(default="", max_length=255)
    # 留空表示不修改已保存的密码
    password: str = Field(default="", max_length=512)
    login_url: str = Field(default="", max_length=512)
    auto_refresh: bool | None = None


class ManualCookiePayload(BaseModel):
    cookie: str = Field(..., max_length=20000)
    # 留空表示按系统默认保守估计
    expire_at: str | None = None


class AccountCreatePayload(BaseModel):
    """新增一个账号到池里。"""

    label: str = Field(default="", max_length=64)
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=512)
    login_url: str = Field(default="", max_length=512)
    # 小的优先。主力号给 10、备用号给 90 这种用法
    priority: int = Field(default=100, ge=1, le=10_000)


class AccountUpdatePayload(BaseModel):
    """局部更新。``password`` 空串表示保持原密码。"""

    label: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)
    login_url: str | None = Field(default=None, max_length=512)
    priority: int | None = Field(default=None, ge=1, le=10_000)
    auto_refresh: bool | None = None
    disabled: bool | None = None


class RoleBindingPayload(BaseModel):
    """用途 → 模型名。传空字符串表示「这个用途不单独指定」。"""

    roles: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _require_provider(db: Session, provider_id: int):
    row = provider_spec.get_provider(db, provider_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提供商不存在")
    return row


def _active_provider_id() -> int | None:
    return provider_spec.resolve_active_provider().provider_id


def _view(row, db: Session) -> dict:
    accounts = (
        credentials.list_credentials(db, row.id)
        if row.provider_type == _ENTERPRISE
        else []
    )
    return provider_spec.to_public_dict(
        row,
        credential=accounts[0] if accounts else None,
        is_active=(row.id == _active_provider_id()),
        account_count=len(accounts) if row.provider_type == _ENTERPRISE else None,
    )


def _audit(
    http_request: Request,
    db: Session,
    *,
    action: str,
    current_user: UserModel,
    provider_id: int | None = None,
    result: str = "allow",
    detail: dict | None = None,
) -> None:
    audit_service.record_request(
        db,
        http_request,
        action=action,
        actor=current_user,
        resource_type="llm_provider",
        resource_id=provider_id,
        result=result,
        detail=detail or {},
    )


# ---------------------------------------------------------------------------
# 提供商 CRUD
# ---------------------------------------------------------------------------


@router.get("")
def list_llm_providers(
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    """列表 + 当前生效来源。

    ``env_fallback`` 单独返回：它让管理员能一眼看出「现在其实没有一个启用
    的提供商，是在用环境变量」。这种状态在界面上必须是显式的，否则
    「明明配了提供商却没生效」会被误判成 bug。
    """
    rows = provider_spec.list_providers(db)
    active = provider_spec.resolve_active_provider()
    env = provider_spec.env_provider_spec()
    return {
        "items": [_view(row, db) for row in rows],
        "active": active.describe(),
        "env_fallback": {
            "slug": env.slug,
            "base_url": env.base_url,
            "model": env.model,
            "has_api_key": bool(env.api_key),
            "usable": bool(env.api_key),
        },
        "provider_types": [
            {"value": value, "label": provider_spec.PROVIDER_TYPE_LABELS.get(value, value)}
            for value in provider_spec.PROVIDER_TYPES
        ],
        "presets": presets.list_presets(),
        "model_roles": [
            {"value": value, "label": label} for value, label in presets.MODEL_ROLES.items()
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_llm_provider(
    payload: ProviderCreatePayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = provider_spec.create_provider(
            db,
            name=payload.name,
            slug=payload.slug,
            provider_type=payload.provider_type,
            base_url=payload.base_url,
            model=payload.model,
            api_key=payload.api_key,
            timeout_seconds=payload.timeout_seconds,
            max_tokens=payload.max_tokens,
            extra=payload.extra,
            description=payload.description,
            enabled=payload.enabled,
            is_default=payload.is_default,
            created_by=current_user.id,
            preset_slug=payload.preset,
        )
    except provider_spec.ProviderConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(row)
    _audit(
        http_request, db, action="llm_provider.create", current_user=current_user,
        provider_id=row.id,
        detail={
            "slug": row.slug,
            "provider_type": row.provider_type,
            "base_url": row.base_url,
            "model": row.model,
            "api_key_set": bool(payload.api_key),
            "is_default": row.is_default,
        },
    )
    return _view(row, db)


@router.post("/import-env", status_code=status.HTTP_201_CREATED)
def import_from_env(
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """把环境变量里的 LLM 配置落成一个真实的提供商记录。

    显式动作而不是启动时自动搬运：自动搬会把 .env 里的明文 Key 静默复制
    进库，运维根本不知道凭据多了一份副本。
    """
    env = provider_spec.env_provider_spec()
    if not env.base_url and not env.model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="环境变量未配置 OPENAI_BASE_URL / OPENAI_MODEL，无可导入内容",
        )
    try:
        row = provider_spec.create_provider(
            db,
            name="环境变量导入",
            slug="env-import",
            provider_type=provider_spec.PROVIDER_TYPE_OPENAI,
            base_url=env.base_url or "https://api.openai.com/v1",
            model=env.model or "gpt-4o-mini",
            api_key=env.api_key,
            timeout_seconds=env.timeout_seconds,
            description="由环境变量导入，导入后可脱离 .env 独立维护",
            created_by=current_user.id,
        )
    except provider_spec.ProviderConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(row)
    _audit(
        http_request, db, action="llm_provider.import_env", current_user=current_user,
        provider_id=row.id,
        detail={"slug": row.slug, "base_url": row.base_url, "model": row.model,
                "api_key_set": bool(env.api_key)},
    )
    return _view(row, db)


@router.patch("/{provider_id}")
def update_llm_provider(
    provider_id: int,
    payload: ProviderUpdatePayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = _require_provider(db, provider_id)
    # model_fields_set 才能区分「没传」与「显式传了空」——
    # 这两者语义完全不同（保持原 Key vs 清空 Key）。
    fields = payload.model_dump(exclude_unset=True)
    try:
        provider_spec.update_provider(db, row, fields=fields)
    except provider_spec.ProviderConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(row)
    _audit(
        http_request, db, action="llm_provider.update", current_user=current_user,
        provider_id=row.id,
        detail={
            "changed_fields": sorted(fields.keys()),
            # 只记「Key 是否被轮换」，不记内容
            "api_key_rotated": "api_key" in fields and bool(fields.get("api_key")),
            "api_key_cleared": "api_key" in fields and not fields.get("api_key"),
        },
    )
    return _view(row, db)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_provider(
    provider_id: int,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    row = _require_provider(db, provider_id)
    slug, was_default = row.slug, row.is_default
    provider_spec.delete_provider(db, row)
    db.commit()
    _audit(
        http_request, db, action="llm_provider.delete", current_user=current_user,
        provider_id=provider_id, detail={"slug": slug, "was_default": was_default},
    )


@router.post("/{provider_id}/default")
def set_default_llm_provider(
    provider_id: int,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = _require_provider(db, provider_id)
    try:
        provider_spec.set_default_provider(db, provider_id)
    except provider_spec.ProviderConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    _audit(
        http_request, db, action="llm_provider.set_default", current_user=current_user,
        provider_id=provider_id, detail={"slug": row.slug},
    )
    return {"active": provider_spec.resolve_active_provider().describe()}


@router.post("/{provider_id}/test")
async def test_llm_provider(
    provider_id: int,
    http_request: Request,
    deep: bool = False,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """分阶段连通性诊断。失败也返回 200 + ``ok=false``：这是诊断结果，不是请求错误。

    ``deep=true`` 会再发一条真实对话和一次带 ``tools`` 的请求 —— 那是唯一能
    确认「agent 能不能真的跑起来」的办法，但会消耗上游额度，所以默认关闭。
    """
    row = _require_provider(db, provider_id)
    result = await runtime.test_provider(provider_spec.spec_from_row(row), deep=deep)
    _audit(
        http_request, db, action="llm_provider.test", current_user=current_user,
        provider_id=provider_id,
        result="allow" if result.get("ok") else "error",
        detail={
            "deep": deep,
            "stage": result.get("stage"),
            "status_code": result.get("status_code"),
            "message": (result.get("message") or "")[:200],
            "elapsed_ms": result.get("elapsed_ms"),
        },
    )
    return result


# ---------------------------------------------------------------------------
# 企业网关的凭据与登录态
# ---------------------------------------------------------------------------


def _require_enterprise(row) -> None:
    if row.provider_type != _ENTERPRISE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有企业网关（Cookie）类型的提供商需要登录凭据",
        )


@router.get("/{provider_id}/credential")
def get_provider_credential(
    provider_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    credential_row = credentials.get_credential(db, row.id)
    if credential_row is None:
        return {"username": "", "has_password": False, "has_cookie": False,
                "status": "pending", "auto_refresh": True, "expire_at": None,
                "last_login_at": None, "last_error": None, "updated_at": None}
    return provider_spec.credential_status_dict(credential_row)


@router.put("/{provider_id}/credential")
def update_provider_credential(
    provider_id: int,
    payload: CredentialPayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    credential_row = credentials.save_credentials(
        db,
        row.id,
        username=payload.username,
        password=payload.password or None,
        login_url=payload.login_url or None,
        auto_refresh=payload.auto_refresh,
    )
    db.commit()
    db.refresh(credential_row)
    _audit(
        http_request, db, action="llm_provider.credential_update", current_user=current_user,
        provider_id=provider_id,
        detail={
            "username": payload.username,
            "password_rotated": bool(payload.password),
            "auto_refresh": credential_row.auto_refresh,
            "status": credential_row.status,
        },
    )
    return provider_spec.credential_status_dict(credential_row)


@router.delete("/{provider_id}/credential")
def clear_provider_credential(
    provider_id: int,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    credential_row = credentials.clear_credentials(db, row.id)
    db.commit()
    db.refresh(credential_row)
    _audit(
        http_request, db, action="llm_provider.credential_clear", current_user=current_user,
        provider_id=provider_id, detail={"username_cleared": True},
    )
    return provider_spec.credential_status_dict(credential_row)


@router.post("/{provider_id}/login")
async def login_provider(
    provider_id: int,
    http_request: Request,
    credential_id: int | None = None,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """触发一次自动登录（Playwright）。

    同步在请求里跑：一次登录数秒，管理员点按钮后等结果是可接受的交互；
    真正的「无人值守续期」由定时任务负责，不走这里。

    ``credential_id`` 省略时由服务层挑「最需要续期」的那个账号（未登录成功
    或已过期优先），而不是无脑刷第一个 —— 池里 3 个号只有 1 个挂了时，
    点一次登录应该修的是挂掉的那个。
    """
    row = _require_provider(db, provider_id)
    _require_enterprise(row)

    result = await auto_login.login_and_store(provider_id, credential_id)
    _audit(
        http_request, db, action="llm_provider.login", current_user=current_user,
        provider_id=provider_id,
        result="allow" if result.success else "error",
        detail={
            "success": result.success,
            "credential_id": result.credential_id,
            "message": result.message[:200],
        },
    )
    return {
        "success": result.success,
        "message": result.message,
        "credential_id": result.credential_id,
        "credentials": _accounts_view(db, provider_id),
    }


@router.put("/{provider_id}/credential/cookie")
def put_manual_cookie(
    provider_id: int,
    payload: ManualCookiePayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """手贴 Cookie 兜底。

    自动登录依赖上游登录页结构，上游一改版就失效；这条路保证「至少还能救
    回来」，不必等代码适配。
    """
    from datetime import datetime

    row = _require_provider(db, provider_id)
    _require_enterprise(row)

    expire_at = None
    if payload.expire_at:
        try:
            expire_at = datetime.fromisoformat(payload.expire_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="expire_at 格式不正确"
            ) from exc

    try:
        credential_row = credentials.save_manual_cookie(
            db, row.id, cookie=payload.cookie, expire_at=expire_at
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(credential_row)
    _audit(
        http_request, db, action="llm_provider.cookie_update", current_user=current_user,
        provider_id=provider_id,
        detail={"expire_at": credential_row.expire_at.isoformat() if credential_row.expire_at else None},
    )
    return provider_spec.credential_status_dict(credential_row)


# ---------------------------------------------------------------------------
# 账号池（一个企业网关挂多个账号分摊配额）
# ---------------------------------------------------------------------------


def _accounts_view(db: Session, provider_id: int) -> list[dict]:
    return [
        provider_spec.credential_status_dict(row)
        for row in credentials.list_credentials(db, provider_id)
    ]


@router.get("/{provider_id}/accounts")
def list_provider_accounts(
    provider_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    """账号池列表。**只返回状态，不返回 Cookie 与密码。**"""
    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    items = _accounts_view(db, provider_id)
    return {
        "items": items,
        "total": len(items),
        "active": sum(1 for item in items if item["status"] == "active"),
        "rotation_policy": "按 priority 升序，同级内最久未用优先；连续失败达阈值自动退出轮换",
    }


@router.post("/{provider_id}/accounts", status_code=status.HTTP_201_CREATED)
def create_provider_account(
    provider_id: int,
    payload: AccountCreatePayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = _require_provider(db, provider_id)
    _require_enterprise(row)

    existing = credentials.list_credentials(db, provider_id)
    if payload.username:
        duplicated = [item for item in existing if item.username == payload.username.strip()]
        if duplicated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"账号 {payload.username} 已存在，请直接编辑或删除后重建",
            )

    account = credentials.add_account(
        db,
        provider_id,
        label=payload.label,
        username=payload.username,
        password=payload.password or None,
        login_url=payload.login_url or None,
        priority=payload.priority,
    )
    db.commit()
    db.refresh(account)
    _audit(
        http_request, db, action="llm_provider.account_create", current_user=current_user,
        provider_id=provider_id,
        detail={
            "credential_id": account.id,
            "username": account.username,
            "priority": account.priority,
            "password_set": bool(payload.password),
        },
    )
    return provider_spec.credential_status_dict(account)


@router.patch("/{provider_id}/accounts/{credential_id}")
def update_provider_account(
    provider_id: int,
    credential_id: int,
    payload: AccountUpdatePayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    account = credentials.get_by_id(db, credential_id)
    if account is None or account.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    fields = payload.model_dump(exclude_unset=True)
    if any(key in fields for key in ("username", "password", "login_url", "label", "priority", "auto_refresh")):
        account = credentials.save_credentials(
            db,
            provider_id,
            username=fields.get("username", account.username),
            password=fields.get("password") or None,
            login_url=fields.get("login_url"),
            auto_refresh=fields.get("auto_refresh"),
            credential_id=credential_id,
            label=fields.get("label"),
            priority=fields.get("priority"),
        )
    if "disabled" in fields and fields["disabled"] is not None:
        account.disabled = bool(fields["disabled"])
        # 重新启用时清掉失败计数，否则会带着「已退出轮换」的历史继续被跳过
        if not account.disabled:
            account.failure_count = 0
            if account.cookie_encrypted and account.status == credentials.STATUS_EXPIRED:
                account.status = credentials.STATUS_ACTIVE

    db.commit()
    db.refresh(account)
    _audit(
        http_request, db, action="llm_provider.account_update", current_user=current_user,
        provider_id=provider_id,
        detail={
            "credential_id": credential_id,
            "changed_fields": sorted(fields.keys()),
            "password_rotated": bool(fields.get("password")),
            "disabled": account.disabled,
        },
    )
    return provider_spec.credential_status_dict(account)


@router.delete("/{provider_id}/accounts/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_account(
    provider_id: int,
    credential_id: int,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    account = credentials.get_by_id(db, credential_id)
    if account is None or account.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    username = account.username
    credentials.delete_account(db, credential_id)
    db.commit()
    _audit(
        http_request, db, action="llm_provider.account_delete", current_user=current_user,
        provider_id=provider_id, detail={"credential_id": credential_id, "username": username},
    )


@router.put("/{provider_id}/accounts/{credential_id}/cookie")
def put_account_cookie(
    provider_id: int,
    credential_id: int,
    payload: ManualCookiePayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """给指定账号手贴 Cookie。多账号时「贴给谁」必须显式，不能靠默认。"""
    from datetime import datetime

    row = _require_provider(db, provider_id)
    _require_enterprise(row)
    account = credentials.get_by_id(db, credential_id)
    if account is None or account.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    expire_at = None
    if payload.expire_at:
        try:
            expire_at = datetime.fromisoformat(payload.expire_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="expire_at 格式不正确"
            ) from exc

    try:
        account = credentials.save_manual_cookie(
            db, provider_id, cookie=payload.cookie, expire_at=expire_at, credential_id=credential_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(account)
    _audit(
        http_request, db, action="llm_provider.account_cookie", current_user=current_user,
        provider_id=provider_id,
        detail={
            "credential_id": credential_id,
            "expire_at": account.expire_at.isoformat() if account.expire_at else None,
        },
    )
    return provider_spec.credential_status_dict(account)


# ---------------------------------------------------------------------------
# 模型目录与用途绑定
# ---------------------------------------------------------------------------


@router.get("/{provider_id}/models")
def list_provider_models(
    provider_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    row = _require_provider(db, provider_id)
    items = [catalog.to_dict(item) for item in catalog.list_models(db, provider_id)]
    return {
        "items": items,
        "total": len(items),
        "roles": (provider_spec.parse_extra(row.extra_json).get("roles") or {}),
        "role_options": [
            {"value": value, "label": label} for value, label in presets.MODEL_ROLES.items()
        ],
    }


@router.post("/{provider_id}/models/discover")
async def discover_provider_models(
    provider_id: int,
    http_request: Request,
    persist: bool = True,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """从上游拉模型清单。

    ``persist=false`` 只做预演：接新网关时先看一眼「上游到底有哪些模型」，
    再决定要不要写进库。默认写入，因为绝大多数情况下这就是想要的结果。
    """
    row = _require_provider(db, provider_id)
    spec = provider_spec.spec_from_row(row)

    cookie = None
    if row.provider_type == _ENTERPRISE:
        lease = credentials.acquire(provider_id)
        if lease is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="账号池里没有可用账号，请先登录或手贴 Cookie",
            )
        cookie = lease.cookie

    models, meta = await discovery.fetch_models(
        base_url=spec.base_url,
        extra=spec.extra,
        cookie=cookie,
        api_key=spec.api_key,
    )

    added = updated = 0
    if models and persist:
        added, updated = catalog.upsert_models(db, provider_id, models)
        db.commit()

    _audit(
        http_request, db, action="llm_provider.model_discover", current_user=current_user,
        provider_id=provider_id,
        result="allow" if models else "error",
        detail={
            "count": len(models),
            "added": added,
            "updated": updated,
            "persist": persist,
            "message": (meta.get("message") or "")[:200],
        },
    )
    return {
        "ok": bool(models),
        "meta": meta,
        "models": models,
        "added": added,
        "updated": updated,
    }


@router.delete("/{provider_id}/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_model(
    provider_id: int,
    model_id: int,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    _require_provider(db, provider_id)
    if not catalog.delete_model(db, provider_id, model_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")
    db.commit()
    _audit(
        http_request, db, action="llm_provider.model_delete", current_user=current_user,
        provider_id=provider_id, detail={"model_id": model_id},
    )


@router.put("/{provider_id}/roles")
def update_provider_roles(
    provider_id: int,
    payload: RoleBindingPayload,
    http_request: Request,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """按用途绑定模型。

    校验模型名是否在目录里 —— 但**目录为空时放行**。理由是「先绑模型、
    后同步目录」是合理顺序，硬拦会逼用户先去点一次同步。
    """
    row = _require_provider(db, provider_id)
    unknown = set(payload.roles) - set(presets.MODEL_ROLES)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未知用途: " + "、".join(sorted(unknown)),
        )

    cleaned = {key: str(value).strip() for key, value in payload.roles.items() if str(value).strip()}
    available = catalog.model_names(db, provider_id)
    if available:
        missing = [value for value in cleaned.values() if value not in available]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="这些模型不在已同步的目录里: " + "、".join(sorted(set(missing))),
            )

    extra = provider_spec.parse_extra(row.extra_json)
    extra["roles"] = cleaned
    provider_spec.update_provider(db, row, fields={"extra": extra})
    db.commit()
    db.refresh(row)
    _audit(
        http_request, db, action="llm_provider.roles_update", current_user=current_user,
        provider_id=provider_id, detail={"roles": cleaned},
    )
    return {"roles": cleaned}
