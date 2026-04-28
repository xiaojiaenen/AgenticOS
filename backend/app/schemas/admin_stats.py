from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_users: int
    active_users: int
    total_sessions: int
    total_runs: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    llm_calls: int
    tool_calls: int
    avg_latency_ms: int


class DashboardTrendPoint(BaseModel):
    date: str
    runs: int
    tokens: int
    tool_calls: int


class DashboardDistributionItem(BaseModel):
    name: str
    value: int


class DashboardUserUsage(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    is_active: bool
    sessions: int
    runs: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    llm_calls: int
    tool_calls: int
    avg_latency_ms: int


class DashboardStatsResponse(BaseModel):
    summary: DashboardSummary
    trend: list[DashboardTrendPoint]
    model_distribution: list[DashboardDistributionItem]
    tool_distribution: list[DashboardDistributionItem]
    user_usage: list[DashboardUserUsage]
