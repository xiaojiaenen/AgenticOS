from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import (
    AgentMessageModel,
    AgentProfileAudienceModel,
    AgentSessionModel,
    AgentUsageEventModel,
    ApprovalModel,
    AuthSessionModel,
    PptArtifactModel,
    UserInstalledAgentModel,
    UserModel,
)
from app.schemas.users import UserCreateRequest, UserListItem, UserListResponse, UserStatusUpdateRequest, UserUpdateRequest
from app.services import audit_service, rate_limiter

router = APIRouter(prefix="/users", tags=["Users"])


def _audit(db: Session, request: Request, *, action: str, actor: UserModel | None, **fields) -> None:
    """用户管理的审计（端点内显式调用，不引中间件）。"""
    ctx = audit_service.request_context(request)
    try:
        audit_service.record(db, action=action, actor=actor, ip=ctx["ip"], user_agent=ctx["user_agent"], **fields)
    except Exception:  # noqa: BLE001 -- 审计异常不得让用户管理失败
        import logging

        logging.getLogger("agenticos.audit").warning("audit %s failed", action, exc_info=True)


def _to_item(user: UserModel) -> UserListItem:
    return UserListItem(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _find_user_by_email(db: Session, email: str) -> UserModel | None:
    return db.scalar(select(UserModel).where(func.lower(UserModel.email) == email.lower()))


@router.get("", response_model=UserListResponse)
def list_users(
    search: str = Query(default="", max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListResponse:
    statement = select(UserModel)
    count_statement = select(func.count(UserModel.id))
    query = search.strip().lower()
    if query:
        condition = or_(
            func.lower(UserModel.email).contains(query),
            func.lower(UserModel.name).contains(query),
        )
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    total = db.scalar(count_statement) or 0
    users = db.scalars(statement.order_by(UserModel.created_at.desc()).offset(offset).limit(limit)).all()
    return UserListResponse(items=[_to_item(user) for user in users], total=total)


@router.post("", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> UserListItem:
    existing = _find_user_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # 在线程池中执行 PBKDF2 哈希，防止阻塞事件循环
    import asyncio
    password_hash = await asyncio.to_thread(hash_password, payload.password)

    user = UserModel(
        email=payload.email,
        name=payload.name.strip(),
        password_hash=password_hash,
        role=payload.role,
        is_active=payload.is_active,
        auth_source=payload.auth_source,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # M6-C：新用户绑定默认 Casbin 角色（策略表缺失不应阻断建号）
    try:
        from app.services.permission_service import assign_default_role_for_user

        assign_default_role_for_user(user)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("agenticos.permission").warning("assign default role failed for %s", user.email, exc_info=True)

    _audit(
        db, request, action="user.create", actor=current_user,
        resource_type="user", resource_id=user.id,
        detail={"email": user.email, "role": user.role, "auth_source": user.auth_source},
    )

    # 发送欢迎邮件（异步，不阻塞响应）
    from app.core.config import get_settings
    from app.services.notification_service import send_welcome_email
    settings = get_settings()
    frontend_base = settings.get_cors_allow_origins()[0] if settings.get_cors_allow_origins() else ""
    asyncio.create_task(send_welcome_email(user.email, user.name.strip(), frontend_base))

    return _to_item(user)


@router.get("/{user_id}", response_model=UserListItem)
def get_user(
    user_id: int,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListItem:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _to_item(user)


@router.patch("/{user_id}", response_model=UserListItem)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> UserListItem:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.email is not None:
        existing = _find_user_by_email(db, payload.email)
        if existing is not None and existing.id != user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        user.email = payload.email

    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    role_changed = False
    if payload.role is not None:
        if user.id == current_user.id and payload.role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role")
        role_changed = user.role != payload.role
        user.role = payload.role
    if payload.is_active is not None:
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable yourself")
        user.is_active = payload.is_active
    if payload.auth_source is not None:
        user.auth_source = payload.auth_source

    db.add(user)
    db.commit()
    db.refresh(user)

    # M6-C：角色变更同步 Casbin（改绑 admin/user 基线角色，保留部门角色不动）
    if role_changed:
        try:
            from app.services.permission_service import assign_default_role_for_user

            assign_default_role_for_user(user)
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger("agenticos.permission").warning("sync role failed for %s", user.email, exc_info=True)

    _audit(
        db, request, action="user.update", actor=current_user,
        resource_type="user", resource_id=user.id,
        # password 字段由 audit_service 脱敏为 "***"
        detail=payload.model_dump(exclude_none=True),
    )
    return _to_item(user)


@router.patch("/{user_id}/status", response_model=UserListItem)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> UserListItem:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable yourself")

    user.is_active = payload.is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    _audit(
        db, request, action="user.status_change", actor=current_user,
        resource_type="user", resource_id=user.id, detail={"is_active": payload.is_active},
    )
    return _to_item(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> None:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete yourself")

    deleted_email = user.email
    _audit(
        db, request, action="user.delete", actor=current_user,
        resource_type="user", resource_id=user_id, detail={"email": deleted_email},
    )

    session_ids = [row[0] for row in db.execute(
        select(AgentSessionModel.session_id).where(AgentSessionModel.user_id == user_id)
    ).all()]

    if session_ids:
        db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id.in_(session_ids)))
        db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.session_id.in_(session_ids)))
        db.execute(delete(ApprovalModel).where(ApprovalModel.session_id.in_(session_ids)))
        db.execute(delete(PptArtifactModel).where(PptArtifactModel.session_id.in_(session_ids)))
        db.execute(delete(AgentSessionModel).where(AgentSessionModel.user_id == user_id))

    db.execute(delete(UserInstalledAgentModel).where(UserInstalledAgentModel.user_id == user_id))
    db.execute(delete(AgentProfileAudienceModel).where(AgentProfileAudienceModel.user_id == user_id))
    db.execute(delete(AuthSessionModel).where(AuthSessionModel.user_id == user_id))
    # 登录限流已迁至 Redis（rate_limiter），按 email 清除全部 IP 维度的限流状态
    rate_limiter.clear_rate_limit_by_email(get_settings(), "login", email=user.email)
    db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id == user_id))

    db.delete(user)
    db.commit()
