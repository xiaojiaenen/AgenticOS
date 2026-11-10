"""run 级预算断路器（wuwei BudgetMiddleware 接入）+ 流式端点每用户频控 回归测试。

背景：wuwei 3.3.0 自带 ``BudgetMiddleware``（token/成本断路），项目此前
一直没用 —— 长任务绕圈/重试可能烧掉预估 10-20 倍 token，只能靠
agent_max_steps 的步数上限兜底，token 维度无任何护栏。接入点：

- factory._build_run_budget：配置 → Budget（未启用/配置非法降级 None）
- factory._build_middleware_stack：预算中间件插在最前（超限省掉本次调用）
- 超限行为：硬阈值抛 BudgetExhausted → 上游 runner 转 SSE error 事件；
  软阈值（80%）只记一次 WARNING。

频控：/agent/stream 此前无每用户限流（llm_gate 只是全站并发闸），
单个用户刷运行能把并发配额刷满饿死别人。现在固定窗口频控 + 管理员豁免。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel
from app.db.session import create_db_session


# ---------------------------------------------------------------------------
# 复用件：profile / factory / 用户 token（与 test_agent_modules 同款，就地复制
# 避免 cross-test-module import 脆弱性）
# ---------------------------------------------------------------------------

def _make_profile(**overrides) -> "RuntimeAgentProfile":
    from app.services.agent_profile_service import RuntimeAgentProfile

    defaults = dict(
        profile_id=None,
        name="budget-test",
        slug="budget-test",
        response_mode="general",
        system_prompt="",
        builtin_tools=("calc",),
        approval_tools=frozenset(),
        signature=(),
        skills=(),
    )
    defaults.update(overrides)
    return RuntimeAgentProfile(**defaults)


def _make_factory():
    from cachetools import TTLCache

    from app.services.agent.factory import AgentFactory
    from app.services.approval_manager import ApprovalManager

    class _FactoryHarness(AgentFactory):
        def __init__(self) -> None:
            # model_copy：避免污染全局 lru_cache 的共享 Settings 单例
            self.settings = get_settings().model_copy()
            self.approval_manager = ApprovalManager(timeout_seconds=1)
            self._agents = TTLCache(maxsize=2, ttl=60)

    return _FactoryHarness()


def cleanup_test_users(*emails: str) -> None:
    with create_db_session() as db:
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def create_user_token(email: str, *, role: str = "user") -> str:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name="Budget Test",
            password_hash=hash_password("password-123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    settings = get_settings()
    return create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


# ---------------------------------------------------------------------------
# _build_run_budget
# ---------------------------------------------------------------------------

class TestBuildRunBudget:
    """factory._build_run_budget：配置 → Budget 的映射与降级。"""

    def test_off_by_default(self):
        factory = _make_factory()
        assert factory.settings.agent_budget_max_tokens is None
        assert factory.settings.agent_budget_max_cost_usd is None
        assert factory._build_run_budget() is None, "默认不启用，不改变既有部署行为"

    def test_token_budget_enabled(self):
        factory = _make_factory()
        factory.settings.agent_budget_max_tokens = 100_000
        budget = factory._build_run_budget()
        assert budget is not None
        assert budget.max_tokens == 100_000
        assert budget.max_cost_usd is None
        # 步数上限刻意不进 Budget：session.max_steps 由 runner 优雅收尾，
        # 放进预算会把优雅收尾变成 BudgetExhausted 错误
        assert budget.max_steps is None

    def test_invalid_config_degrades_to_none(self):
        factory = _make_factory()
        factory.settings.agent_budget_max_tokens = -1  # 负数非法
        assert factory._build_run_budget() is None, "配置非法降级为无预算，不能炸掉所有对话"

    def test_invalid_on_exhausted_degrades_to_none(self):
        factory = _make_factory()
        factory.settings.agent_budget_max_tokens = 1000
        factory.settings.agent_budget_on_exhausted = "explode"  # 只支持 abort/warn
        assert factory._build_run_budget() is None


# ---------------------------------------------------------------------------
# 中间件栈装配
# ---------------------------------------------------------------------------

class TestMiddlewareStackWiring:
    """预算中间件的装配位置与启停。"""

    def test_stack_without_budget_when_unset(self):
        from wuwei import LLMGateway

        factory = _make_factory()
        stack = factory._build_middleware_stack(_make_profile(), LLMGateway.from_env())
        names = [type(m).__name__ for m in stack.middlewares]
        assert "BudgetMiddleware" not in names

    def test_stack_with_budget_first(self):
        from wuwei import LLMGateway
        from wuwei.middleware.budget import BudgetMiddleware

        factory = _make_factory()
        factory.settings.agent_budget_max_tokens = 100_000
        stack = factory._build_middleware_stack(
            _make_profile(), LLMGateway.from_env(), model_name="glm-4"
        )
        middlewares = stack.middlewares
        assert isinstance(middlewares[0], BudgetMiddleware), (
            "预算放最前：超限时省掉本次 LLM 调用，不被其他中间件白耗一轮"
        )
        assert middlewares[0].model == "glm-4"


# ---------------------------------------------------------------------------
# BudgetMiddleware 本体行为
# ---------------------------------------------------------------------------

class TestBudgetMiddlewareBehavior:
    """BudgetMiddleware 行为（直接构造上下文验证，不起真实 agent）。"""

    def _ctx(self, usage_total: dict, usage_available: bool = True):
        from wuwei.graph.state import State
        from wuwei.middleware.base import MiddlewareContext

        return MiddlewareContext(
            state=State(messages=[]),
            config={},
            metadata={
                "usage_total": usage_total,
                "usage_available": usage_available,
                "llm_calls": 1,
            },
        )

    @staticmethod
    def _mw(max_tokens=None, max_cost_usd=None, on_exhausted="abort"):
        from wuwei.middleware.budget import Budget, BudgetMiddleware

        return BudgetMiddleware(
            Budget(max_tokens=max_tokens, max_cost_usd=max_cost_usd, on_exhausted=on_exhausted),
            model="glm-4",
        )

    @pytest.mark.asyncio
    async def test_hard_abort_on_token_cap(self):
        from wuwei.middleware.budget import BudgetExhausted

        ctx = self._ctx({"prompt_tokens": 900, "completion_tokens": 200, "total_tokens": 1100})
        with pytest.raises(BudgetExhausted):
            await self._mw(max_tokens=1000).before_llm(ctx)

    @pytest.mark.asyncio
    async def test_warn_mode_continues(self):
        ctx = self._ctx({"prompt_tokens": 900, "completion_tokens": 200, "total_tokens": 1100})
        mw = self._mw(max_tokens=1000, on_exhausted="warn")
        assert await mw.before_llm(ctx) is ctx, "warn 模式只记日志不中断"

    @pytest.mark.asyncio
    async def test_soft_threshold_warns_once(self):
        # 1100/1250 = 88% ≥ 软阈值 80%，未达硬阈值
        ctx = self._ctx({"prompt_tokens": 900, "completion_tokens": 200, "total_tokens": 1100})
        mw = self._mw(max_tokens=1250)
        assert await mw.before_llm(ctx) is ctx
        assert ctx.metadata.get("_budget_warned") is True

    @pytest.mark.asyncio
    async def test_aborts_when_usage_unavailable(self):
        """模型不回传 usage 时 token/成本预算直接断路（不可靠的预算宁可不执行）。"""
        from wuwei.middleware.budget import BudgetExhausted

        ctx = self._ctx(
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            usage_available=False,
        )
        with pytest.raises(BudgetExhausted, match="usage"):
            await self._mw(max_tokens=100_000).before_llm(ctx)


# ---------------------------------------------------------------------------
# /agent/stream 每用户固定窗口频控
# ---------------------------------------------------------------------------

class TestStreamRateLimit:
    def _clear_window_mem(self) -> None:
        from app.services import rate_limiter as rl

        with rl._window_mem_lock:
            rl._window_mem.clear()

    def test_window_quota_memory_fallback(self, monkeypatch):
        from app.services import rate_limiter as rl

        monkeypatch.setattr(rl, "get_redis_sync", lambda: None)
        self._clear_window_mem()

        first, _ = rl.check_window_quota("agent_stream", "t1", limit=2, window_seconds=60)
        second, _ = rl.check_window_quota("agent_stream", "t1", limit=2, window_seconds=60)
        third, reset_in = rl.check_window_quota("agent_stream", "t1", limit=2, window_seconds=60)
        assert (first, second) == (True, True)
        assert third is False, "窗口内第 limit+1 次应拒绝"
        assert 0 < reset_in <= 60
        assert rl.check_window_quota("agent_stream", "t1", limit=0, window_seconds=60)[0], (
            "limit<=0 表示关闭频控"
        )
        self._clear_window_mem()

    def test_window_quota_window_rolls(self, monkeypatch):
        import time as time_mod

        from app.services import rate_limiter as rl

        monkeypatch.setattr(rl, "get_redis_sync", lambda: None)
        self._clear_window_mem()
        for _ in range(3):
            rl.check_window_quota("agent_stream", "t2", limit=2, window_seconds=1)
        assert rl.check_window_quota("agent_stream", "t2", limit=2, window_seconds=1)[0] is False
        time_mod.sleep(1.05)
        assert rl.check_window_quota("agent_stream", "t2", limit=2, window_seconds=1)[0] is True, (
            "窗口滚动后重新放行"
        )
        self._clear_window_mem()

    def test_stream_endpoint_429_then_admin_exempt(self):
        """端点装配：普通用户第 2 次 429 + Retry-After；管理员豁免。

        用 FakeAgentService 替身走 HTTP 层（真实 AgentService 在测试环境
        没有 LLM 配置），频控发生在 ensure_ready 之后、流开始之前。
        """
        from app.main import app
        from app.services import rate_limiter as rl
        from app.services.agent_service import get_agent_service

        class FakeAgentService:
            def ensure_ready(self) -> None:
                return None

            async def ensure_session_access(self, request, user) -> None:
                return None

            async def stream_chat(self, request, user):
                yield {"event": "session", "data": {"session_id": "s-rate"}}
                yield {"event": "done", "data": {"session_id": "s-rate", "finish_reason": "stop", "usage": None}}

        monkeypatch_ok = rl.get_redis_sync  # noqa: F841 —— 仅确认模块可导入
        settings = get_settings().model_copy()
        settings.agent_stream_rate_limit = 1
        settings.agent_stream_rate_window_seconds = 300

        app.dependency_overrides[get_agent_service] = lambda: FakeAgentService()
        email_user, email_admin = "budget-rate-u@example.com", "budget-rate-a@example.com"
        try:
            # 频控统一走进程内 fallback（测试环境不依赖 Redis 状态）
            with patch.object(rl, "get_redis_sync", lambda: None):
                self._clear_window_mem()
                with patch(
                    "app.api.v1.endpoints.agent.get_settings", return_value=settings
                ):
                    with TestClient(app) as client:
                        user_token = create_user_token(email_user)
                        headers = {"Authorization": f"Bearer {user_token}"}
                        body = {"message": "hi"}
                        first = client.post("/api/v1/agent/stream", json=body, headers=headers)
                        assert first.status_code == 200, first.text[:200]
                        second = client.post("/api/v1/agent/stream", json=body, headers=headers)
                        assert second.status_code == 429, second.text[:200]
                        assert "Retry-After" in second.headers

                        admin_token = create_user_token(email_admin, role="admin")
                        admin_headers = {"Authorization": f"Bearer {admin_token}"}
                        for _ in range(3):
                            resp = client.post(
                                "/api/v1/agent/stream", json=body, headers=admin_headers
                            )
                            assert resp.status_code == 200, (
                                f"管理员应豁免频控: {resp.status_code} {resp.text[:200]}"
                            )
        finally:
            cleanup_test_users(email_user, email_admin)
            app.dependency_overrides.clear()
            self._clear_window_mem()
