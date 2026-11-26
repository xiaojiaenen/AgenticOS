"""run 级预算断路器（自研 Budget，DeepAgents 无等价计费语义）+ 频控回归。

背景：长任务绕圈/重试可能烧掉预估 10-20 倍 token，agent_max_steps 只兜步数，
token/成本维度需要独立护栏。接入点：

- factory._build_run_budget：配置 → Budget（未启用/配置非法降级 None）
- engine：每次 AIMessage 产出后 check_budget（含纯文本回答）
- 超限行为：硬阈值抛 BudgetExhausted → SSE error 事件；软阈值（80%）每 run 只记一次 WARNING。

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

def _make_profile(**overrides) -> "object":  # 返回 RuntimeAgentProfile（函数内 import，见下）
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

class TestEngineBudgetWiring:
    """引擎侧预算装配：settings 配置 → LangGraphAgent.budget 字段。"""

    def test_budget_none_when_unset(self):
        from app.core.config import get_settings
        from app.services.agent.factory import AgentFactory

        factory = AgentFactory.__new__(AgentFactory)
        factory.settings = get_settings().model_copy()
        assert factory._build_run_budget() is None

    def test_budget_built_when_configured(self):
        from app.core.config import get_settings
        from app.services.agent.factory import AgentFactory
        from app.services.agent.native.budget import Budget

        factory = AgentFactory.__new__(AgentFactory)
        factory.settings = get_settings().model_copy()
        factory.settings.agent_budget_max_tokens = 100_000
        budget = factory._build_run_budget()
        assert isinstance(budget, Budget)
        assert budget.max_tokens == 100_000


# ---------------------------------------------------------------------------
# BudgetMiddleware 本体行为
# ---------------------------------------------------------------------------

class TestBudgetCheckBehavior:
    """check_budget 行为验证（原 BudgetMiddleware 语义，移植为函数式检查）。"""

    @staticmethod
    def _spend(model="glm-4"):
        from app.services.agent.native.budget import RunSpend

        return RunSpend(model=model)

    def test_hard_abort_on_token_cap(self):
        from app.services.agent.native.budget import Budget, BudgetExhausted, check_budget

        budget = Budget(max_tokens=1000)
        with pytest.raises(BudgetExhausted):
            check_budget(budget, {"total_tokens": 1100}, steps=1, spend=self._spend())

    def test_warn_mode_continues(self):
        from app.services.agent.native.budget import Budget, check_budget

        budget = Budget(max_tokens=1000, on_exhausted="warn")
        spend = self._spend()
        check_budget(budget, {"total_tokens": 1100}, steps=1, spend=spend)  # 不应抛出

    def test_soft_threshold_warns_once(self):
        from app.services.agent.native.budget import Budget, check_budget

        budget = Budget(max_tokens=1250)
        spend = self._spend()
        check_budget(budget, {"total_tokens": 1100}, steps=1, spend=spend)
        assert spend.warned is True, "软阈值只警告一次"

    def test_aborts_when_usage_unavailable(self):
        """模型不回传 usage 时 token/成本预算直接断路（不可靠的预算宁可不执行）。"""
        from app.services.agent.native.budget import Budget, BudgetExhausted, check_budget

        budget = Budget(max_tokens=100_000)
        with pytest.raises(BudgetExhausted, match="usage"):
            check_budget(
                budget,
                {"total_tokens": 0},
                steps=1,
                spend=self._spend(),
                usage_available=False,
            )

    def test_cost_budget_by_price_table(self):
        from app.services.agent.native.budget import Budget, BudgetExhausted, check_budget, estimate_cost

        usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000}
        # glm-4 价格 0.1/Mtok → 1M tokens = $0.1
        assert estimate_cost(usage, "glm-4") == pytest.approx(0.1)
        budget = Budget(max_cost_usd=0.05)
        spend = self._spend("glm-4")
        # spend.cost_usd 由引擎的 _spend() 计算；测试里同样先算再传入
        spend.cost_usd = estimate_cost(usage, "glm-4")
        with pytest.raises(BudgetExhausted):
            check_budget(budget, usage, steps=1, spend=spend)



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


def test_estimate_cost_accepts_both_usage_key_sets():
    """成本估算必须同时认网关原生键与 LangChain/DeepAgents 键。

    快照只输出 input_tokens/output_tokens 时，旧实现读 prompt_tokens/
    completion_tokens 恒返回 0，导致 AGENT_BUDGET_MAX_COST_USD 完全失效。
    """
    from app.services.agent.native.budget import estimate_cost

    legacy = estimate_cost(
        {"prompt_tokens": 2_000_000, "completion_tokens": 1_000_000}, "gpt-4o"
    )
    native = estimate_cost(
        {"input_tokens": 2_000_000, "output_tokens": 1_000_000}, "gpt-4o"
    )
    assert native == legacy
    assert legacy > 0

    from app.services.agent.langgraph_engine.engine import _UsageTracker

    t = _UsageTracker()
    t.add_usage({"input_tokens": 1000, "output_tokens": 500})
    snap = t.snapshot()
    assert snap["input_tokens"] == 1000
    assert snap["prompt_tokens"] == 1000
    assert snap["completion_tokens"] == 500
    assert estimate_cost(snap, "gpt-4o") > 0


def test_plan_mode_only_registers_read_only_tools():
    """计划模式必须从注册表移除所有写工具（发邮件/部署/生图/写文件等）。

    之前只过滤了 builtin 插件循环，app/tools/*.py 注册的写工具仍可用，
    导致「只做只读调研」的承诺失效。这里直接验证注册表结果。
    """
    from app.services.agent.factory import AgentFactory
    from app.services.agent_profile_service import RuntimeAgentProfile
    from app.services.tool_config_service import DEFAULT_MODE_TOOLS

    tools = tuple(DEFAULT_MODE_TOOLS["general"].keys())
    profile = RuntimeAgentProfile(
        profile_id=1, name="plan-test", slug="plan-test", response_mode="general",
        system_prompt="", builtin_tools=tools, approval_tools=frozenset(),
        signature=tuple((name, True, False) for name in tools), skills=(),
        plan_mode=True, allowed_tools=frozenset(tools),
    )
    registry, _ = AgentFactory._build_tool_registry(profile)
    names = set(t.name for t in registry.list_tools())

    # 只读工具保留
    assert "list_files" in names
    assert "read_text_file" in names
    # 写工具必须全部移除
    for write_tool in ("send_email", "deploy_website", "generate_image", "write_text_file", "python", "build_website"):
        assert write_tool not in names, f"计划模式不应注册写工具: {write_tool}"
