"""上游集成：唯一上游 agents.gree.com。

自动登录流程与 sesame 保持一致（Playwright 表单识别 + cookie 过期算法）。
"""

from app.services.upstream.auto_login_service import login_with_credentials
from app.services.upstream.credential_store import (
    UPSTREAM_KEY,
    get_active_cookie,
    get_upstream_base_url,
    get_upstream_login_url,
)
from app.services.upstream.login_orchestrator import (
    ensure_cookie_for_user,
    perform_auto_login,
    refresh_expired_credentials,
    start_cookie_refresh_loop,
    sync_after_login,
    sync_to_sesame,
)
from app.services.upstream.upstream_client import UpstreamAuthError, UpstreamClient, get_upstream_client

__all__ = [
    "UPSTREAM_KEY",
    "UpstreamAuthError",
    "UpstreamClient",
    "ensure_cookie_for_user",
    "get_active_cookie",
    "get_upstream_base_url",
    "get_upstream_client",
    "get_upstream_login_url",
    "login_with_credentials",
    "perform_auto_login",
    "refresh_expired_credentials",
    "start_cookie_refresh_loop",
    "sync_after_login",
    "sync_to_sesame",
]
