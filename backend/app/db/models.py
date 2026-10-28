from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.mysql import LONGTEXT

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
    auth_source: Mapped[str] = mapped_column(String(32), default="local", server_default="local")
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class UserEmailCredentialsModel(Base):
    __tablename__ = "user_email_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    email_address: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(String(512), comment="已弃用，使用 password_encrypted")
    password_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True, comment="Fernet 加密的密码")
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
    """已由 Redis 限流取代（app/services/rate_limiter.py），保留一版后废弃。"""

    __tablename__ = "auth_rate_limits"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    blocked_until: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentSessionModel(Base):
    __tablename__ = "agent_sessions"
    # M6-A3：会话列表按 user_id 过滤 + updated_at 倒序（list_user_sessions），
    # 复合索引让过滤与排序共用一次索引扫描；user_id 单列索引保留不动
    __table_args__ = (Index("ix_agent_sessions_user_updated", "user_id", "updated_at"),)

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
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now, index=True)


class AgentUsageEventModel(Base):
    __tablename__ = "agent_usage_events"
    # dashboard 核心查询（按用户/会话聚合 + 按时间窗口扫描）复合索引。
    #
    # 注意：这里曾经写了两组 ``__table_args__``（``ix_agent_usage_events_*`` 与
    # ``ix_usage_*``，字段完全相同）。Python 类里后定义的属性直接覆盖前面的，
    # 结果是第一组在 ORM 侧完全失效 —— 改它不会产生任何效果，也不报错。
    # 现在合并成一组；DB 里那对重复索引由迁移 0014 清掉。
    __table_args__ = (
        Index("ix_agent_usage_events_user_created", "user_id", "created_at"),
        Index("ix_agent_usage_events_session_created", "session_id", "created_at"),
    )

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

    # ── 审计维度：这次请求实际走了哪条路由 ──
    # 这些列**只用于审计**，不参与用量归属。归属永远是 ``user_id``（发起人）：
    # 凭据是系统级共享池，一个号被多人共用，按账号统计出来的 token 数对谁
    # 都不成立。放在同一行只是为了让「谁用的 / 走的哪条凭据 / 哪个模型」
    # 能在一次查询里对上，不用再去 join 日志。
    #
    # ``credential_id`` 刻意不加外键：凭据会被删除（换账号、Key 泄露后轮换），
    # 而用量是历史事实，不能因为删了个账号就让历史统计悬挂或级联消失。
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    provider_slug: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    credential_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    account_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # True 表示这行 token 数是按字符数估的（上游没回流 usage），统计口径要能
    # 区分开，否则「实际计费」和「估算值」混在一张图里谁也不信。
    #
    # server_default 用 ``text("0")`` 而不是字符串 "0"：后者会渲染成
    # ``DEFAULT '0'``，SQLite 存文本，ORM 的 Boolean 做 ``bool('0')`` 得到 True
    # —— 存量行会被全部误判成「已估算」。
    tokens_estimated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0")
    )

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
    # 所有者：NULL = 平台内置（任何角色都不可删改）；有值 = 该用户自建，仅本人与管理员可管理
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # private = 仅自己可见可用；public = 可出现在商店供他人安装
    visibility: Mapped[str] = mapped_column(String(16), default="private", index=True)
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

    # 资产化扩展（schema 演进由 alembic 负责，见 backend/alembic/）
    version: Mapped[int] = mapped_column(default=1)
    trigger_patterns_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private", index=True)  # private / team / restricted


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
    __table_args__ = (
        Index("ix_agent_messages_session_created", "session_id", "created_at"),
        # M6-A3：会话历史按 id 升序分页（offset/limit），(session_id, id) 可直接走索引
        Index("ix_agent_messages_session_ord", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    message_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"))
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, index=True)


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
    deck_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"))
    preview_html: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class MCPServerModel(Base):
    """MCP 服务器配置（管理员维护，供 Agent 发现并调用外部工具）"""

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # stdio | http | sse
    transport: Mapped[str] = mapped_column(String(16), default="http", index=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    command: Mapped[str | None] = mapped_column(String(256), nullable=True)
    args_json: Mapped[str] = mapped_column(Text, default="[]")
    env_json: Mapped[str] = mapped_column(Text, default="{}")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    timeout: Mapped[float] = mapped_column(default=60.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # ── 内网接入选项（爬虫类 MCP 服务常用）────────────────────────────
    # 内网服务多为自签证书；官方 SDK 的 create_mcp_http_client 不暴露
    # verify 参数，只能在平台侧自建 httpx 客户端时传入。
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    # 出网网段白名单（逗号分隔 CIDR）。MCP 服务本身可能要去访问内网站点，
    # 这时 SSRF 风险在 MCP 服务侧，平台无法代管；本字段用于**平台连 MCP
    # 服务**这一跳的地址校验（空 = 不限制，仅对管理员配置的地址生效）。
    allowed_cidrs: Mapped[str] = mapped_column(Text, default="")
    # 该 MCP 服务是否允许被普通（非管理员）智能体使用。
    # 内网爬虫类服务默认 false —— 必须在 profile 上显式授权。
    user_accessible: Mapped[bool] = mapped_column(Boolean, default=True)
    # 凭据来源：指向一个已配置的「集成」，用户在该集成下配置的凭据
    # 会在调用本 MCP 工具时按 $CREDENTIAL.<字段> 注入（值不进模型上下文）。
    # 为空表示本服务不接收凭据注入。
    external_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("external_systems.id"), nullable=True, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AgentProfileMCPServerModel(Base):
    """智能体 profile ↔ MCP 服务器授权。

    MCP 工具此前是**全局注册**到所有 Agent 的（factory.py 里无条件
    register），没有 profile 级授权 —— 这跟外部系统（agent_profile_external_systems）
    的模型不一致。内网爬虫这类 MCP 服务必须限定在指定智能体上。
    """

    __tablename__ = "agent_profile_mcp_servers"
    __table_args__ = (UniqueConstraint("profile_id", "server_name", name="uq_profile_mcp_server"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    server_name: Mapped[str] = mapped_column(String(120), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class VideoArtifactModel(Base):
    __tablename__ = "video_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    video_path: Mapped[str] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[float] = mapped_column(Float, default=0)
    resolution: Mapped[str] = mapped_column(String(32), default="1920x1080")
    fps: Mapped[int] = mapped_column(Integer, default=30)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_soundtrack: Mapped[bool] = mapped_column(Boolean, default=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
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


class ApiKeyModel(Base):
    """供外部软件调用 OpenAI 兼容网关（/v1/*）的 API Key（sk-agenticos-*）。"""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    prefix: Mapped[str] = mapped_column(String(32), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class WebsiteDeployModel(Base):
    __tablename__ = "website_deploys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    project_slug: Mapped[str] = mapped_column(String(128), index=True)
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
    """L1: Atom 事实层（向后兼容旧表）"""
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

    # 分层蒸馏扩展字段（schema 演进由 alembic 负责，见 backend/alembic/）
    layer: Mapped[str] = mapped_column(String(8), default="L1", index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("memory_scenarios.id"), nullable=True, index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True, index=True)
    access_count: Mapped[int] = mapped_column(default=0)
    visibility: Mapped[str] = mapped_column(String(16), default="private", index=True)  # private / team / restricted

    # 知识库扩展字段
    scope: Mapped[str] = mapped_column(String(10), default="user", index=True)  # user / org
    knowledge_base_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    authority_level: Mapped[str] = mapped_column(String(10), default="L1", index=True)  # L3 / L2 / L1 / L0


class MemoryConversationModel(Base):
    """L0: 原始对话完整留存（用于回溯、审计、重新蒸馏）"""
    __tablename__ = "memory_conversations"
    __table_args__ = (
        Index("ix_mem_conv_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_message: Mapped[str] = mapped_column(Text)
    assistant_message: Mapped[str] = mapped_column(Text)
    tokens_used: Mapped[int] = mapped_column(default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")  # 模式、工具调用摘要
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, index=True)


class MemoryScenarioModel(Base):
    """L2: 场景块（围绕项目/主题聚合）"""
    __tablename__ = "memory_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    atom_ids_json: Mapped[str | None] = mapped_column(Text)  # [1,2,3]
    conversation_ids_json: Mapped[str | None] = mapped_column(Text)  # 来源 L0
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_accessed_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, index=True)
    access_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class MemoryPersonaModel(Base):
    """L3: 用户长期画像（跨场景稳定模式）"""
    __tablename__ = "memory_personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    identity_json: Mapped[str] = mapped_column(Text, default="{}")
    preferences_json: Mapped[str] = mapped_column(Text, default="{}")
    tech_stack_json: Mapped[str] = mapped_column(Text, default="[]")
    goals_json: Mapped[str] = mapped_column(Text, default="[]")
    projects_json: Mapped[str] = mapped_column(Text, default="[]")
    version: Mapped[int] = mapped_column(default=1)
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
    default_credential_data_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, comment="管理员默认凭据(加密JSON)")
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
    body_wrapper_key: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 如 "params"，body 包为 {"params":{...}}
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
    # 参数来源：static(固定值) / user_input(用户输入) / user_credential(用户凭据)
    param_source: Mapped[str] = mapped_column(String(16), default="static")
    # 用户输入/凭据时的显示标签
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AgentProfileExternalSystemModel(Base):
    __tablename__ = "agent_profile_external_systems"
    __table_args__ = (UniqueConstraint("profile_id", "system_id", name="uq_profile_ext_system"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("agent_profiles.id"), index=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("external_systems.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), default="")
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


# ---------------------------------------------------------------------------
# Knowledge Base System
# ---------------------------------------------------------------------------


class KnowledgeBaseModel(Base):
    """知识库定义"""
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")  # 目标声明：定义知识库关注什么、不关注什么
    scope: Mapped[str] = mapped_column(String(20), default="org", index=True)  # org / team / personal
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # scope=team 时关联的团队
    visibility: Mapped[str] = mapped_column(String(20), default="public")  # public / restricted / private
    settings_json: Mapped[str] = mapped_column(Text, default="{}")  # 编译参数（LLM 模型、chunk 大小等）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class KBDocumentModel(Base):
    """原始文档"""
    __tablename__ = "kb_documents"
    __table_args__ = (
        Index("ix_kb_documents_kb_status", "knowledge_base_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))
    file_type: Mapped[str] = mapped_column(String(20))  # pdf / docx / md / html / epub
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA256，用于增量编译
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending / compiling / compiled / failed
    compiled_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class KBWikiPageModel(Base):
    """Wiki 编译产物页面"""
    __tablename__ = "kb_wiki_pages"
    __table_args__ = (
        Index("ix_kb_wiki_pages_kb_type", "knowledge_base_id", "page_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(500), index=True)
    page_type: Mapped[str] = mapped_column(String(30), index=True)  # entity / concept / source_summary / synthesis / comparison / faq / procedure
    content: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"))
    # 自动生成的一句话摘要：参与检索命中（标题不符但摘要命中也能召回本页），
    # 参考 Dify 的 Summary Auto-Gen；为空时检索只匹配正文
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    frontmatter_json: Mapped[str] = mapped_column(Text, default="{}")  # YAML frontmatter 结构化存储
    sources_json: Mapped[str] = mapped_column(Text, default="[]")  # 溯源：["kb_document:3", "kb_document:7"]
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # 向量 embedding
    authority_level: Mapped[str] = mapped_column(String(10), default="L1", index=True)  # L3 / L2 / L1 / L0
    conflicts_json: Mapped[str] = mapped_column(Text, default="[]")  # 冲突标记
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class KBWikiLinkModel(Base):
    """页面间链接关系，用于知识图谱"""
    __tablename__ = "kb_wiki_links"
    __table_args__ = (
        Index("ix_kb_wiki_links_source", "source_page_id"),
        Index("ix_kb_wiki_links_target", "target_page_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("kb_wiki_pages.id"), index=True)
    target_page_id: Mapped[int] = mapped_column(ForeignKey("kb_wiki_pages.id"), index=True)
    link_type: Mapped[str] = mapped_column(String(20), default="reference")  # reference / related / contradicts / extends
    context: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 链接上下文


class KBChunkModel(Base):
    """Wiki 页面的段级切片。

    为什么需要独立一张表：页级 embedding 把整页压成一个向量，长页（编译出的
    source_summary / synthesis 动辄数千字）的主题会被「平均」掉，问其中某一节
    往往召不回本页。段级切片的收益有两块——

    1. 向量召回按段算，长尾内容不再被平均；
    2. 命中片段直接取「真正命中的那一段」，不再靠启发式猜哪段相关。

    页级 ``kb_wiki_pages.embedding`` 保留：段表为空（存量库、切块失败）时
    检索自动退化为页级向量，不会因为新表没数据就丢掉整个语义通道。
    """

    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index("ix_kb_chunks_page_chunk", "page_id", "chunk_index"),
        Index("ix_kb_chunks_kb", "knowledge_base_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("kb_wiki_pages.id"), index=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    # 该段所属的最近一级 Markdown 标题，向量化时前置（Contextual Retrieval 的简化版）
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # base64(float32)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class KBIngestTaskModel(Base):
    """文档编译任务"""
    __tablename__ = "kb_ingest_tasks"
    __table_args__ = (
        # 注意：不能叫 ix_kb_ingest_tasks_status，会与 status 列 index=True 的自动索引重名
        Index("ix_kb_ingest_tasks_kb_status", "knowledge_base_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(20), default="compile")  # compile / recompile / delete
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending / running / completed / failed / retrying
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class KBReviewItemModel(Base):
    """人工审核项"""
    __tablename__ = "kb_review_items"
    __table_args__ = (
        Index("ix_kb_review_items_kb_status", "knowledge_base_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    review_type: Mapped[str] = mapped_column(String(30), index=True)  # conflict_resolution / page_creation / page_merge / page_delete / authority_upgrade
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    options_json: Mapped[str] = mapped_column(Text, default="[]")  # 可选操作列表
    related_page_ids_json: Mapped[str] = mapped_column(Text, default="[]")  # 关联的 Wiki 页面 ID
    related_document_ids_json: Mapped[str] = mapped_column(Text, default="[]")  # 关联的原始文档 ID
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending / approved / rejected / resolved
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


class KBAccessControlModel(Base):
    """知识库访问控制"""
    __tablename__ = "kb_access_control"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "principal_type", "principal_id", name="uq_kb_access"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    principal_type: Mapped[str] = mapped_column(String(10))  # user / team
    principal_id: Mapped[int] = mapped_column(Integer, index=True)  # user_id 或 team_id
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin / editor / viewer
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)


# ---------------------------------------------------------------------------
# 企业权限体系（M6-C / docs/design/m6-design.md 第四节）
# ---------------------------------------------------------------------------


class RoleModel(Base):
    """自定义角色（Casbin ``p``/``g`` 的 sub 命名空间，兼具可读元数据）。"""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("slug", name="uq_roles_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # 内置角色不允许删除，避免内置策略失去主体
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class CasbinRuleModel(Base):
    """Casbin 策略存储（对应 casbin 官方 adapter 的 ``casbin_rule`` 表）。

    列名 v0..v5 是 casbin 官方 adapter 的约定，adapter 实现见
    ``app/services/permission_service.py::SQLAlchemyAdapter``。
    """

    __tablename__ = "casbin_rule"
    __table_args__ = (
        Index("ix_casbin_rule_ptype_v0_v1", "ptype", "v0", "v1"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ptype: Mapped[str] = mapped_column(String(16), index=True)
    v0: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v1: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v2: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v3: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v4: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v5: Mapped[str | None] = mapped_column(String(256), nullable=True)


# ---------------------------------------------------------------------------
# AI 提供商（LLM 后端）
# ---------------------------------------------------------------------------


class LlmProviderModel(Base):
    """AI 提供商：一套「怎么连大模型」的完整描述。

    ``provider_type`` 决定的是**认证方式**，不是厂商：

    - ``openai_compatible``：标准 OpenAI 兼容端点，Bearer API Key 认证。
      OpenAI / DeepSeek / 通义 / Ollama / vLLM 都归这一类，换厂商只改配置。
    - ``enterprise_cookie``：企业内网 AI 网关，登录态靠浏览器 Cookie，
      没有可用的 API Key。凭据与登录态见 ``LlmProviderCredentialModel``。

    ``is_default`` 全局唯一由服务层保证 —— SQLite 与 MySQL 都没有可移植的
    部分唯一索引（partial index），放在 DB 层会写出只在一种方言下成立的约束。
    """

    __tablename__ = "llm_providers"
    __table_args__ = (UniqueConstraint("slug", name="uq_llm_provider_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(64), index=True)
    provider_type: Mapped[str] = mapped_column(String(32), default="openai_compatible", index=True)
    base_url: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class LlmProviderCredentialModel(Base):
    """企业类型提供商的登录态，**一个提供商下可以有多条账号**。

    单账号是旧实现的默认形态，但真实企业网关普遍按账号限配额：全部流量压在
    一个号上，一旦该号被限流或被安全策略锁定，整站对话同时不可用。因此这里
    改成账号池 —— 每个 provider 下挂多条凭据，构建网关时按
    ``priority`` + ``last_used_at`` 选号（见 ``credentials.acquire``）。

    **仍然不按终端用户存**：账号池是系统级资源，上游看到的身份只由池里选中
    的那条决定，与会话发起人无关。

    刻意**不加** ``(provider_id, username)`` 唯一约束：账号未填用户名时是空串，
    唯一约束会让「先建凭据、后补用户名」的正常流程互相冲突。去重由服务层做。
    """

    __tablename__ = "llm_provider_credentials"
    __table_args__ = (Index("ix_llm_provider_cred_provider_status", "provider_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id"), index=True)
    # 展示名，例如「运营号-01」。留空时界面回退显示 username
    label: Mapped[str] = mapped_column(String(64), default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    password_encrypted: Mapped[str] = mapped_column(Text, default="")
    cookie_encrypted: Mapped[str] = mapped_column(Text, default="")
    login_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # pending（从未登录）/ active / expired / failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 过期前自动重新登录；关闭后只能人工更新 Cookie
    auto_refresh: Mapped[bool] = mapped_column(Boolean, default=True)
    expire_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 轮换权重：小的优先。留出空档是为了「主力号 priority=10、备用号=90」
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    # 选号依据：最少使用优先，让配额在池内均匀摊开
    last_used_at: Mapped[datetime | None] = mapped_column(AppDateTime(), nullable=True)
    # 连续失败计数：达到阈值后自动退出候选池，避免坏号被反复选中
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    # 人工停用（临时摘掉一个号但保留其凭据，便于恢复）
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class LlmModelCatalogModel(Base):
    """某个提供商下可用模型的目录（从上游注册表或 ``/models`` 发现）。

    存在的理由：上游的「模型 ID」和「请求体里要填的模型名」经常不是同一个
    东西（上游常见 ``qwen3.6-35b`` vs ``Qwen3.6-35B-A3B``），而表单是一个自由
    文本框，填错只能等到调用时吃一个 404 ``Model Not Exist``。把目录落库后，
    界面能给出候选、能校验、也能按用途挑模型。

    ``provider.extra_json.roles`` 负责把用途（chat / reasoner / vision / image
    / title）映射到这里的 ``model_name``。
    """

    __tablename__ = "llm_provider_chat_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_key", name="uq_llm_provider_model_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id"), index=True)
    # 上游注册表里的 ID（上游注册表 ID：qwen3.6-35b）
    model_key: Mapped[str] = mapped_column(String(128))
    # 请求体里真正要填的名字（请求体模型名：Qwen3.6-35B-A3B）
    model_name: Mapped[str] = mapped_column(String(128))
    # text-generation / image-text-to-text / text-to-image / any-to-any
    task_type: Mapped[str] = mapped_column(String(48), default="", index=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 采样参数等上游建议值，构建网关时并入 extra_body 之外的默认值
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now)
    updated_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, onupdate=app_now)


class AuditLogModel(Base):
    """审计日志。

    ``action`` 用 ``resource.action`` 形式（如 ``knowledge.create``），
    ``result`` 取 allow / deny / error。两个复合索引分别服务
    「某人的操作时间线」与「某资源的变更时间线」两类查询。
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_resource_created", "resource_type", "resource_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result: Mapped[str] = mapped_column(String(16), default="allow", index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 已脱敏的 JSON 文本（密码/token 不落库，长值截断）
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(AppDateTime(), default=app_now, index=True)
