"""MCP 工具集成服务

使用 wuwei 2.2.0 的 MCP 支持接入外部工具。
支持 stdio 和 HTTP 两种 MCP 服务器连接方式。
"""

import logging
from typing import Any

from wuwei.mcp import MCPConfig, MCPSessionManager, MCPToolAdapter

_logger = logging.getLogger("mcp_service")


class McpService:
    """MCP 工具集成服务"""

    def __init__(self):
        self._session_manager: MCPSessionManager | None = None
        self._tools: list = []

    async def connect(self, config_path: str | None = None) -> bool:
        """连接 MCP 服务器

        Args:
            config_path: MCP 配置文件路径，None 则使用默认配置
        """
        try:
            if config_path:
                config = MCPConfig.load(config_path)
            else:
                # 使用默认配置
                config = MCPConfig(servers=[])

            self._session_manager = MCPSessionManager(config)
            await self._session_manager.connect_all()

            # 获取所有工具
            self._tools = self._session_manager.get_all_tools()
            _logger.info(f"Connected to MCP servers, found {len(self._tools)} tools")
            return True
        except Exception as e:
            _logger.error(f"MCP connection failed: {e}")
            return False

    def get_tools(self) -> list:
        """获取 MCP 工具列表"""
        return self._tools

    async def disconnect(self):
        """断开 MCP 连接"""
        if self._session_manager:
            await self._session_manager.disconnect_all()
            self._session_manager = None
            self._tools = []


# 全局实例
_mcp_service: McpService | None = None


def get_mcp_service() -> McpService:
    """获取 MCP 服务单例"""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = McpService()
    return _mcp_service
