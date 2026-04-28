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
    role: str = Field(default="user", pattern="^(admin|user)$")
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("Invalid email address")
        return email

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        email = value.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("Invalid email address")
        return email

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class UserStatusUpdateRequest(BaseModel):
    is_active: bool = Field(..., description="Whether the user can sign in and use the system.")
