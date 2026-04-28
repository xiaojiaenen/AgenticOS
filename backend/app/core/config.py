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
    agent_parallel_tool_calls: bool = False
    database_url: str = Field(default="sqlite:///./data/agenticos.db", validation_alias="DATABASE_URL")
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
    auth_secret_key: str = Field(default="agenticos-dev-secret-change-me", validation_alias="AUTH_SECRET_KEY")
    auth_token_expire_minutes: int = Field(default=60 * 24 * 7, validation_alias="AUTH_TOKEN_EXPIRE_MINUTES")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_cors_allow_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    def get_hitl_require_approval_tools(self) -> set[str]:
        return {tool.strip() for tool in self.hitl_require_approval_tools.split(",") if tool.strip()}

    def get_skill_storage_dir(self) -> Path:
        return Path(self.skill_storage_dir).expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
