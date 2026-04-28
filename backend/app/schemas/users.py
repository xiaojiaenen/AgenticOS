from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserListItem(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserListItem]
    total: int


class UserStatusUpdateRequest(BaseModel):
    is_active: bool = Field(..., description="Whether the user can sign in and use the system.")
