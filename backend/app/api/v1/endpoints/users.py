from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.db.models import UserModel
from app.schemas.users import UserListItem, UserListResponse, UserStatusUpdateRequest

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
