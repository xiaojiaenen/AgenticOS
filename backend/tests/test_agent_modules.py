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
        assert "ContextCompressionMiddleware" in mw_names
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

    def test_concurrency_patch_applied_at_import(self):
        """monkey-patch 在模块导入时应用（时机不变）。"""
        from wuwei.runtime.agent_runner import AgentRunner
        from app.services.agent import factory as agent_factory

        assert AgentRunner.stream_events is agent_factory._patched_stream_events
        assert "TECH-DEBT" in (agent_factory._patched_stream_events.__doc__ or "")


class TestArtifactSlugInference:
    """artifacts.py：slug 推断（注入临时 WEBSITES_DIR）。"""

    def test_returns_none_when_dir_missing(self, tmp_path: Path, monkeypatch):
        from app.services.agent import artifacts as agent_artifacts

        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path / "nonexistent")
        assert agent_artifacts.ArtifactFactory._infer_project_slug_from_tools([]) is None

    def test_returns_none_when_no_dist(self, tmp_path: Path, monkeypatch):
        from app.services.agent import artifacts as agent_artifacts

        (tmp_path / "proj-a").mkdir()
        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path)
        assert agent_artifacts.ArtifactFactory._infer_project_slug_from_tools([]) is None

    def test_returns_most_recent_dist(self, tmp_path: Path, monkeypatch):
        from app.services.agent import artifacts as agent_artifacts
        import os

        for name, mtime in (("proj-old", 1_000_000_000), ("proj-new", 2_000_000_000)):
            dist = tmp_path / name / "dist"
            dist.mkdir(parents=True)
            index = dist / "index.html"
            index.write_text("<html></html>", encoding="utf-8")
            os.utime(index, (mtime, mtime))

        # 隐藏目录应被跳过
        dot = tmp_path / ".hidden" / "dist"
        dot.mkdir(parents=True)
        (dot / "index.html").write_text("<html></html>", encoding="utf-8")

        monkeypatch.setattr(agent_artifacts, "WEBSITES_DIR", tmp_path)
        slug = agent_artifacts.ArtifactFactory._infer_project_slug_from_tools([])
        assert slug == "proj-new"

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
