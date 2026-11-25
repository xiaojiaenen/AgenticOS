"""网站应用化平台的请求体 schema（docs/research/网站应用化设计.md）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppCreateRequest(BaseModel):
    """管理员创建应用：slug 是数据端点路径里的稳定标识。"""

    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")


class ManifestSubmitRequest(BaseModel):
    """提交新版本 manifest（候选版本），服务端生成 plan 进审批队列。"""

    manifest: dict[str, Any]


class ManifestApproveRequest(BaseModel):
    """批准候选版本：approved_paths 为空/缺省 = 全部批准；指定 = 逐项收紧。

    只有 plan 里的 ``!`` 风险项看路径 —— 未批准的风险项回退旧值（5.4）。
    """

    approved_paths: list[str] | None = None


class ManifestRejectRequest(BaseModel):
    reason: str | None = None


class MemberRolesRequest(BaseModel):
    """设置应用内角色（只能授予 manifest.auth.roles 声明过的角色）。"""

    roles: list[str] = Field(default_factory=list)


class AppLoginRequest(BaseModel):
    """应用终端用户登录（应用级，与平台账号无关）。"""

    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AppSignupRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class ManifestDraftRequest(BaseModel):
    """AI 生成 manifest 草稿的入参：业务描述（非字段级 JSON）。"""

    brief: str = Field(min_length=2, max_length=4000, description="业务描述（自然语言）")


class ManifestDraftResponse(BaseModel):
    requirements_md: str = ""
    manifest: dict[str, Any]
