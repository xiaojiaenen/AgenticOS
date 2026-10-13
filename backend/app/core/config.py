from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "AgenticOS API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_allow_origins: str = "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3001,http://localhost:3001"
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-5.4", validation_alias="OPENAI_MODEL")
    agent_system_prompt: str = "你是 AgenticOS 的 AI 助手。"
    agent_max_steps: int = 10
    agent_max_tokens: int = 65536
    agent_parallel_tool_calls: bool = False
    llm_timeout: int = Field(default=300, validation_alias="LLM_TIMEOUT")
    database_url: str = Field(default=f"sqlite:///{PROJECT_ROOT / 'data' / 'agenticos.db'}", validation_alias="DATABASE_URL")
    # MySQL 连接池分级（M6-A1）：常驻连接 / 溢出上限 / 回收秒数
    db_pool_size: int = Field(default=10, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, validation_alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=1800, validation_alias="DB_POOL_RECYCLE")
    # LLM 全局并发闸（M6-A5）：跨实例共享计数，Redis 不可用时退化为本地信号量
    llm_gate_enabled: bool = Field(default=True, validation_alias="LLM_GATE_ENABLED")
    llm_gate_max_concurrency: int = Field(default=60, validation_alias="LLM_GATE_MAX_CONCURRENCY")
    llm_gate_lease_seconds: int = Field(default=300, validation_alias="LLM_GATE_LEASE_SECONDS")
    llm_gate_wait_seconds: float = Field(default=120.0, validation_alias="LLM_GATE_WAIT_SECONDS")
    # 压测/联调用 LLM mock：开启后 orchestrator 不调用真实 LLM（默认关闭）
    llm_mock_enabled: bool = Field(default=False, validation_alias="LLM_MOCK_ENABLED")
    # dashboard 统计缓存 TTL 秒（M6-A4）
    dashboard_cache_ttl: int = Field(default=30, validation_alias="DASHBOARD_CACHE_TTL")
    skill_storage_dir: str = Field(
        default=str(PROJECT_ROOT / "data" / "skills"),
        validation_alias="SKILL_STORAGE_DIR",
    )
    context_compression_enabled: bool = True
    context_compress_after_turns: int = 16
    context_keep_recent_turns: int = 6
    hitl_enabled: bool = True
    hitl_require_approval_tools: str = "file_to_md,run_skill_python_script"
    hitl_timeout_seconds: int = 300
    auth_secret_key: str = Field(default="", validation_alias="AUTH_SECRET_KEY")
    auth_token_expire_minutes: int = Field(default=60 * 24, validation_alias="AUTH_TOKEN_EXPIRE_MINUTES")
    auth_rate_limit_max_attempts: int = Field(default=5, validation_alias="AUTH_RATE_LIMIT_MAX_ATTEMPTS")
    auth_rate_limit_window_seconds: int = Field(default=600, validation_alias="AUTH_RATE_LIMIT_WINDOW_SECONDS")
    auth_rate_limit_block_seconds: int = Field(default=900, validation_alias="AUTH_RATE_LIMIT_BLOCK_SECONDS")

    # 异步子代理配置
    async_sub_agents_enabled: bool = Field(default=True, validation_alias="ASYNC_SUB_AGENTS_ENABLED")

    # Redis 配置（留空则使用内存 fallback）
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    redis_cluster: bool = Field(default=False, validation_alias="REDIS_CLUSTER")

    # 外部系统凭据加密密钥（留空则从 AUTH_SECRET_KEY 派生）
    external_system_encryption_key: str = Field(default="", validation_alias="EXTERNAL_SYSTEM_ENCRYPTION_KEY")

    # 凭据代理 API 内部令牌（供爬虫平台等内部系统调用）
    credential_proxy_token: str = Field(default="", validation_alias="CREDENTIAL_PROXY_TOKEN")

    # Sesame 网关集成（LDAP 登录成功后自动同步账号密码到 sesame cookie 共享池）
    sesame_gateway_url: str = Field(default="", validation_alias="SESAME_GATEWAY_URL")
    sesame_internal_token: str = Field(default="", validation_alias="SESAME_INTERNAL_TOKEN")
    sesame_channel_id: int = Field(default=0, validation_alias="SESAME_CHANNEL_ID")

    # 唯一上游 agents.gree.com — 本地自动登录 + Cookie 请求（流程与 sesame 一致）
    upstream_base_url: str = Field(default="https://agents.gree.com", validation_alias="UPSTREAM_BASE_URL")
    upstream_login_url: str = Field(default="", validation_alias="UPSTREAM_LOGIN_URL")
    upstream_auto_login_enabled: bool = Field(default=True, validation_alias="UPSTREAM_AUTO_LOGIN_ENABLED")
    upstream_cookie_refresh_minutes: int = Field(default=30, validation_alias="UPSTREAM_COOKIE_REFRESH_MINUTES")
    upstream_cookie_refresh_buffer_hours: int = Field(default=2, validation_alias="UPSTREAM_COOKIE_REFRESH_BUFFER_HOURS")
    # 本机 Agent 对话默认用登录用户 Cookie 直连 agents.gree.com（不需要 API Key）
    upstream_use_cookie_llm: bool = Field(
        default=True,
        validation_alias="UPSTREAM_USE_COOKIE_LLM",
        description="本机对话默认用当前用户 Cookie 调上游；关闭则仅用 OPENAI_BASE_URL",
    )

    # LDAP 认证配置（留空 = 不启用）
    ldap_enabled: bool = Field(default=False, validation_alias="LDAP_ENABLED")
    ldap_auto_create_users: bool = Field(default=False, validation_alias="LDAP_AUTO_CREATE_USERS")
    ldap_gateway_url: str = Field(default="", validation_alias="LDAP_GATEWAY_URL")
    ldap_email_domain: str = Field(default="gree.com.cn", validation_alias="LDAP_EMAIL_DOMAIN")
    ldap_email_imap_host: str = Field(default="10.12.128.18", validation_alias="LDAP_EMAIL_IMAP_HOST")
    ldap_email_imap_port: int = Field(default=993, validation_alias="LDAP_EMAIL_IMAP_PORT")
    ldap_email_smtp_host: str = Field(default="10.12.128.18", validation_alias="LDAP_EMAIL_SMTP_HOST")
    ldap_email_smtp_port: int = Field(default=465, validation_alias="LDAP_EMAIL_SMTP_PORT")

    # 系统通知邮箱配置（用于任务完成通知等系统邮件）
    notify_email_address: str = Field(default="", validation_alias="NOTIFY_EMAIL_ADDRESS")
    notify_email_password: str = Field(default="", validation_alias="NOTIFY_EMAIL_PASSWORD")
    notify_smtp_host: str = Field(default="10.12.128.18", validation_alias="NOTIFY_SMTP_HOST")
    notify_smtp_port: int = Field(default=465, validation_alias="NOTIFY_SMTP_PORT")
    notify_smtp_ssl: bool = Field(default=True, validation_alias="NOTIFY_SMTP_SSL")
    notify_task_min_seconds: int = Field(default=120, validation_alias="NOTIFY_TASK_MIN_SECONDS")

    # 记忆系统（分层蒸馏 + 混合检索）
    memory_embedding_model: str = Field(default="text-embedding-3-small", validation_alias="MEMORY_EMBEDDING_MODEL")
    memory_embedding_dimensions: int = Field(default=1536, validation_alias="MEMORY_EMBEDDING_DIMENSIONS")
    memory_retrieval_char_budget: int = Field(default=2000, validation_alias="MEMORY_RETRIEVAL_CHAR_BUDGET")
    memory_retrieval_timeout_ms: int = Field(default=500, validation_alias="MEMORY_RETRIEVAL_TIMEOUT_MS")
    memory_l2_aggregate_turns: int = Field(default=6, validation_alias="MEMORY_L2_AGGREGATE_TURNS")
    memory_l3_persona_turns: int = Field(default=20, validation_alias="MEMORY_L3_PERSONA_TURNS")
    memory_vector_top_k: int = Field(default=10, validation_alias="MEMORY_VECTOR_TOP_K")
    memory_bm25_top_k: int = Field(default=10, validation_alias="MEMORY_BM25_TOP_K")
    memory_rrf_k: int = Field(default=60, validation_alias="MEMORY_RRF_K")

    # ── M6-C OIDC 单点登录（留空/关闭 = 不启用）────────────────────────────
    oidc_enabled: bool = Field(default=False, validation_alias="OIDC_ENABLED")
    # 形如 https://sso.example.com/realms/main（结尾不带 /）
    oidc_issuer: str = Field(default="", validation_alias="OIDC_ISSUER")
    oidc_client_id: str = Field(default="", validation_alias="OIDC_CLIENT_ID")
    oidc_client_secret: str = Field(default="", validation_alias="OIDC_CLIENT_SECRET")
    # 留空时由请求的 origin 推导（须与 IdP 侧登记的 redirect_uri 完全一致）
    oidc_redirect_uri: str = Field(default="", validation_alias="OIDC_REDIRECT_URI")
    oidc_scopes: str = Field(default="openid profile email", validation_alias="OIDC_SCOPES")
    # IdP 角色映射：只接受该白名单内的角色，防止 IdP 侧误配置直接下发 admin
    oidc_admin_group: str = Field(default="", validation_alias="OIDC_ADMIN_GROUP")
    # OIDC 用户名/邮箱的本地域后缀（claims 里只有裸工号时补全）
    oidc_email_domain: str = Field(default="", validation_alias="OIDC_EMAIL_DOMAIN")

    # ── M6-C LDAP 部门同步（属性名可配置，不在代码里假设 DN 语法）──────────
    ldap_department_sync_enabled: bool = Field(default=False, validation_alias="LDAP_DEPARTMENT_SYNC_ENABLED")
    ldap_directory_user_path: str = Field(default="", validation_alias="LDAP_DIRECTORY_USER_PATH")
    ldap_directory_search_base: str = Field(default="", validation_alias="LDAP_DIRECTORY_SEARCH_BASE")
    ldap_department_dn_attribute: str = Field(default="dn", validation_alias="LDAP_DEPARTMENT_DN_ATTRIBUTE")
    ldap_department_name_attribute: str = Field(default="cn", validation_alias="LDAP_DEPARTMENT_NAME_ATTRIBUTE")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_cors_allow_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    def get_hitl_require_approval_tools(self) -> set[str]:
        return {tool.strip() for tool in self.hitl_require_approval_tools.split(",") if tool.strip()}

    def get_skill_storage_dir(self) -> Path:
        return Path(self.skill_storage_dir).expanduser().resolve()


def _load_or_create_auth_secret() -> tuple[str, bool]:
    """未配置 AUTH_SECRET_KEY 时，从持久化文件读取/生成密钥。

    - 优先读取 data/.auth_secret（多进程共享，重启不变）；
    - 不存在则生成并以 O_EXCL 原子创建（0600），避免多进程竞态各生成一份；
    - 文件不可写时回退为进程内随机密钥（重启会变化，仅开发环境可用）。

    Returns:
        (secret, from_file) — from_file=True 表示已持久化，多进程一致。
    """
    import logging
    import os
    import secrets

    logger = logging.getLogger("config")
    secret_path = PROJECT_ROOT / "data" / ".auth_secret"

    try:
        if secret_path.exists():
            existing = secret_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing, True
    except OSError as exc:
        logger.warning("读取 %s 失败: %s", secret_path, exc)

    secret = secrets.token_hex(32)
    try:
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # 0600：仅属主可读写；O_EXCL 保证并发下只有一个进程创建成功
            fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(secret + "\n")
        except FileExistsError:
            # 另一进程刚创建 → 使用其内容，保证多进程密钥一致
            concurrent = secret_path.read_text(encoding="utf-8").strip()
            if concurrent:
                return concurrent, True
        try:
            os.chmod(str(secret_path), 0o600)
        except OSError:
            pass  # Windows/受限文件系统上 chmod 可能不生效
        return secret, True
    except OSError as exc:
        logger.warning(
            "无法持久化 AUTH_SECRET_KEY 到 %s (%s)，将使用临时随机密钥（重启后失效）。"
            "生产环境请务必在 .env 中配置 AUTH_SECRET_KEY。",
            secret_path,
            exc,
        )
        return secret, False


@lru_cache
def get_settings() -> Settings:
    import logging

    settings = Settings()
    # 先校验、后派生：派生逻辑只在非生产兜底，生产环境必须在派生发生前就失败，
    # 否则会被派生出来的临时密钥掩盖「其实没配」的事实。
    _assert_production_secrets(settings)
    if not settings.auth_secret_key:
        secret, from_file = _load_or_create_auth_secret()
        settings.auth_secret_key = secret
        logger = logging.getLogger("config")
        if from_file:
            logger.warning(
                "AUTH_SECRET_KEY 未设置，已从 data/.auth_secret 加载/生成持久化密钥。"
                "生产环境仍强烈建议在 .env 中显式配置 AUTH_SECRET_KEY。"
            )
        else:
            logger.warning(
                "AUTH_SECRET_KEY 未设置且无法持久化，已自动生成临时随机密钥"
                "（重启后会变化，已有会话/加密数据将失效）。"
                "生产环境必须在 .env 中设置 AUTH_SECRET_KEY。"
            )
    return settings


# ENVIRONMENT=production 时必须显式提供的密钥。
# 元组含义：(settings 属性, .env 变量名, 为什么必须显式给出)
_REQUIRED_PRODUCTION_SECRETS: tuple[tuple[str, str, str], ...] = (
    (
        "auth_secret_key",
        "AUTH_SECRET_KEY",
        "签发/校验本系统 JWT；留空时只会从 data/.auth_secret 派生，"
        "容器重建即失效（所有会话被登出）",
    ),
    (
        "external_system_encryption_key",
        "EXTERNAL_SYSTEM_ENCRYPTION_KEY",
        "加密外部系统凭据；留空时从 AUTH_SECRET_KEY 派生，"
        "轮换 JWT 密钥会连带让已存凭据无法解密",
    ),
)


def _assert_production_secrets(settings: Settings) -> None:
    """生产环境启动即失败：关键密钥留空不允许静默派生。

    派生行为只在非生产保留（开发机免配置、测试不依赖 .env）。
    容器化部署建议改用 docker secrets / K8s Secret 注入同名环境变量。

    Raises:
        RuntimeError: ENVIRONMENT 为 production/prod 且有密钥缺失。
    """
    if settings.environment.strip().lower() not in {"production", "prod"}:
        return

    missing = [
        f"{env_name}（{why}）"
        for attr, env_name, why in _REQUIRED_PRODUCTION_SECRETS
        if not (getattr(settings, attr, "") or "").strip()
    ]
    if missing:
        raise RuntimeError(
            "ENVIRONMENT=production 但以下密钥未显式配置，拒绝启动：\n  - "
            + "\n  - ".join(missing)
            + "\n请在 backend/.env（参见 backend/.env.example 的 SECURITY 段）或容器环境变量中显式设置；"
            "生产部署建议改用 docker secrets / K8s Secret 注入。"
        )
