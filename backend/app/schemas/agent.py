from pydantic import BaseModel, Field

# 合法响应模式的单一来源，供运行时白名单（会话恢复、/v1 网关）引用。
# 曾有多处各自硬编码白名单、漏掉 office/bigdata，导致会话恢复或 API 调用
# 被静默降级成 general。下方 Pydantic 的 pattern 正则仍需同步修改，
# 两者一致性由 tests/test_agent_modes.py 守护。
RESPONSE_MODES: tuple[str, ...] = ("general", "ppt", "website", "email", "bigdata", "office")


class FileAttachment(BaseModel):
    filename: str = Field(..., description="Original filename.")
    file_path: str = Field(..., description="Server-side absolute path of the saved file.")
    rel_path: str | None = Field(
        default=None,
        description=(
            "Path relative to the session workspace (e.g. ``uploads/报告.docx``). "
            "Preferred when telling the agent where the file is: file tools resolve "
            "relative paths against the workspace, and absolute container paths "
            "would expose the deployment layout."
        ),
    )


class AgentStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message sent to the agent.")
    session_id: str | None = Field(default=None, description="Session ID reused across turns.")
    system_prompt: str | None = Field(default=None, description="System prompt used when creating a session.")
    agent_profile_id: int | None = Field(default=None, ge=1, description="Pluggable agent profile ID.")
    plan_mode: bool = Field(
        default=False,
        description="计划模式：只允许只读工具，产出可执行计划后再执行",
    )
    approval_mode: str = Field(
        default="auto",
        pattern="^(ask|auto|full)$",
        description=(
            "会话级审批模式：ask=逐次确认；auto=只读工具自动放行；"
            "full=全部放行（仅管理员生效）。"
            "默认 auto：只读操作（list_files/read_text_file 等）没有副作用，"
            "逐次确认只会让长任务点到手酸；写文件、发邮件等仍会照常询问。"
        ),
    )
    response_mode: str = Field(
        default="general",
        pattern="^(general|ppt|website|email|bigdata|office)$",
        description="Expected response mode, used as a backward-compatible fallback.",
    )
    # Accept common alias `mode` from clients/scripts so `"mode": "ppt"` works.
    mode: str | None = Field(
        default=None,
        pattern="^(general|ppt|website|email|bigdata|office)$",
        description="Alias of response_mode.",
    )
    max_steps: int | None = Field(default=None, ge=1, le=50, description="Max runtime steps for one turn.")
    parallel_tool_calls: bool | None = Field(default=None, description="Whether parallel tool calls are allowed.")
    files: list[FileAttachment] | None = Field(default=None, description="Attached files with extracted text.")
    ppt_phase: str | None = Field(
        default=None,
        pattern="^(planning|confirming|generating|done)$",
        description="PPT generation phase: 'planning' (output spec_lock), 'confirming' (wait for user), 'generating' (generate SVGs), 'done'. None for single-phase mode.",
    )

    def model_post_init(self, __context) -> None:
        if self.mode and (self.response_mode == "general" or not self.response_mode):
            self.response_mode = self.mode


class PptExportRequest(BaseModel):
    artifact_id: str = Field(..., min_length=1, description="PPT artifact ID to export as .pptx")
    canvas_format: str | None = Field(default=None, description="Canvas format key (ppt169, ppt43, etc.)")
    theme: str | None = Field(default=None, description="Theme name for SVG token resolution")
    use_native_shapes: bool = Field(default=True, description="Use native DrawingML shapes (editable in PowerPoint)")
    use_compat_mode: bool = Field(default=False, description="Embed PNG fallback for older Office versions")
    transition: str | None = Field(default=None, description="Transition effect name (fade, push, wipe, etc.)")
    animation: str | None = Field(default=None, description="Per-element entrance animation mode")
    enable_notes: bool = Field(default=True, description="Embed speaker notes from SVG data-notes")


class ApprovalDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$", description="Approval decision.")
    reason: str | None = Field(default=None, description="Reason for the decision.")
