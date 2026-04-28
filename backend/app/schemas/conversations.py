from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.base import AppBaseModel


class ConversationListItem(AppBaseModel):
    session_id: str
    user_id: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    summary: str | None = None
    first_message: str | None = None
    last_message: str | None = None
    message_count: int
    model_names: list[str]
    total_tokens: int
    input_tokens: int
    output_tokens: int
    llm_calls: int
    tool_calls: int
    avg_latency_ms: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationListResponse(AppBaseModel):
    items: list[ConversationListItem]
    total: int


class ConversationDetailMessage(AppBaseModel):
    id: int
    role: str | None = None
    text: str = ""
    created_at: datetime | None = None


class ConversationDetailResponse(AppBaseModel):
    session_id: str
    user_id: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    summary: str | None = None
    message_count: int
    model_names: list[str]
    total_tokens: int
    input_tokens: int
    output_tokens: int
    llm_calls: int
    tool_calls: int
    avg_latency_ms: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[ConversationDetailMessage]
