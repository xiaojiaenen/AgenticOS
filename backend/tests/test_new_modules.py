"""测试 wuwei 2.2.0 重构新增模块"""


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

