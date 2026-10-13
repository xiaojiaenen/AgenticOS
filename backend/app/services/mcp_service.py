"""MCP 服务器管理服务。

管理员在后台维护 MCP 服务器（stdio / http / sse），服务负责：

1. 把数据库配置翻译成 wuwei 的 :class:`MCPConfig`
2. 建立/刷新连接并发现工具
3. 把发现的工具以 ``mcp__<server>__<tool>`` 命名暴露给 Agent 的工具目录

连接失败只记录错误、不影响其他服务器；工具发现结果带缓存，
避免每轮对话都重连。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select

from app.core.timezone import app_now
from app.db.models import MCPServerModel
from app.db.session import create_db_session

logger = logging.getLogger("mcp_service")


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class McpService:
    """MCP 工具集成服务"""

    def __init__(self) -> None:
        self._session_manager: Any | None = None
        self._clients: dict[str, Any] = {}
        self._server_errors: dict[str, str] = {}
        self._tools: list = []
        self._last_error: str | None = None

    # ── 配置装配 ──────────────────────────────────────────────
    @staticmethod
    def _to_wuwei_config(db) -> Any:
        from wuwei.mcp import MCPConfig, MCPServerConfig

        config = MCPConfig(mcp_servers={})
        rows = db.scalars(
            select(MCPServerModel).where(MCPServerModel.enabled.is_(True))
        ).all()
        for row in rows:
            config.add_server(
                MCPServerConfig(
                    name=row.name,
                    transport=row.transport or "http",
                    url=row.url,
                    command=row.command,
                    args=_loads(row.args_json, []),
                    env=_loads(row.env_json, {}),
                    headers=_loads(row.headers_json, {}),
                    timeout=float(row.timeout or 60.0),
                    enabled=True,
                )
            )
        return config

    # ── 连接与发现 ────────────────────────────────────────────
    async def connect(self, config_path: str | None = None) -> bool:
        """连接所有启用的 MCP 服务器并发现工具。"""

        try:
            if config_path:
                from wuwei.mcp import MCPConfig

                config = MCPConfig.load(config_path)
            else:
                def _build():
                    with create_db_session() as db:
                        return self._to_wuwei_config(db)

                config = await asyncio.to_thread(_build)

            if not getattr(config, "mcp_servers", None):
                logger.info("MCP: 没有启用的服务器，跳过连接")
                self._session_manager = None
                self._tools = []
                self._last_error = None
                await self._mark_connected(None)
                return True

            await self.disconnect()
            # 逐服务器连接过程中已按服务器记录过错误；仅在都没有错误时
            # 才用"未发现工具"兜底，避免掩盖真实连接失败原因
            server_errors = {**self._server_errors}
            await self._connect_servers(config)
            if server_errors:
                self._last_error = "; ".join(f"{k}: {v}" for k, v in server_errors.items())
            elif not self._tools and config.mcp_servers:
                self._last_error = "已连接但未发现可用工具"
            logger.info(
                "MCP connected: %d servers, %d tools",
                len(config.mcp_servers), len(self._tools),
            )
            await self._mark_connected(None)
            return True
        except Exception as exc:  # noqa: BLE001 —— 单个服务器失败不应影响整体
            logger.exception("MCP 连接失败")
            self._last_error = str(exc)
            await self._mark_connected(str(exc))
            return False


    async def _connect_servers(self, config) -> None:
        """逐个连接 MCP 服务器并发现工具。

        为什么不直接用 ``MCPSessionManager.connect_all()``：该方法在 wuwei
        中按 ``for name, cfg in config.get_enabled_servers()`` 解包，而
        ``get_enabled_servers()`` 返回的是 list，会抛
        ``too many values to unpack``。这里自行遍历，顺带把「单个服务器
        失败不影响其他服务器」落实到位。
        """
        from wuwei.mcp import HTTPMCPClient, MCPToolAdapter, StdioMCPClient

        self._clients = {}
        self._server_errors = {}
        self._tools = []
        for name, server_cfg in config.mcp_servers.items():
            try:
                client = (
                    StdioMCPClient(server_cfg)
                    if server_cfg.transport == "stdio"
                    else HTTPMCPClient(server_cfg)
                )
                await client.connect()
                self._clients[name] = client
                adapter = MCPToolAdapter(client, name)
                tools = await adapter.discover_tools()
                self._tools.extend(tools)
                logger.info("MCP server %s: %d tools", name, len(tools))
                await self._mark_server_error(name, None)
            except Exception as exc:  # noqa: BLE001 —— 单服务器失败不影响其他
                logger.warning("MCP 服务器 %s 连接失败: %s", name, exc)
                self._server_errors[name] = str(exc)
                await self._mark_server_error(name, str(exc))

    async def _mark_server_error(self, name: str, error: str | None) -> None:
        def _update() -> None:
            with create_db_session() as db:
                row = db.scalar(select(MCPServerModel).where(MCPServerModel.name == name))
                if row is not None:
                    row.last_error = error
                    row.last_connected_at = app_now()
                    db.commit()

        try:
            await asyncio.to_thread(_update)
        except Exception:  # noqa: BLE001
            logger.debug("记录 MCP 服务器状态失败", exc_info=True)

    async def _mark_connected(self, error: str | None) -> None:
        def _update() -> None:
            with create_db_session() as db:
                for row in db.scalars(select(MCPServerModel)).all():
                    row.last_error = error
                    row.last_connected_at = app_now()
                db.commit()

        try:
            await asyncio.to_thread(_update)
        except Exception:  # noqa: BLE001
            logger.debug("记录 MCP 连接状态失败", exc_info=True)

    def get_tools(self) -> list:
        return list(self._tools)

    def tool_catalogue(self) -> list[dict[str, Any]]:
        """把发现的工具转成工具目录条目（供编辑器/工具配置展示）。

        命名遵循 MCP 惯例：``mcp__<server>__<tool>``。
        """
        entries: list[dict[str, Any]] = []
        for tool in self._tools:
            name = getattr(tool, "name", None) or str(tool)
            description = (getattr(tool, "description", "") or "").strip()
            entries.append({
                "name": f"mcp__{name}",
                "label": f"MCP · {name}",
                "description": description or f"来自 MCP 服务器的工具：{name}",
                "approval_scope": [],
                "sub_tools": {},
                "builtin_name": None,
                "source": "mcp",
            })
        return entries

    async def disconnect(self) -> None:
        if self._session_manager:
            try:
                await self._session_manager.disconnect_all()
            except Exception:  # noqa: BLE001
                logger.debug("MCP 断开失败", exc_info=True)
            self._session_manager = None
        self._tools = []

    @property
    def last_error(self) -> str | None:
        return self._last_error


# 全局实例
_mcp_service: McpService | None = None


def get_mcp_service() -> McpService:
    """获取 MCP 服务单例"""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = McpService()
    return _mcp_service


def _serialize_server(row: MCPServerModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "transport": row.transport,
        "url": row.url,
        "command": row.command,
        "args": _loads(row.args_json, []),
        "env": _loads(row.env_json, {}),
        "headers": _loads(row.headers_json, {}),
        "timeout": row.timeout,
        "enabled": row.enabled,
        "last_error": row.last_error,
        "last_connected_at": (
            row.last_connected_at.isoformat() if row.last_connected_at else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_servers() -> list[dict[str, Any]]:
    with create_db_session() as db:
        rows = db.scalars(select(MCPServerModel).order_by(MCPServerModel.name)).all()
        return [_serialize_server(row) for row in rows]


def upsert_server(payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("MCP 服务器名称不能为空")
    transport = payload.get("transport") or "http"
    if transport not in {"stdio", "http", "sse"}:
        raise ValueError(f"不支持的传输方式: {transport}")
    if transport == "stdio":
        if not (payload.get("command") or "").strip():
            raise ValueError("stdio 方式必须填写启动命令")
    elif not (payload.get("url") or "").strip():
        raise ValueError("http/sse 方式必须填写服务地址")

    with create_db_session() as db:
        row = db.scalar(select(MCPServerModel).where(MCPServerModel.name == name))
        if row is None:
            row = MCPServerModel(name=name)
            db.add(row)
        row.description = payload.get("description") or ""
        row.transport = transport
        row.url = (payload.get("url") or "").strip() or None
        row.command = (payload.get("command") or "").strip() or None
        row.args_json = _dumps(payload.get("args") or [])
        row.env_json = _dumps(payload.get("env") or {})
        row.headers_json = _dumps(payload.get("headers") or {})
        row.timeout = float(payload.get("timeout") or 60.0)
        row.enabled = bool(payload.get("enabled", True))
        db.commit()
        db.refresh(row)
        return _serialize_server(row)


def delete_server(name: str) -> None:
    with create_db_session() as db:
        row = db.scalar(select(MCPServerModel).where(MCPServerModel.name == name))
        if row is None:
            raise KeyError(name)
        db.delete(row)
        db.commit()


def get_server(name: str) -> dict[str, Any] | None:
    with create_db_session() as db:
        row = db.scalar(select(MCPServerModel).where(MCPServerModel.name == name))
        return _serialize_server(row) if row else None