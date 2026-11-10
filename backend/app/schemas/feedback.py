from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import AppBaseModel

IssueType = Literal["bug", "feature", "question", "other"]
IssueStatus = Literal["open", "confirmed", "in_progress", "resolved", "shipped", "closed"]
IssuePriority = Literal["low", "medium", "high"]
IssueVisibility = Literal["public", "private"]


class FeedbackAuthor(AppBaseModel):
    id: int
    name: str
    role: str


class FeedbackIssueItem(AppBaseModel):
    id: int
    type: IssueType
    title: str
    body: str
    status: IssueStatus
    priority: IssuePriority
    visibility: IssueVisibility
    author: FeedbackAuthor
    vote_count: int
    comment_count: int
    my_vote: bool = False
    context: dict[str, Any] = Field(default_factory=dict)
    resolution_note: str | None = None
    shipped_version: str | None = None
    resolved_by: FeedbackAuthor | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FeedbackIssueListResponse(AppBaseModel):
    items: list[FeedbackIssueItem]
    total: int
    page: int
    page_size: int


class FeedbackCommentItem(AppBaseModel):
    id: int
    issue_id: int
    author: FeedbackAuthor | None = None
    body: str
    is_official: bool
    is_system: bool
    created_at: datetime


class FeedbackIssueDetail(AppBaseModel):
    issue: FeedbackIssueItem
    comments: list[FeedbackCommentItem]


class FeedbackStatsResponse(AppBaseModel):
    total: int
    open: int
    in_progress: int
    resolved: int
    shipped: int
    closed: int
    resolved_this_week: int
    created_this_week: int
    avg_resolve_hours: float | None = None
    resolve_rate: float


class FeedbackCreateRequest(BaseModel):
    type: IssueType = "feature"
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=10000)
    visibility: IssueVisibility = "public"
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标题不能为空")
        return v


class FeedbackCommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def _strip_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("评论内容不能为空")
        return v


class FeedbackStatusUpdateRequest(BaseModel):
    status: IssueStatus
    priority: IssuePriority | None = None
    resolution_note: str | None = Field(default=None, max_length=5000)
    shipped_version: str | None = Field(default=None, max_length=64)
