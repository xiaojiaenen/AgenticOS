from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.timezone import APP_TIMEZONE, app_now, to_app_timezone


class AppDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None

        normalized = to_app_timezone(value)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=APP_TIMEZONE)
        return value.astimezone(APP_TIMEZONE)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class UserEmailCredentialsModel(Base):
    __tablename__ = "user_email_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    email_address: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(String(512))
    imap_host: Mapped[str] = mapped_column(String(255))
    imap_port: Mapped[int] = mapped_column(Integer)
    imap_ssl: Mapped[bool] = mapped_column(Boolean)
    smtp_host: Mapped[str] = mapped_column(String(255))
    smtp_port: Mapped[int] = mapped_column(Integer)
    smtp_ssl: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(AppDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    last_seen_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AuthRateLimitModel(Base):
    __tablename__ = "auth_rate_limits"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    blocked_until: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentSessionModel(Base):
    __tablename__ = "agent_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_profile_id: Mapped[int | None] = mapped_column(ForeignKey("agent_profiles.id"), nullable=True, index=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    max_steps: Mapped[int] = mapped_column(Integer, default=10)
    parallel_tool_calls: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    last_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    last_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    last_llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentUsageEventModel(Base):
    __tablename__ = "agent_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_profile_id: Mapped[int | None] = mapped_column(ForeignKey("agent_profiles.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    response_mode: Mapped[str] = mapped_column(String(32), default="general", index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_names_json: Mapped[str] = mapped_column(Text, default="[]")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, index=True)


class AgentToolConfigModel(Base):
    __tablename__ = "agent_tool_configs"
    __table_args__ = (UniqueConstraint("mode", "tool_name", name="uq_agent_tool_mode_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(32), index=True)
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_sub_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentProfileModel(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text)
    response_mode: Mapped[str] = mapped_column(String(32), default="general", index=True)
    avatar: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    listed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    max_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentProfileToolModel(Base):
    __tablename__ = "agent_profile_tools"
    __table_args__ = (UniqueConstraint("profile_id", "tool_name", name="uq_agent_profile_tool"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_sub_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class SkillModel(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    root_dir: Mapped[str] = mapped_column(String(767), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentProfileSkillModel(Base):
    __tablename__ = "agent_profile_skills"
    __table_args__ = (UniqueConstraint("profile_id", "skill_id", name="uq_agent_profile_skill"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class UserInstalledAgentModel(Base):
    __tablename__ = "user_installed_agents"
    __table_args__ = (UniqueConstraint("user_id", "profile_id", name="uq_user_installed_agent"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    installed_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class AgentProfileAudienceModel(Base):
    __tablename__ = "agent_profile_audiences"
    __table_args__ = (UniqueConstraint("profile_id", "user_id", name="uq_agent_profile_audience"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class AgentMessageModel(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (Index("ix_agent_messages_session_created", "session_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    message_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class ApprovalModel(Base):
    __tablename__ = "agent_approvals"
    __table_args__ = (Index("ix_agent_approvals_session_status", "session_id", "status"),)

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    decided_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)


class PptArtifactModel(Base):
    __tablename__ = "ppt_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256))
    slide_count: Mapped[int] = mapped_column(Integer, default=0)
    deck_json: Mapped[str] = mapped_column(Text)
    preview_html: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class AnnouncementModel(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        Index("ix_announcements_publish_window", "is_published", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eyebrow: Mapped[str] = mapped_column(String(80), default="系统公告")
    title: Mapped[str] = mapped_column(String(160))
    subtitle: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_format: Mapped[str] = mapped_column(String(16), default="markdown")
    theme: Mapped[str] = mapped_column(String(32), default="aurora", index=True)
    cta_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cta_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dismissible: Mapped[bool] = mapped_column(Boolean, default=True)
    show_once: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class WebsiteDeployModel(Base):
    __tablename__ = "website_deploys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    project_slug: Mapped[str] = mapped_column(String(128))
    stack: Mapped[str] = mapped_column(String(16))
    dist_path: Mapped[str] = mapped_column(String(512))
    target_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deploy_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class MemoryModel(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    memory_type: Mapped[str] = mapped_column(String(32), default="fact")
    importance: Mapped[float] = mapped_column(default=0.5)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="auto")  # auto / manual / tool
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


# ---------------------------------------------------------------------------
# External system integration
# ---------------------------------------------------------------------------


class ExternalSystemModel(Base):
    __tablename__ = "external_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)  # 预设分类，见 INTEGRATION_CATEGORIES
    base_url: Mapped[str] = mapped_column(String(512))
    auth_type: Mapped[str] = mapped_column(String(32))  # api_key / bearer / basic / oauth2 / custom
    credential_template_json: Mapped[str] = mapped_column(Text, default="{}")  # user credential field definitions
    oauth_client_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_client_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_auth_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    oauth_token_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    oauth_scope: Mapped[str | None] = mapped_column(String(512), nullable=True)
    oauth_refresh_token_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jwt_login_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jwt_refresh_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jwt_refresh_body_template: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. {"grant_type":"refresh_token","refresh_token":"{refresh_token}"}
    jwt_refresh_token_path: Mapped[str | None] = mapped_column(String(256), nullable=True)  # e.g. data.refresh_token
    advanced_auth_json: Mapped[str] = mapped_column(Text, default="{}")  # sign/encrypt/decrypt config
    jwt_request_body_template: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. {"username":"{username}","password":"{password}"}
    jwt_response_token_path: Mapped[str | None] = mapped_column(String(256), nullable=True)  # e.g. data.access_token
    jwt_response_expires_path: Mapped[str | None] = mapped_column(String(256), nullable=True)  # e.g. data.expires_in
    jwt_response_token_header: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. dinky-token (Sa-Token style)
    login_token_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # header / body (default: body)
    login_inject_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # bearer / header (default: bearer)
    login_inject_header_name: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. dinky-token, Cookie, X-Auth-Token
    headers_json: Mapped[str] = mapped_column(Text, default="{}")  # extra fixed headers
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class ExternalUserCredentialModel(Base):
    __tablename__ = "external_user_credentials"
    __table_args__ = (UniqueConstraint("user_id", "system_id", name="uq_user_ext_credential"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("external_systems.id"), index=True)
    credential_data_encrypted: Mapped[str] = mapped_column(Text, default="")
    oauth_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_expires_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    cached_jwt_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    jwt_expires_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="connected", index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class ExternalApiModel(Base):
    __tablename__ = "external_apis"
    __table_args__ = (UniqueConstraint("system_id", "name", name="uq_external_api_system_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("external_systems.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))  # tool function name, e.g. jira_create_issue
    display_name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(String(8))  # GET / POST / PUT / DELETE / PATCH
    path: Mapped[str] = mapped_column(String(512))  # relative path, e.g. /rest/api/2/issue
    request_body_schema: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON Schema
    response_example: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class ExternalApiParamModel(Base):
    __tablename__ = "external_api_params"
    __table_args__ = (UniqueConstraint("api_id", "name", name="uq_external_param_api_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_id: Mapped[int] = mapped_column(ForeignKey("external_apis.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    param_type: Mapped[str] = mapped_column(String(16))  # path / query / body
    data_type: Mapped[str] = mapped_column(String(16), default="string")  # string / integer / boolean / object
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentProfileExternalSystemModel(Base):
    __tablename__ = "agent_profile_external_systems"
    __table_args__ = (UniqueConstraint("profile_id", "system_id", name="uq_profile_ext_system"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("external_systems.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)
