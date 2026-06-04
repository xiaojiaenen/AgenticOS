"""Pydantic schemas for website deploy requests and responses."""

from pydantic import BaseModel, Field


class DeployRequest(BaseModel):
    session_id: str
    project_slug: str
    stack: str = "vanilla"
    target_domain: str | None = None


class DeployDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    reason: str | None = None
