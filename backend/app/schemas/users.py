from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import AppBaseModel


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserListItem(AppBaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


class UserListResponse(AppBaseModel):
    items: list[UserListItem]
    total: int


class UserCreateRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)
    #: 角色白名单见 app/core/roles.py（端点校验并给可读报错）
    role: str = Field(default="user", max_length=32)
    is_active: bool = True
    auth_source: str = Field(default="local", pattern="^(local|ldap)$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("邮箱格式不正确")
        return email

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    #: 角色白名单在 `app/core/roles.py`（VALID_ROLES）里统一维护，端点负责校验
    #: 并给出「未知角色」这种可读报错。这里**不再**用正则枚举 —— 早先写死的
    #: `^(admin|user)$` 会让新增的 operator/auditor/superadmin 在 422 处就被拒，
    #: 而且每加一个角色都要回来改一次 schema。
    role: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    auth_source: str | None = Field(default=None, pattern="^(local|ldap)$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        email = value.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("邮箱格式不正确")
        return email

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class UserStatusUpdateRequest(BaseModel):
    is_active: bool = Field(..., description="Whether the user can sign in and use the system.")
