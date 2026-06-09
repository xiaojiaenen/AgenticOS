from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import AppBaseModel
from app.schemas.tool_config import ToolCatalogItem


class AgentProfileTool(BaseModel):
    tool_name: str
    enabled: bool
    requires_approval: bool
    approval_sub_tools: list[str] = Field(default_factory=list)


class AgentProfileSkillReference(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    enabled: bool
    has_python_scripts: bool
    script_paths: list[str] = Field(default_factory=list)
    has_references: bool
    reference_paths: list[str] = Field(default_factory=list)


class AgentProfileAudienceUser(BaseModel):
    id: int
    name: str
    email: str


class AgentProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    system_prompt: str = Field(..., min_length=1, max_length=12000)
    response_mode: str = Field(default="general", pattern="^(general|ppt|website|bigdata)$")
    avatar: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    listed: bool = False
    max_steps: int | None = Field(default=None, ge=1, le=2147483647)
    audience_mode: str = Field(default="all", pattern="^(all|selected)$")
    audience_user_ids: list[int] = Field(default_factory=list)

    @field_validator("name", "description", "system_prompt", "avatar")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower().replace(" ", "-")


class AgentProfileExternalSystemRef(BaseModel):
    system_id: int
    enabled: bool = True


class AgentProfileCreateRequest(AgentProfileBase):
    tools: list[AgentProfileTool] = Field(default_factory=list)
    skill_ids: list[int] = Field(default_factory=list)
    external_systems: list[AgentProfileExternalSystemRef] = Field(default_factory=list)


class AgentProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=12000)
    response_mode: str | None = Field(default=None, pattern="^(general|ppt|website|bigdata)$")
    avatar: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    listed: bool | None = None
    max_steps: int | None = Field(default=None, ge=1, le=2147483647)
    audience_mode: str | None = Field(default=None, pattern="^(all|selected)$")
    audience_user_ids: list[int] | None = None
    tools: list[AgentProfileTool] | None = None
    skill_ids: list[int] | None = None
    external_systems: list[AgentProfileExternalSystemRef] | None = None

    @field_validator("name", "description", "system_prompt", "avatar")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower().replace(" ", "-")


class AgentProfileExternalSystemInfo(BaseModel):
    system_id: int
    system_name: str
    enabled: bool


class AgentProfileResponse(AppBaseModel):
    id: int
    name: str
    slug: str
    description: str
    system_prompt: str
    response_mode: str
    avatar: str | None
    enabled: bool
    listed: bool
    is_builtin: bool
    installed: bool = False
    max_steps: int | None = None
    audience_mode: str
    audience_users: list[AgentProfileAudienceUser] = Field(default_factory=list)
    tools: list[AgentProfileTool]
    skills: list[AgentProfileSkillReference] = Field(default_factory=list)
    external_systems: list[AgentProfileExternalSystemInfo] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AgentProfileListResponse(AppBaseModel):
    catalog: list[ToolCatalogItem]
    available_skills: list[AgentProfileSkillReference] = Field(default_factory=list)
    items: list[AgentProfileResponse]
