from pydantic import BaseModel, Field


class AgentStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message sent to the agent.")
    session_id: str | None = Field(default=None, description="Session ID reused across turns.")
    system_prompt: str | None = Field(default=None, description="System prompt used when creating a session.")
    agent_profile_id: int | None = Field(default=None, ge=1, description="Pluggable agent profile ID.")
    response_mode: str = Field(
        default="general",
        pattern="^(general|ppt|website)$",
        description="Expected response mode, used as a backward-compatible fallback.",
    )
    max_steps: int | None = Field(default=None, ge=1, le=50, description="Max runtime steps for one turn.")
    parallel_tool_calls: bool | None = Field(default=None, description="Whether parallel tool calls are allowed.")


class ApprovalDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$", description="Approval decision.")
    reason: str | None = Field(default=None, description="Reason for the decision.")
