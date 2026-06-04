from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import AppBaseModel

_ALLOWED_THEMES = {"aurora", "sunset", "midnight"}
_ALLOWED_FORMATS = {"markdown", "html"}


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class AnnouncementItem(AppBaseModel):
    id: int
    eyebrow: str
    title: str
    subtitle: str
    body: str
    image_url: str | None = None
    content_format: str
    theme: str
    cta_label: str | None = None
    cta_link: str | None = None
    is_published: bool
    dismissible: bool
    show_once: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    active_now: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


class AnnouncementListResponse(AppBaseModel):
    items: list[AnnouncementItem]


class ActiveAnnouncementResponse(AppBaseModel):
    item: AnnouncementItem | None = None


class AnnouncementCreateRequest(BaseModel):
    eyebrow: str = Field(default="系统公告", min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=5000)
    image_url: str | None = Field(default=None, max_length=2048)
    content_format: str = Field(default="markdown", max_length=16)
    theme: str = Field(default="aurora", max_length=32)
    cta_label: str | None = Field(default=None, max_length=64)
    cta_link: str | None = Field(default=None, max_length=512)
    is_published: bool = False
    dismissible: bool = True
    show_once: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("eyebrow", "title", "subtitle", "body")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("cta_label", "cta_link", "image_url")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        theme = value.strip().lower()
        if theme not in _ALLOWED_THEMES:
            raise ValueError(f"Unsupported theme: {value}")
        return theme

    @field_validator("content_format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        content_format = value.strip().lower()
        if content_format not in _ALLOWED_FORMATS:
            raise ValueError(f"Unsupported content format: {value}")
        return content_format


class AnnouncementUpdateRequest(BaseModel):
    eyebrow: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    subtitle: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=2048)
    content_format: str | None = Field(default=None, max_length=16)
    theme: str | None = Field(default=None, max_length=32)
    cta_label: str | None = Field(default=None, max_length=64)
    cta_link: str | None = Field(default=None, max_length=512)
    is_published: bool | None = None
    dismissible: bool | None = None
    show_once: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("eyebrow", "title", "subtitle", "body")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("cta_label", "cta_link", "image_url")
    @classmethod
    def normalize_optional_link_text(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("theme")
    @classmethod
    def validate_optional_theme(cls, value: str | None) -> str | None:
        if value is None:
            return value
        theme = value.strip().lower()
        if theme not in _ALLOWED_THEMES:
            raise ValueError(f"Unsupported theme: {value}")
        return theme

    @field_validator("content_format")
    @classmethod
    def validate_optional_format(cls, value: str | None) -> str | None:
        if value is None:
            return value
        content_format = value.strip().lower()
        if content_format not in _ALLOWED_FORMATS:
            raise ValueError(f"Unsupported content format: {value}")
        return content_format


class AnnouncementGenerateRequest(BaseModel):
    brief: str = Field(..., min_length=6, max_length=1200)
    content_format: str = Field(default="markdown", max_length=16)
    theme: str = Field(default="aurora", max_length=32)
    cta_goal: str | None = Field(default=None, max_length=200)

    @field_validator("brief")
    @classmethod
    def normalize_brief(cls, value: str) -> str:
        return value.strip()

    @field_validator("cta_goal")
    @classmethod
    def normalize_cta_goal(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("theme")
    @classmethod
    def validate_generate_theme(cls, value: str) -> str:
        theme = value.strip().lower()
        if theme not in _ALLOWED_THEMES:
            raise ValueError(f"Unsupported theme: {value}")
        return theme

    @field_validator("content_format")
    @classmethod
    def validate_generate_format(cls, value: str) -> str:
        content_format = value.strip().lower()
        if content_format not in _ALLOWED_FORMATS:
            raise ValueError(f"Unsupported content format: {value}")
        return content_format


class AnnouncementGeneratedDraft(AppBaseModel):
    eyebrow: str
    title: str
    subtitle: str
    body: str
    content_format: str
    theme: str
    cta_label: str | None = None
    cta_link: str | None = None
