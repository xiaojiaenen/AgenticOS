"""系统设置：LDAP 认证配置（管理后台维护，支持连接测试）。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings, require_admin
from app.core.config import Settings
from app.db.models import UserModel
from app.services import ldap_auth_service as ldap

logger = logging.getLogger("agenticos.settings")

router = APIRouter(prefix="/settings", tags=["Settings"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LdapConfigPayload(BaseModel):
    """LDAP 配置（bind_password 传空字符串表示不修改）。"""

    enabled: bool = False
    server_url: str = Field(default="", max_length=512)
    start_tls: bool = False
    bind_dn: str = Field(default="", max_length=512)
    bind_password: str = Field(default="", max_length=512)
    base_dn: str = Field(default="", max_length=512)
    user_filter: str = Field(default="(sAMAccountName={username})", max_length=512)
    attr_username: str = Field(default="sAMAccountName", max_length=128)
    attr_email: str = Field(default="mail", max_length=128)
    attr_name: str = Field(default="displayName", max_length=128)
    attr_department: str = Field(default="department", max_length=128)
    auto_create_users: bool = False
    default_role: str = Field(default="user", pattern="^(user|admin)$")
    department_sync: bool = False
    email_domain: str = Field(default="", max_length=255)
    email_auto_configure: bool = False
    imap_host: str = Field(default="", max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    smtp_host: str = Field(default="", max_length=255)
    smtp_port: int = Field(default=465, ge=1, le=65535)


class LdapConfigResponse(BaseModel):
    enabled: bool
    server_url: str
    start_tls: bool
    bind_dn: str
    bind_password_set: bool
    base_dn: str
    user_filter: str
    attr_username: str
    attr_email: str
    attr_name: str
    attr_department: str
    auto_create_users: bool
    default_role: str
    department_sync: bool
    email_domain: str
    email_auto_configure: bool
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int


class LdapTestRequest(LdapConfigPayload):
    """连接测试：可提交未保存的配置进行验证。"""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/ldap", response_model=LdapConfigResponse)
def get_ldap_setting(
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LdapConfigResponse:
    config = ldap.load_config(db, settings)
    return LdapConfigResponse(**ldap.config_to_response(config))


@router.put("/ldap", response_model=LdapConfigResponse)
def update_ldap_setting(
    payload: LdapConfigPayload,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LdapConfigResponse:
    config = ldap.save_config(db, payload.model_dump(), settings)
    logger.info(
        "LDAP config updated: enabled=%s server=%s auto_create=%s",
        config.enabled, config.server_url, config.auto_create_users,
    )
    return LdapConfigResponse(**ldap.config_to_response(config))


@router.post("/ldap/test")
async def test_ldap_connection(
    payload: LdapTestRequest,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """连接测试：验证服务器可达、服务账号可绑定、用户过滤器可执行。

    优先使用提交的配置（便于保存前验证）；密码留空时沿用已保存的密码。
    """
    import asyncio

    data = payload.model_dump()
    if not data.get("bind_password"):
        stored = ldap.load_config(db, settings)
        data["bind_password"] = stored.bind_password

    config = ldap.LdapConfig(**{k: v for k, v in data.items() if k in ldap.DEFAULTS})
    # ldap3 为同步 API，放线程池避免阻塞事件循环
    return await asyncio.to_thread(ldap.test_connection, config)
