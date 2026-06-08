from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.security import hash_password
from app.db.models import (
    AgentMessageModel,
    AgentProfileAudienceModel,
    AgentSessionModel,
    AgentUsageEventModel,
    ApprovalModel,
    AuthSessionModel,
    AuthRateLimitModel,
    PptArtifactModel,
    UserInstalledAgentModel,
    UserModel,
)
from app.schemas.users import UserCreateRequest, UserListItem, UserListResponse, UserStatusUpdateRequest, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


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
    request: UserCreateRequest,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListItem:
    existing = _find_user_by_email(db, request.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = UserModel(
        email=request.email,
        name=request.name.strip(),
        password_hash=hash_password(request.password),
        role=request.role,
        is_active=request.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 发送欢迎邮件（异步，不阻塞响应）
    import asyncio
    from app.core.config import get_settings
    from app.services.notification_service import send_welcome_email
    settings = get_settings()
    frontend_base = settings.get_cors_allow_origins()[0] if settings.get_cors_allow_origins() else ""
    asyncio.create_task(send_welcome_email(request.email, request.name.strip(), frontend_base))

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
    request: UserUpdateRequest,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListItem:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request.email is not None:
        existing = _find_user_by_email(db, request.email)
        if existing is not None and existing.id != user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        user.email = request.email

    if request.name is not None:
        user.name = request.name.strip()
    if request.password is not None:
        user.password_hash = hash_password(request.password)
    if request.role is not None:
        if user.id == current_user.id and request.role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role")
        user.role = request.role
    if request.is_active is not None:
        if user.id == current_user.id and not request.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable yourself")
        user.is_active = request.is_active

    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_item(user)


@router.patch("/{user_id}/status", response_model=UserListItem)
def update_user_status(
    user_id: int,
    request: UserStatusUpdateRequest,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListItem:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id and not request.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable yourself")

    user.is_active = request.is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_item(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete yourself")

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
    db.execute(
        delete(AuthRateLimitModel).where(
            AuthRateLimitModel.key.startswith(f"login:{user.email}:")
        )
    )
    db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id == user_id))

    db.delete(user)
    db.commit()
