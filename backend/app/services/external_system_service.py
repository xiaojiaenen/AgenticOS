"""External system integration — CRUD, user credentials, one-tool-per-system design.

自本文件拆分出 ``app/services/external_systems/`` 包（纯移动，公共 API 零变更）：

- context            当前用户/会话的 contextvars
- cache              外部系统配置的 Redis 缓存
- coordinators       UserInputBlocker / ApprovalBlocker 阻塞协调器
- serializers        ORM 序列化助手与轻量凭据对象
- auth_injector      AuthInjector：出站请求认证注入
- security_processor SecurityProcessor：签名/加解密
- tool_builder       一系统一工具的动态工具注册
- service            ExternalSystemService CRUD 门面
- presets            预设外部系统 seed

本模块保留为兼容层，re-export 全部既有公共符号。
"""

from __future__ import annotations

import logging

from app.services.external_systems.auth_injector import AuthInjector
from app.services.external_systems.cache import (
    _CACHE_FIELDS,
    _CachedSystem,
    _SYSTEM_CACHE_TTL,
    _cache_delete,
    _cache_get,
    _cache_put,
    _serialize_system_for_cache,
    _system_cache_key,
    refresh_system_cache,
)
from app.services.external_systems.coordinators import ApprovalBlocker, UserInputBlocker
from app.services.external_systems.context import (
    _current_session_id,
    _current_user_id,
    get_ext_user_id,
    set_ext_user_id,
)
from app.services.external_systems.presets import seed_preset_external_systems
from app.services.external_systems.security_processor import SecurityProcessor
from app.services.external_systems.serializers import (
    _DefaultCredential,
    _build_default_credential,
    _extract_nested,
    _make_naive,
    _naive_utc_now,
    _safe_name,
    _serialize_api,
    _serialize_connection,
    _serialize_headers,
    _serialize_system,
)
from app.services.external_systems.service import (
    INTEGRATION_CATEGORIES,
    ExternalSystemService,
)
from app.services.external_systems.tool_builder import (
    _build_system_tool_handler,
    _cast_value,
    _resolve_path,
    register_external_tools,
)

logger = logging.getLogger(__name__)

__all__ = [
    "INTEGRATION_CATEGORIES",
    "ApprovalBlocker",
    "AuthInjector",
    "ExternalSystemService",
    "SecurityProcessor",
    "UserInputBlocker",
    "_CACHE_FIELDS",
    "_CachedSystem",
    "_DefaultCredential",
    "_build_default_credential",
    "_build_system_tool_handler",
    "_cache_delete",
    "_cache_get",
    "_cache_put",
    "_cast_value",
    "_current_session_id",
    "_current_user_id",
    "_extract_nested",
    "_make_naive",
    "_naive_utc_now",
    "_resolve_path",
    "_safe_name",
    "_serialize_api",
    "_serialize_connection",
    "_serialize_headers",
    "_serialize_system",
    "_serialize_system_for_cache",
    "_SYSTEM_CACHE_TTL",
    "_system_cache_key",
    "get_ext_user_id",
    "logger",
    "refresh_system_cache",
    "register_external_tools",
    "seed_preset_external_systems",
    "set_ext_user_id",
]
