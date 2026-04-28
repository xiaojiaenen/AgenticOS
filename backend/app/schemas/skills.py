from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SkillBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower().replace(" ", "-")


class SkillCreateRequest(SkillBase):
    instruction: str = Field(..., min_length=1, max_length=50000)

    @field_validator("instruction")
    @classmethod
    def strip_instruction(cls, value: str) -> str:
        return value.strip()


class SkillUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    instruction: str | None = Field(default=None, min_length=1, max_length=50000)

    @field_validator("name", "description", "instruction")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower().replace(" ", "-")


class SkillResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    enabled: bool
    instruction: str
    root_dir: str
    has_python_scripts: bool
    script_paths: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SkillListResponse(BaseModel):
    items: list[SkillResponse]
