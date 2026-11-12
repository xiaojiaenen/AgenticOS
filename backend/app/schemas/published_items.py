"""文件型作品发布（PPT / 文档 / 表格）的请求模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PublishedItemPublishRequest(BaseModel):
    kind: str = Field(..., pattern="^(ppt|document|sheet)$", description="产物类型")
    session_id: str = Field(..., min_length=1, max_length=128)
    source_ref: str = Field(..., min_length=1, max_length=160, description="artifact_id 或版本目录名")
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)


class PublishedItemDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    reason: str | None = Field(default=None, max_length=1000)


class PublishedItemListResponse(BaseModel):
    items: list[dict]
