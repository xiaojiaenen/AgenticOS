"""TECH-DEBT-2026-09：agent 服务包拆分后新模块的直接单测。

覆盖：
- factory：中间件栈构建 / 工具注册表构建 / 并发补丁应用
- artifacts：项目 slug 推断（WEBSITES_DIR 注入临时目录）
- prompts：资源文件目录注入文案渲染
- service 门面：公共 API re-export 完整性
- session_storage：save_session_meta 单事务合并
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.agent_profile_service import RuntimeAgentProfile


def _make_profile(**overrides) -> RuntimeAgentProfile:
    defaults = dict(
        profile_id=None,
        name="general",
        slug="general",
        response_mode="general",
        system_prompt="test",
        builtin_tools=("calc", "time"),
        approval_tools=(),
        signature="",
        skills=(),
    )
    defaults.update(overrides)
    return RuntimeAgentProfile(**defaults)


class TestAgentFactoryMiddlewareStack:
    """factory.py：中间件栈构建。"""

    def _make_factory(self):
        from app.services.agent.factory import AgentFactory
        from app.services.approval_manager import ApprovalManager
        from cachetools import TTLCache

        class _FactoryHarness(AgentFactory):
            def __init__(self) -> None:
                # model_copy：避免污染全局 lru_cache 的共享 Settings 单例
                self.settings = get_settings().model_copy()
                self.approval_manager = ApprovalManager(timeout_seconds=1)
                self._agents = TTLCache(maxsize=2, ttl=60)

        return _FactoryHarness()

    def test_middleware_stack_general_dev(self):
        from wuwei import LLMGateway

        factory = self._make_factory()
        factory.settings.environment = "development"
        stack = factory._build_middleware_stack(_make_profile(), LLMGateway.from_env())
        mw_names = [type(m).__name__ for m in stack.middlewares]
        # 按继承关系判断而不是类名字符串 —— 装配可能换成带可观测性的子类
        # （ObservableCompressionMiddleware），写死类名会在合理替换时误报。
        from wuwei.middleware import ContextCompressionMiddleware

        assert any(
            isinstance(m, ContextCompressionMiddleware) or "ContextCompressionMiddleware" in type(m).__name__
            for m in stack.middlewares
        ), f"缺少压缩中间件（含其子类）: {mw_names}"
        assert "ThinkingHistoryCompatibilityMiddleware" in mw_names
        assert "LoggingMiddleware" in mw_names
        assert "HitlMiddleware" not in mw_names  # approval_tools 为空

    def test_middleware_stack_with_approval_adds_lenient_hitl(self):
        from wuwei import LLMGateway

        factory = self._make_factory()
        stack = factory._build_middleware_stack(
            _make_profile(approval_tools=frozenset({"file_to_md"})), LLMGateway.from_env()
        )
        mw_names = [type(m).__name__ for m in stack.middlewares]
        assert "LenientHitlMiddleware" in mw_names

    def test_middleware_stack_hitl_disabled(self):
        from wuwei import LLMGateway

        factory = self._make_factory()
        factory.settings.hitl_enabled = False
        stack = factory._build_middleware_stack(
            _make_profile(approval_tools=frozenset({"file_to_md"})), LLMGateway.from_env()
        )
        mw_names = [type(m).__name__ for m in stack.middlewares]
        assert "LenientHitlMiddleware" not in mw_names

    def test_build_tool_registry_basic(self):
        from app.services.agent.factory import AgentFactory

        registry, ext_instruction = AgentFactory._build_tool_registry(_make_profile())
        tool_names = [t.name for t in registry.list_tools()]
        assert "calculate" in tool_names
        assert "get_now" in tool_names
        assert "__tool_rejected__" in tool_names
        assert ext_instruction == ""

    def test_concurrent_tool_execution_relies_on_upstream(self):
        """并发工具执行由上游原生实现，不再有 monkey-patch。

        这里曾经有一份 230 行的 ``AgentRunner.stream_events`` 整体重写
        （TECH-DEBT），目的是让安全工具并发执行。wuwei 3.2.1 的
        ``ToolExecutor.execute(concurrent=True)`` 已原生实现同样的分批并发，
        补丁已删除 —— 它整段复制了上游执行循环，上游一改就静默落后。

        守护点：**不要重新引入这个补丁**。断言我们的 factory 里已经没有那个
        覆盖实现，且 ``AgentRunner.stream_events`` 仍指向上游自己的函数。
        """
        from wuwei.runtime.agent_runner import AgentRunner
        from wuwei.tools.executor import ToolExecutor

        from app.services.agent import factory as agent_factory

        # 补丁符号必须已消失
        assert not hasattr(agent_factory, "_patched_stream_events")
        assert not hasattr(agent_factory, "_original_stream_events")

        # stream_events 必须还是上游自己的实现（没有被我们换掉）
        assert AgentRunner.stream_events.__module__ == "wuwei.runtime.agent_runner"

        # 上游自己提供并发入口
        import inspect

        signature = inspect.signature(ToolExecutor.execute)
        assert "concurrent" in signature.parameters


class TestArtifactSlugInference:
    """artifacts.py：slug 推断必须按会话过滤（注入临时 WEBSITES_DIR）。

    回归背景：旧实现扫全库取「最近修改的 dist」，data/websites 是所有用户
    共用的 —— 别的会话/用户刚构建完，artifact_ready 就把那个项目推给当前
    用户，表现为"预览里显示的不是我刚生成的网站，点刷新才对"。
    """

    def test_returns_none_without_session_id(self, tmp_path: Path, monkeypatch):
        from app.services.agent import artifacts as agent_artifacts

        dist = tmp_path / "u1_s123_v1" / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path)
        # 不给 session_id 绝不能全局兜底，否则就是跨会话串号
        assert agent_artifacts.ArtifactFactory._infer_project_slug_from_tools() is None

    def test_returns_none_when_dir_missing(self, tmp_path: Path, monkeypatch):
        from app.services.agent import artifacts as agent_artifacts

        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path / "nonexistent")
        assert agent_artifacts.ArtifactFactory._infer_project_slug_from_tools("s1") is None

    def test_returns_none_when_no_dist(self, tmp_path: Path, monkeypatch):
        from app.services.agent import artifacts as agent_artifacts

        (tmp_path / "u1_s123_v1").mkdir()
        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path)
        assert agent_artifacts.ArtifactFactory._infer_project_slug_from_tools("123") is None

    def test_returns_highest_version_for_session(self, tmp_path: Path, monkeypatch):
        """同会话多轮迭代：取版本号最大的（比 mtime 可靠）。"""
        from app.services.agent import artifacts as agent_artifacts
        import os

        for ver, mtime in ((1, 2_000_000_000), (2, 1_000_000_000)):
            dist = tmp_path / f"u1_s123_v{ver}" / "dist"
            dist.mkdir(parents=True)
            index = dist / "index.html"
            index.write_text("<html></html>", encoding="utf-8")
            os.utime(index, (mtime, mtime))

        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path)
        slug = agent_artifacts.ArtifactFactory._infer_project_slug_from_tools("123")
        assert slug == "u1_s123_v2"

    def test_ignores_other_sessions_and_hidden_dirs(self, tmp_path: Path, monkeypatch):
        """跨会话 + 跨用户隔离 + 隐藏目录跳过（回归：全库扫描会串号）。"""
        from app.services.agent import artifacts as agent_artifacts

        for name in ("u1_s123_v1", "u1_s999_v9", "u7_s123_v9", ".hidden"):
            dist = tmp_path / name / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<html></html>", encoding="utf-8")

        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path)
        # 同会话不同用户的目录（u7_s123_v9）必须被排除
        slug = agent_artifacts.ArtifactFactory._infer_project_slug_from_tools("123", user_id=1)
        assert slug == "u1_s123_v1"

    def test_inline_dist_assets_inlines_css_and_js(self, tmp_path: Path):
        from app.services.agent import artifacts as agent_artifacts

        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "assets" / "style.css").write_text("body{color:red}", encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        html = (
            '<html><head><link rel="stylesheet" href="/assets/style.css" /></head>'
            '<body><script src="/assets/app.js"></script>'
            '<script src="https://cdn.example.com/x.js"></script></body></html>'
        )
        result = agent_artifacts.ArtifactFactory._inline_dist_assets(dist, html)
        assert "<style>body{color:red}</style>" in result
        # 原实现保留 src 前捕获组（含空格）：<script >console.log(1)</script>
        assert ">console.log(1)</script>" in result
        assert "/assets/app.js" not in result
        assert 'src="https://cdn.example.com/x.js"' in result  # 外链保留


class TestPreviewTokenOwnership:
    """website_preview._assert_can_preview_project：现签预览令牌前必须验归属。

    没有这道校验时，任何登录用户拿到别人的 slug（data/websites 目录名可枚举）
    就能签出有效令牌看别人的网站；serve_preview 只验签名与 slug，分不清令牌
    是谁替谁签的。
    """

    @staticmethod
    def _user(uid: int, role: str = "user"):
        from types import SimpleNamespace

        return SimpleNamespace(id=uid, role=role)

    def _guard(self, slug: str, user):
        from fastapi import HTTPException

        from app.api.v1.endpoints.website_preview import _assert_can_preview_project

        return _assert_can_preview_project(slug, user)

    def test_owner_can_preview_own_project(self):
        self._guard("u493_s123_v1", self._user(493))

    def test_admin_can_preview_any_project(self):
        self._guard("u7_s999_v9", self._user(493, role="admin"))

    def test_other_users_project_rejected(self):
        import pytest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._guard("u7_s999_v9", self._user(493))
        assert exc.value.status_code == 403

    def test_malformed_slug_rejected(self):
        import pytest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._guard("proj-a", self._user(493))
        assert exc.value.status_code == 400


class TestDecisionOwnership:
    """decision_tools：决策归属登记 / 按 session 清理。

    回归背景：/decisions/{id}/decision 端点原本不校验调用者身份，decision_id
    又只有 8 位 hex —— 任何登录用户知道 id 就能替别人回答决策。端点现在通过
    get_decision_session → ensure_session_access 校验归属，依赖本组测试保护的
    登记数据。另外 cleanup_session_decisions 曾全表遍历取消 Future，一个会话
    的流结束会误取消其它会话正在等待的决策 —— 一并回归。
    """

    def test_register_and_peek_session(self):
        import asyncio

        from app.tools.decision_tools import (
            get_decision_session,
            register_decision,
            _forget_decision,
        )

        loop = asyncio.new_event_loop()
        try:
            future: asyncio.Future[str] = loop.create_future()
            register_decision("d1", "s1", future)
            assert get_decision_session("d1") == "s1"
            _forget_decision("d1")
            assert get_decision_session("d1") is None
        finally:
            loop.close()

    def test_resolve_pops_future_and_ownership(self):
        import asyncio

        from app.tools.decision_tools import (
            get_decision_session,
            register_decision,
            resolve_decision,
        )

        loop = asyncio.new_event_loop()
        try:
            future: asyncio.Future[str] = loop.create_future()
            register_decision("d2", "s1", future)

            async def _run():
                assert await resolve_decision("d2", "选项A") is True

            assert loop.run_until_complete(_run()) is None
            assert get_decision_session("d2") is None
            assert loop.run_until_complete(resolve_decision("d2", "again")) is False  # 已弹出
        finally:
            loop.close()

    def test_cleanup_scoped_to_session(self):
        """清理 s1 不得误伤 s2 正在等待的决策（历史上是全表遍历）。"""
        import asyncio

        from app.tools.decision_tools import (
            cleanup_session_decisions,
            get_decision_session,
            register_decision,
            resolve_decision,
        )

        # 用独立 loop：asyncio.run 会清掉主线程 current event loop，
        # 让后续测试的 get_event_loop 直接 RuntimeError
        loop = asyncio.new_event_loop()
        try:
            f1: asyncio.Future[str] = loop.create_future()
            f2: asyncio.Future[str] = loop.create_future()
            register_decision("d-s1", "s1", f1)
            register_decision("d-s2", "s2", f2)

            cleanup_session_decisions("s1")
            assert get_decision_session("d-s1") is None
            assert f1.cancelled()
            # s2 的决策完好：仍可正常 resolve
            assert get_decision_session("d-s2") == "s2"

            async def _run():
                assert await resolve_decision("d-s2", "保留") is True

            assert loop.run_until_complete(_run()) is None
        finally:
            loop.close()

    def test_unknown_decision_has_no_session(self):
        from app.tools.decision_tools import get_decision_session

        assert get_decision_session("nope") is None


class TestPromptCatalogInjection:
    """prompts.py：资源文件文案渲染。"""

    def test_design_catalog_contains_theme_guide(self):
        from app.services.agent.prompts import inject_design_catalog

        result = inject_design_catalog("BASE")
        assert result.startswith("BASE")
        assert "## ⭐ 主题选择" in result
        assert "**快速决策：**" in result
        assert "## Token 语义速查" in result
        assert "CURRENT TIME:" in result
        assert "{theme_count}" not in result  # 占位符已全部渲染

    @pytest.mark.anyio
    async def test_website_catalog_contains_workflow(self):
        from app.services.agent.prompts import inject_website_catalog

        result = await inject_website_catalog("BASE")
        assert result.startswith("BASE")
        assert "## Website 模式资源速查" in result
        assert "### 致命错误警告" in result
        assert "copy_template" in result

    def test_service_binds_prompts_as_staticmethods(self):
        from app.services.agent_service import AgentService

        assert AgentService._inject_design_catalog("X").startswith("X")
        assert AgentService._scan_website_catalog.__doc__ is not None


class TestFacadeReexports:
    """service 门面：agent_service 兼容层公共符号 re-export 完整性。"""

    def test_import_all_public_symbols(self):
        from app.services.agent_service import (  # noqa: F401
            AgentService,
            MAX_STEPS_LIMIT_MESSAGE,
            SKILL_INSTRUCTION,
            LenientHitlMiddleware,
            SkillInstructionMiddleware,
            ThinkingHistoryCompatibilityMiddleware,
            clear_agent_service_cache,
            get_agent_service,
        )
        from app.services import agent_service as compat
        from app.services.agent.service import (
            AgentService as _S,
            clear_agent_service_cache as _c,
            get_agent_service as _g,
        )
        from app.services.agent.factory import (
            MAX_STEPS_LIMIT_MESSAGE as _m,
            ThinkingHistoryCompatibilityMiddleware as _t,
        )

        assert compat.AgentService is _S
        assert compat.get_agent_service is _g
        assert compat.clear_agent_service_cache is _c
        assert compat.MAX_STEPS_LIMIT_MESSAGE is _m
        assert compat.ThinkingHistoryCompatibilityMiddleware is _t
        assert compat._current_session_id.get() is None

    def test_agent_service_composes_all_modules(self):
        from app.services.agent_service import AgentService
        from app.services.agent.artifacts import ArtifactFactory
        from app.services.agent.factory import AgentFactory
        from app.services.agent.orchestrator import StreamOrchestrator

        assert issubclass(AgentService, AgentFactory)
        assert issubclass(AgentService, StreamOrchestrator)
        assert issubclass(AgentService, ArtifactFactory)

    def test_facade_public_methods_present(self):
        from app.services.agent_service import AgentService

        for method in (
            "stream_chat",
            "ensure_ready",
            "ensure_session_access",
            "decide_approval",
            "get_session_state",
            "get_ppt_artifact",
            "export_pptx",
            "list_user_sessions",
            "delete_session",
            "submit_user_input",
            "clear_agent_cache",
            "_get_agent",
            "_build_tool_registry",
            "_build_middleware_stack",
            "_ensure_record_owner",
            "_create_ppt_artifact",
            "_create_website_artifact",
            "_export_pptx_sync",
            "_inject_design_catalog",
            "_inject_website_catalog",
        ):
            assert hasattr(AgentService, method), f"missing {method}"

    def test_build_tool_registry_source_has_mcp(self):
        """既有测试依赖 inspect.getsource(AgentService._build_tool_registry) 含 mcp_service。"""
        import inspect
        from app.services.agent_service import AgentService

        src = inspect.getsource(AgentService._build_tool_registry)
        assert "mcp_service" in src


class TestSaveSessionMetaTransaction:
    """session_storage.save_session_meta：三段事务合并。"""

    @pytest.mark.anyio
    async def test_save_session_meta_creates_and_binds(self, tmp_path, monkeypatch):
        import asyncio
        from app.db.session import SessionLocal
        from app.db.models import AgentSessionModel
        from app.services.session_storage import DatabaseAgentStorage
        from sqlalchemy import text

        class _FakeSession:
            session_id = "tx-session"
            system_prompt = "sp"
            max_steps = 10
            parallel_tool_calls = False
            summary = None
            metadata = {"user_id": 7, "agent_profile_id": 3}
            last_usage = {}
            last_latency_ms = 0
            last_llm_calls = 0

        storage = DatabaseAgentStorage(session_factory=SessionLocal)
        await storage.save_session_meta(
            _FakeSession(), user_id=7, agent_profile_id=3
        )

        def _read():
            with SessionLocal() as db:
                row = db.get(AgentSessionModel, "tx-session")
                return row

        row = await asyncio.to_thread(_read)
        try:
            assert row is not None
            assert row.user_id == 7
            assert row.agent_profile_id == 3
            assert row.max_steps == 10
        finally:
            def _cleanup():
                with SessionLocal() as db:
                    db.execute(text("DELETE FROM agent_sessions WHERE session_id = 'tx-session'"))
                    db.commit()
            await asyncio.to_thread(_cleanup)
