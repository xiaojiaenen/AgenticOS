"""测试 wuwei 2.2.0 重构新增模块"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMultiAgentPptService:
    """测试 Multi-Agent PPT 生成服务"""

    def test_init(self):
        from app.services.multi_agent_ppt_service import MultiAgentPptService
        svc = MultiAgentPptService()
        assert svc.settings is not None

    def test_build_ppt_registry(self):
        from app.services.multi_agent_ppt_service import MultiAgentPptService
        svc = MultiAgentPptService()
        registry = svc._build_ppt_registry()
        tool_names = [t.name for t in registry.list_tools()]
        assert "save_slide" in tool_names
        assert "search_icons" in tool_names

    @pytest.mark.anyio
    async def test_save_slide(self):
        import tempfile
        from pathlib import Path
        from app.services.multi_agent_ppt_service import MultiAgentPptService

        with tempfile.TemporaryDirectory() as tmpdir:
            from app.core import data_path
            original_dir = data_path.PPT_SESSIONS_DIR
            data_path.PPT_SESSIONS_DIR = Path(tmpdir)

            svc = MultiAgentPptService()
            result = await svc._save_slide("test-session", 1, "<svg>test</svg>")

            assert result is True
            slide_path = Path(tmpdir) / "test-session" / "slide_1.svg"
            assert slide_path.exists()
            assert slide_path.read_text() == "<svg>test</svg>"

            data_path.PPT_SESSIONS_DIR = original_dir


class TestPptPipeline:
    """测试 StateGraph PPT Pipeline"""

    def test_init(self):
        from app.services.ppt_pipeline import PptPipeline
        pipeline = PptPipeline()
        assert pipeline.graph is not None

    def test_graph_structure(self):
        from app.services.ppt_pipeline import PptPipeline
        pipeline = PptPipeline()
        nodes = list(pipeline.graph.graph.nodes)
        assert "plan" in nodes
        assert "generate_slides" in nodes
        assert "validate" in nodes
        assert "create_artifact" in nodes

    def test_state_defaults(self):
        from app.services.ppt_pipeline import PptPipelineState
        state = PptPipelineState()
        assert state.user_message == ""
        assert state.pages == []
        assert state.svgs == []
        assert state.error is None

    def test_validate_node_success(self):
        from app.services.ppt_pipeline import PptPipeline, PptPipelineState
        pipeline = PptPipeline()
        state = PptPipelineState()
        state.svgs = [
            '<svg viewBox="0 0 1280 720">page1</svg>',
            '<svg viewBox="0 0 1280 720">page2</svg>',
            '<svg viewBox="0 0 1280 720">page3</svg>',
        ]
        import asyncio
        result = asyncio.run(pipeline._validate_node(state))
        assert len(result.validated_svgs) == 3
        assert result.error is None

    def test_validate_node_insufficient(self):
        from app.services.ppt_pipeline import PptPipeline, PptPipelineState
        pipeline = PptPipeline()
        state = PptPipelineState()
        state.svgs = [
            '<svg viewBox="0 0 1280 720">page1</svg>',
            '<svg viewBox="0 0 1280 720">page2</svg>',
        ]
        import asyncio
        result = asyncio.run(pipeline._validate_node(state))
        assert len(result.validated_svgs) == 0
        assert result.error is not None

    def test_should_retry(self):
        from app.services.ppt_pipeline import PptPipeline, PptPipelineState
        pipeline = PptPipeline()

        state1 = PptPipelineState(error="test error", step=1)
        assert pipeline._should_retry(state1) == "retry"

        state2 = PptPipelineState(error="test error", step=3)
        assert pipeline._should_retry(state2) == "done"

        state3 = PptPipelineState(step=3)
        assert pipeline._should_retry(state3) == "done"


class TestMcpService:
    """测试 MCP 工具集成服务"""

    def test_init(self):
        from app.services.mcp_service import McpService
        svc = McpService()
        assert svc._session_manager is None
        assert svc._tools == []

    def test_get_tools_empty(self):
        from app.services.mcp_service import McpService
        svc = McpService()
        assert svc.get_tools() == []

    def test_singleton(self):
        from app.services.mcp_service import get_mcp_service
        svc1 = get_mcp_service()
        svc2 = get_mcp_service()
        assert svc1 is svc2


class TestAgentServiceIntegration:
    """测试 AgentService 与新模块的集成"""

    def test_build_middleware_stack_general(self):
        from app.services.agent_service import AgentService
        from app.services.agent_profile_service import RuntimeAgentProfile
        from wuwei import LLMGateway
        from app.core.config import get_settings

        service = AgentService(get_settings())
        profile = RuntimeAgentProfile(
            profile_id=None, name="general", slug="general", response_mode="general",
            system_prompt="test", builtin_tools=("calc", "time"),
            approval_tools=(), signature="", skills=(),
        )
        llm = LLMGateway.from_env()
        stack = service._build_middleware_stack(profile, llm)
        mw_names = [type(m).__name__ for m in stack.middlewares]
        assert "ContextCompressionMiddleware" in mw_names
        assert "ThinkingHistoryCompatibilityMiddleware" in mw_names
        assert "LoggingMiddleware" in mw_names
        assert "HitlMiddleware" not in mw_names  # approval_tools 为空

    def test_build_middleware_stack_with_approval(self):
        from app.services.agent_service import AgentService
        from app.services.agent_profile_service import RuntimeAgentProfile
        from wuwei import LLMGateway
        from app.core.config import get_settings

        service = AgentService(get_settings())
        profile = RuntimeAgentProfile(
            profile_id=None, name="ppt", slug="ppt", response_mode="ppt",
            system_prompt="test", builtin_tools=("skill",),
            approval_tools=frozenset({"save_slide"}), signature="", skills=(),
        )
        llm = LLMGateway.from_env()
        stack = service._build_middleware_stack(profile, llm)
        mw_names = [type(m).__name__ for m in stack.middlewares]
        assert "HitlMiddleware" in mw_names

    def test_build_tool_registry_with_mcp(self):
        from app.services.agent_service import AgentService
        from app.services.agent_profile_service import RuntimeAgentProfile

        profile = RuntimeAgentProfile(
            profile_id=None, name="general", slug="general", response_mode="general",
            system_prompt="test", builtin_tools=("calc", "time"),
            approval_tools=(), signature="", skills=(),
        )
        registry = AgentService._build_tool_registry(profile)
        tool_names = [t.name for t in registry.list_tools()]
        assert "calculate" in tool_names
        assert "get_now" in tool_names


class TestContextCompression:
    """测试 ContextCompressionMiddleware 2.2.0"""

    @pytest.mark.anyio
    async def test_compression_preserves_tool_pairs(self):
        from wuwei.middleware.context_compression import ContextCompressionMiddleware
        from wuwei.middleware.base import MiddlewareContext
        from wuwei.graph.state import State
        from wuwei.core.message import HumanMessage, AIMessage, ToolMessage, SystemMessage
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(message=MagicMock(content="summary")))

        state = State(messages=[
            SystemMessage(content="system"),
            HumanMessage(content="hello"),
            AIMessage(content="calling tool", tool_calls=[{"id": "tc1", "type": "function", "function": {"name": "calc", "arguments": {}}}]),
            ToolMessage(content="result", tool_call_id="tc1", name="calc"),
            HumanMessage(content="thanks"),
            AIMessage(content="welcome"),
        ])

        mw = ContextCompressionMiddleware(llm=mock_llm, trigger_tokens=10, keep_recent_turns=2)
        ctx = MiddlewareContext(state=state, config={}, step=0)
        ctx = await mw.before_llm(ctx)

        # 验证 tool_call 配对完整
        messages = ctx.state.messages
        tool_call_msg = None
        tool_response_msg = None
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                tool_call_msg = msg
            if msg.role == "tool" and msg.tool_call_id:
                tool_response_msg = msg

        assert tool_call_msg is not None, "tool_call 消息丢失"
        assert tool_response_msg is not None, "tool_response 消息丢失"
        assert tool_response_msg.tool_call_id == tool_call_msg.tool_calls[0].id
