from __future__ import annotations

from pydantic import BaseModel, Field


class SubToolInfo(BaseModel):
    name: str
    label: str
    description: str


class ToolCatalogItem(BaseModel):
    name: str
    label: str
    description: str
    approval_scope: list[str]
    sub_tools: list[SubToolInfo]


class AgentModeToolConfig(BaseModel):
    mode: str
    tool_name: str
    enabled: bool
    requires_approval: bool
    approval_sub_tools: list[str] = Field(default_factory=list)


class AgentModeConfig(BaseModel):
    mode: str
    label: str
    description: str
    tools: list[AgentModeToolConfig]


class ToolConfigResponse(BaseModel):
    catalog: list[ToolCatalogItem]
    modes: list[AgentModeConfig]


class ToolConfigUpdateItem(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=64)
    enabled: bool
    requires_approval: bool
    approval_sub_tools: list[str] = Field(default_factory=list)


class ModeToolConfigUpdateRequest(BaseModel):
    tools: list[ToolConfigUpdateItem]
