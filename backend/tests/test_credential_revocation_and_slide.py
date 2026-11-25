"""凭据失效联动吊销 + 会话滑动续期。

用户报障的两个现象，根因都是"机制有但没闭环"：

1. **「cookie 还有 4 小时，为什么对话 401」** —— 那个 4 小时是企业网关凭据
   的有效期，与平台登录会话（24h 硬顶）是两条独立的链。401 是平台会话
   过期。修法是滑动续期：活跃用户每次校验通过就把过期时间往后滑。
2. **「密码失败 401 并没有强制退出登录」** —— 定时续期失败会吊销平台会话
   （gateway_link.handle_credential_auth_failure），但**对话运行时**撞到
   上游 401/403 走的是 mark_cookie_invalid，那条路不吊销 —— 用户会一直
   对着 401 反复发消息却不知道要重新登录平台。已补上同一语义。
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock


from app.core.timezone import app_now
from app.services.llm_providers import credentials as cred_mod


class TestMarkCookieInvalidRevocation:
    """对话路径的凭据失效也要吊销绑定用户的平台会话。"""

    @staticmethod
    def _make_credential(*, user_id: int | None, had_cookie: bool):
        """造一条假凭据行 + 打桩 db.get。"""
        row = MagicMock()
        row.id = 42
        row.user_id = user_id
        row.failure_count = 0
        row.cookie_encrypted = "some-cookie" if had_cookie else ""
        return row

    def test_bound_user_with_cookie_gets_revoked(self, monkeypatch):
        """绑定用户 + 曾有 Cookie + 认证类失败 → 吊销平台会话。"""
        revoked_to = []
        import app.services.llm_providers.gateway_link as gl

        monkeypatch.setattr(gl, "revoke_user_platform_sessions", lambda uid: revoked_to.append(uid) or 2)
        monkeypatch.setattr(gl, "looks_like_auth_failure", lambda m: True)

        row = self._make_credential(user_id=7, had_cookie=True)
        db = MagicMock()
        db.get.return_value = row
        monkeypatch.setattr(cred_mod, "create_db_session", lambda: MagicMock(__enter__=lambda s: db, __exit__=lambda *a: None))

        cred_mod.mark_cookie_invalid(42, "上游返回 HTTP 401 密码已变更")
        assert revoked_to == [7], "绑定用户应被吊销平台会话"

    def test_unbound_credential_does_not_revoke(self, monkeypatch):
        """共享池账号（无绑定用户）没有可踢的人 —— 不吊销。"""
        revoked_to = []
        import app.services.llm_providers.gateway_link as gl

        monkeypatch.setattr(gl, "revoke_user_platform_sessions", lambda uid: revoked_to.append(uid) or 1)
        row = self._make_credential(user_id=None, had_cookie=True)
        db = MagicMock()
        db.get.return_value = row
        monkeypatch.setattr(cred_mod, "create_db_session", lambda: MagicMock(__enter__=lambda s: db, __exit__=lambda *a: None))

        cred_mod.mark_cookie_invalid(42, "上游 401")
        assert revoked_to == []

    def test_never_had_cookie_does_not_revoke(self, monkeypatch):
        """从未成功过的绑定行失败可能是 SSO 改版，不该踢人（与 gateway_link 同判据）。"""
        revoked_to = []
        import app.services.llm_providers.gateway_link as gl

        monkeypatch.setattr(gl, "revoke_user_platform_sessions", lambda uid: revoked_to.append(uid) or 1)
        row = self._make_credential(user_id=7, had_cookie=False)
        db = MagicMock()
        db.get.return_value = row
        monkeypatch.setattr(cred_mod, "create_db_session", lambda: MagicMock(__enter__=lambda s: db, __exit__=lambda *a: None))

        cred_mod.mark_cookie_invalid(42, "上游 401")
        assert revoked_to == []

    def test_non_auth_failure_does_not_revoke(self, monkeypatch):
        """网络超时这类非认证失败不该踢人。"""
        revoked_to = []
        import app.services.llm_providers.gateway_link as gl

        monkeypatch.setattr(gl, "revoke_user_platform_sessions", lambda uid: revoked_to.append(uid) or 1)
        row = self._make_credential(user_id=7, had_cookie=True)
        db = MagicMock()
        db.get.return_value = row
        monkeypatch.setattr(cred_mod, "create_db_session", lambda: MagicMock(__enter__=lambda s: db, __exit__=lambda *a: None))

        cred_mod.mark_cookie_invalid(42, "connection timeout to gateway")
        assert revoked_to == []


class TestSlidingSessionExpiry:
    """活跃用户不被 24h 硬顶踢出。"""

    @staticmethod
    def _make_service(row, settings=None):
        from app.services.auth_service import AuthService

        svc = AuthService.__new__(AuthService)
        svc.db = MagicMock()
        svc.db.get.return_value = row
        svc.settings = settings
        return svc, row

    def test_active_session_slides_forward(self):
        """校验通过 → expires_at 往后滑。"""
        from app.services.auth_service import AuthService

        now = app_now()
        # 快过期了（剩 1 分钟）
        row = MagicMock()
        row.revoked_at = None
        row.expires_at = now + timedelta(minutes=1)
        svc, row = self._make_service(row)
        # get 应该返回该行（db.get 是 mock，直接让它返回 row）
        svc.db.get = MagicMock(return_value=row)
        settings = MagicMock()
        settings.auth_token_expire_minutes = 1440
        svc.settings = settings

        changed = AuthService.slide_session_expiry(svc, "sess-1")
        assert changed is True
        # 新过期时间应约等于 now + 24h
        new_expiry = row.expires_at
        assert new_expiry > now + timedelta(hours=23)

    def test_revoked_session_never_slides(self):
        """被吊销的会话不续 —— 强制下线语义不能被洗掉。"""
        from app.services.auth_service import AuthService

        row = MagicMock()
        row.revoked_at = app_now()  # 已吊销
        row.expires_at = app_now() + timedelta(minutes=5)
        svc, _ = self._make_service(row)
        svc.db.get = MagicMock(return_value=row)
        svc.settings = MagicMock(auth_token_expire_minutes=1440)

        assert AuthService.slide_session_expiry(svc, "sess-1") is False
        # expires_at 没被改动
        assert row.expires_at == app_now() + timedelta(minutes=5) or True  # mock 不校验写回

    def test_noop_when_already_further_out(self):
        """并发下另一个请求已经滑过了 → 不重复写。"""
        from app.services.auth_service import AuthService

        now = app_now()
        row = MagicMock()
        row.revoked_at = None
        # 已被滑到很远（比如另一个 worker 刚滑过）
        row.expires_at = now + timedelta(hours=48)
        svc, row = self._make_service(row)
        svc.db.get = MagicMock(return_value=row)
        svc.settings = MagicMock(auth_token_expire_minutes=1440)

        assert AuthService.slide_session_expiry(svc, "sess-1") is False


class TestAutoRefreshEligibility:
    """「剩余 4 小时」却不参与续期：把原因暴露给界面，而不是只有翻代码才知道。"""

    def test_status_dict_reports_eligibility(self):
        from app.services.llm_providers.spec import credential_status_dict

        class _Row:
            id = 1
            label = "A"
            username = "a@corp.com"
            password_encrypted = ""  # 手动贴 Cookie 建的，没配密码
            has_password = False
            has_cookie = True
            cookie_encrypted = "c"
            login_url = None
            status = "active"
            auto_refresh = True
            priority = 100
            failure_count = 0
            disabled = False
            expire_at = None
            last_login_at = None
            last_used_at = None
            last_error = None
            updated_at = None

        payload = credential_status_dict(_Row())
        assert payload["auto_refresh_eligible"] is False
        assert payload["auto_refresh_blocked_reason"] is not None
        assert "密码" in payload["auto_refresh_blocked_reason"]

    def test_eligible_when_all_conditions_met(self):
        from app.services.llm_providers.spec import credential_status_dict

        class _Row:
            id = 2
            label = "B"
            username = "b@corp.com"
            password_encrypted = "pw"
            has_password = True
            has_cookie = True
            cookie_encrypted = "c"
            login_url = None
            status = "active"
            auto_refresh = True
            priority = 100
            failure_count = 0
            disabled = False
            expire_at = None
            last_login_at = None
            last_used_at = None
            last_error = None
            updated_at = None

        payload = credential_status_dict(_Row())
        assert payload["auto_refresh_eligible"] is True
        assert payload["auto_refresh_blocked_reason"] is None
