from pydantic import BaseModel, Field


class FileAttachment(BaseModel):
    filename: str = Field(..., description="Original filename.")
    text_content: str = Field(..., description="Text content extracted from the file.")


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
    files: list[FileAttachment] | None = Field(default=None, description="Attached files with extracted text.")


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
