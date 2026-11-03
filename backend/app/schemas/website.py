"""Pydantic schemas for website deploy requests and responses."""

from pydantic import BaseModel, Field


class DeployRequest(BaseModel):
    session_id: str
    project_slug: str
    stack: str = "vanilla"
    target_domain: str | None = None
    # 作品库可见性：public = 审批后发布到 /sites/ 对外可见；
    # private（默认）= 仅部署者与管理员在作品库可见，走带签名私有端点
    visibility: str = Field(default="private", pattern="^(public|private)$")


class DeployDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    reason: str | None = None
