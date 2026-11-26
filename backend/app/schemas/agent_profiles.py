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
    response_mode: str = Field(default="general", pattern="^(general|ppt|website|email|bigdata|office)$")
    avatar: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    listed: bool = False
    max_steps: int | None = Field(default=None, ge=1, le=2147483647)
    audience_mode: str = Field(default="all", pattern="^(all|selected|none)$")
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
    knowledge_base_ids: list[int] = Field(default_factory=list, description="绑定的知识库白名单，空=不限制")
    external_systems: list[AgentProfileExternalSystemRef] = Field(default_factory=list)
    # private=仅自己可用（用户自建默认）；public=可出现在商店供他人安装（管理员发布用）
    visibility: str = Field(default="private", pattern="^(private|public)$")


class AgentProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=12000)
    response_mode: str | None = Field(default=None, pattern="^(general|ppt|website|email|bigdata|office)$")
    avatar: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    listed: bool | None = None
    max_steps: int | None = Field(default=None, ge=1, le=2147483647)
    audience_mode: str | None = Field(default=None, pattern="^(all|selected|none)$")
    audience_user_ids: list[int] | None = None
    tools: list[AgentProfileTool] | None = None
    skill_ids: list[int] | None = None
    knowledge_base_ids: list[int] | None = None
    external_systems: list[AgentProfileExternalSystemRef] | None = None
    visibility: str | None = Field(default=None, pattern="^(private|public)$")

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
    #: 内置智能体是否被人工改过（服务层已返回，响应模型曾漏声明导致前端拿不到）
    customized: bool = False
    installed: bool = False
    owner_id: int | None = None
    """是否由当前请求用户拥有（前端据此显示编辑/删除入口）"""
    is_owner: bool = False
    #: 实际所有者（`owner_id` 指向的用户）的姓名/邮箱 —— 后台目录要显示
    #: "这个智能体是谁建的"。内置智能体为 None。
    owner_name: str | None = None
    owner_email: str | None = None
    #: 创建人（`created_by`）：用户自建时与 owner 通常一致；内置/导入的智能体
    #: 可能是创建它那次操作的管理员。None = 平台内置。
    created_by_name: str | None = None
    #: 这个智能体是否**不受工具策略限制**（平台内置 / 管理员自建）。
    #: 前端据此决定编辑器里要不要显示受限工具 —— 与运行期用的是同一个判断
    #: （`_is_privileged_profile`），避免"界面藏了但运行时给用"的不一致。
    tools_unrestricted: bool = False
    visibility: str = "private"
    max_steps: int | None = None
    audience_mode: str
    knowledge_base_ids: list[int] = Field(default_factory=list)
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
