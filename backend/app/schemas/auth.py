from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserPublic(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    auth_source: str = "local"
    #: 该角色拥有的能力位（见 app/core/roles.py）。前端按能力决定显示什么，
    #: 不再硬编码 `role === 'admin'` —— 这样加角色不用改前端。
    #: 默认空列表以兼容老客户端的反序列化（它们会忽略这个字段）。
    capabilities: list[str] = Field(default_factory=list)


class AuthRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)

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


class AuthLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class SendCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    purpose: str = Field(..., pattern="^(login|register)$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginWithCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    code: str = Field(..., min_length=6, max_length=6)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RegisterWithCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)
    code: str = Field(..., min_length=6, max_length=6)

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
