from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import AppBaseModel


# ── nested helpers ──────────────────────────────────────────────────────────


class ExternalApiParam(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    param_type: str = Field(..., pattern="^(path|query|body)$")
    data_type: str = Field(default="string", pattern="^(string|integer|boolean|object)$")
    required: bool = False
    description: str = ""
    default_value: str | None = None


class ExternalApiBrief(BaseModel):
    id: int
    name: str
    display_name: str
    method: str
    path: str
    requires_approval: bool
    enabled: bool


class ExternalApiDetail(ExternalApiBrief):
    description: str
    request_body_schema: str | None
    response_example: str | None
    timeout_seconds: int
    params: list[ExternalApiParam] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ── system schemas ──────────────────────────────────────────────────────────


class ExternalSystemCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    base_url: str = Field(..., min_length=1, max_length=512)
    auth_type: str = Field(..., pattern="^(api_key|bearer|basic|oauth2|custom|jwt_login)$")
    credential_template: dict = Field(default_factory=dict)
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_auth_url: str | None = Field(default=None, max_length=512)
    oauth_token_url: str | None = Field(default=None, max_length=512)
    oauth_scope: str | None = None
    oauth_refresh_token_url: str | None = Field(default=None, max_length=512)
    jwt_login_url: str | None = Field(default=None, max_length=512)
    jwt_refresh_url: str | None = Field(default=None, max_length=512)
    jwt_refresh_body_template: str | None = None
    jwt_refresh_token_path: str | None = None
    jwt_request_body_template: str | None = None
    jwt_response_token_path: str | None = None
    jwt_response_expires_path: str | None = None
    jwt_response_token_header: str | None = None
    published: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    advanced_auth: dict = Field(default_factory=dict)

    @field_validator("name", "description", "base_url", "jwt_login_url", "jwt_refresh_url", "oauth_auth_url", "oauth_token_url", "oauth_refresh_token_url")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, v: str) -> str:
        return v.rstrip("/")


class ExternalSystemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    auth_type: str | None = Field(default=None, pattern="^(api_key|bearer|basic|oauth2|custom|jwt_login)$")
    credential_template: dict | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_auth_url: str | None = Field(default=None, max_length=512)
    oauth_token_url: str | None = Field(default=None, max_length=512)
    oauth_scope: str | None = None
    oauth_refresh_token_url: str | None = Field(default=None, max_length=512)
    jwt_login_url: str | None = Field(default=None, max_length=512)
    jwt_refresh_url: str | None = Field(default=None, max_length=512)
    jwt_refresh_body_template: str | None = None
    jwt_refresh_token_path: str | None = None
    jwt_request_body_template: str | None = None
    jwt_response_token_path: str | None = None
    jwt_response_expires_path: str | None = None
    jwt_response_token_header: str | None = None
    published: bool | None = None
    headers: dict[str, str] | None = None
    advanced_auth: dict | None = None
    enabled: bool | None = None

    @field_validator("name", "description", "base_url", "jwt_login_url", "jwt_refresh_url", "oauth_auth_url", "oauth_token_url", "oauth_refresh_token_url")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, v: str | None) -> str | None:
        return v.rstrip("/") if isinstance(v, str) else v


class ExternalSystemResponse(AppBaseModel):
    id: int
    name: str
    description: str
    base_url: str
    auth_type: str
    credential_template: dict
    oauth_auth_url: str | None
    oauth_token_url: str | None
    oauth_scope: str | None
    oauth_refresh_token_url: str | None
    jwt_login_url: str | None
    jwt_refresh_url: str | None
    jwt_refresh_body_template: str | None
    jwt_refresh_token_path: str | None
    jwt_request_body_template: str | None
    jwt_response_token_path: str | None
    jwt_response_expires_path: str | None
    jwt_response_token_header: str | None
    published: bool
    headers: dict[str, str]
    advanced_auth: dict
    enabled: bool
    api_count: int = 0
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ExternalSystemListResponse(AppBaseModel):
    items: list[ExternalSystemResponse]


# ── api schemas ─────────────────────────────────────────────────────────────


class ExternalApiCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    method: str = Field(..., pattern="^(GET|POST|PUT|DELETE|PATCH)$")
    path: str = Field(..., min_length=1, max_length=512)
    request_body_schema: str | None = None
    response_example: str | None = None
    requires_approval: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    params: list[ExternalApiParam] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip().lower().replace("-", "_").replace(" ", "_")

    @field_validator("display_name", "description", "path")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class ExternalApiUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    method: str | None = Field(default=None, pattern="^(GET|POST|PUT|DELETE|PATCH)$")
    path: str | None = Field(default=None, min_length=1, max_length=512)
    request_body_schema: str | None = None
    response_example: str | None = None
    requires_approval: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    enabled: bool | None = None
    params: list[ExternalApiParam] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        return v.strip().lower().replace("-", "_").replace(" ", "_") if isinstance(v, str) else v

    @field_validator("display_name", "description", "path")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class ExternalApiListResponse(AppBaseModel):
    items: list[ExternalApiDetail]


# ── test call ───────────────────────────────────────────────────────────────


class ExternalApiTestRequest(BaseModel):
    """Payload for testing an API call. Params are passed as key-value pairs."""
    params: dict = Field(default_factory=dict)
    credential_data: dict | None = None


class ExternalApiTestResponse(AppBaseModel):
    success: bool
    status_code: int
    body: str
    elapsed_ms: int


# ── profile ↔ system association ────────────────────────────────────────────


class ProfileExternalSystemRef(BaseModel):
    system_id: int
    enabled: bool = True


# ── user connection schemas ─────────────────────────────────────────────────


class UserConnectionCreateRequest(BaseModel):
    credential_data: dict = Field(default_factory=dict)


class UserConnectionResponse(AppBaseModel):
    id: int
    system_id: int
    system_name: str
    connection_status: str
    connected_at: datetime
    last_checked_at: datetime | None


class UserConnectionListResponse(AppBaseModel):
    items: list[UserConnectionResponse]


# ── OpenAPI import ──────────────────────────────────────────────────────────


class OpenApiImportRequest(BaseModel):
    """Import from OpenAPI/Swagger JSON."""
    openapi_json: str | None = None
    openapi_url: str | None = None


class OpenApiImportPreview(BaseModel):
    """Preview of what will be imported from OpenAPI."""
    system_name: str
    system_description: str
    base_url: str
    auth_type: str
    apis: list[dict]
