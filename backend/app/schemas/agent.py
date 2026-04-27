from pydantic import BaseModel, Field


class AgentStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户发送给智能体的消息。")
    session_id: str | None = Field(default=None, description="多轮对话复用的会话 ID。")
    system_prompt: str | None = Field(default=None, description="新建会话时使用的系统提示词。")
    response_mode: str = Field(
        default="general",
        pattern="^(general|ppt|website)$",
        description="前端期望的响应模式，用于后端决定是否拦截结构化制品。",
    )
    max_steps: int | None = Field(default=None, ge=1, le=50, description="智能体单轮运行的最大步骤数。")
    parallel_tool_calls: bool | None = Field(
        default=None,
        description="是否允许并行执行多个工具调用。",
    )


class ApprovalDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$", description="审批结果。")
    reason: str | None = Field(default=None, description="拒绝或批准的说明。")
