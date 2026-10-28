"""MCP 服务器管理服务。

管理员在后台维护 MCP 服务器（stdio / http / sse），服务负责：

1. 把数据库配置翻译成 wuwei 的 :class:`MCPConfig`
2. 建立/刷新连接并发现工具
3. 把发现的工具以 ``mcp__<server>__<tool>`` 命名暴露给 Agent 的工具目录

连接失败只记录错误、不影响其他服务器；工具发现结果带缓存，
避免每轮对话都重连。

## 内网爬虫类服务的适配（2026-10-28）

内网爬虫以「独立 MCP 服务」形态接入后，有三处官方 SDK 能力不够用，
在**平台侧**补齐（不改 site-packages）：

- **自签证书**：官方 ``create_mcp_http_client()`` 只有 headers/timeout/auth，
  没有 verify 参数；内网服务普遍自签 CA，握手会直接失败。
  → 见 ``_build_http_client``，自建 httpx2 客户端传给 streamable_http 传输。
- **出网网段限制**：平台连 MCP 服务这一跳的地址可限制在管理员配置的网段内。
- **profile 级授权 + 凭据注入 + 用户追问**：见 ``mcp_tool_bridge``。
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
from app.services.mcp_tool_bridge import set_credential_scope, wrap_mcp_tool

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


class _VerifiableHTTPMCPClient:
    """支持自签证书的 MCP HTTP 客户端。

    上游 ``wuwei.mcp.HTTPMCPClient`` 的 ``_open_streams`` 里直接调用官方
    ``create_mcp_http_client(headers, timeout)`` 建客户端 —— **没有 verify
    参数**，内网自签 CA 会在 TLS 握手阶段直接失败，且上游没留替换点。

    这里**继承**它，只覆写「怎么建客户端」这一个最小单元：

    - ``verify_tls=False`` → 放行自签证书（内网爬虫服务常见）；
    - ``verify_tls=True`` → 仍走官方工厂，保持公网 MCP 的默认安全行为。

    其余握手 / list_tools / call_tool 逻辑全部继承上游，上游升级时不会
    静默落后。

    注意：必须走**继承**而非持有实例 —— 上游 ``connect()`` 内部调用的是
    ``self._open_streams()``，用组合 + ``__getattr__`` 转发的话，覆写不会
    生效（会静默退回官方工厂，表现为「配了自签证书但仍然握手失败」）。
    """

    def __init__(self, config: Any, *, verify_tls: bool = False) -> None:
        from wuwei.mcp import HTTPMCPClient

        # 动态创建子类：基类在运行时才可导入，且要按 verify_tls 决定行为
        base = HTTPMCPClient
        verify = verify_tls

        class _Client(base):  # type: ignore[misc, valid-type]
            def _open_streams(self):
                from contextlib import asynccontextmanager

                from mcp.client.streamable_http import (
                    httpx2 as sdk_httpx2,
                    streamable_http_client,
                )
                import httpx2

                timeout = sdk_httpx2.Timeout(self.config.timeout)
                kwargs: dict[str, Any] = {
                    "timeout": timeout,
                    "verify": verify,
                }
                headers = dict(self.config.headers or {})
                if headers:
                    kwargs["headers"] = headers

                @asynccontextmanager
                async def _streams():
                    client = httpx2.AsyncClient(**kwargs)
                    async with client, streamable_http_client(
                        self.config.url, http_client=client
                    ) as streams:
                        yield streams[0], streams[1]

                return _streams()

        self._client = _Client(config)
        self._verify_tls = verify_tls

    # ── 委托上游 ──
    async def connect(self) -> None:
        await self._client.connect()

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def list_tools(self) -> list[dict]:
        return await self._client.list_tools()

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._client.call_tool(name, arguments)

    def __getattr__(self, item: str) -> Any:
        # 其余属性（session 等）转发给上游实例
        return getattr(self._client, item)


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

    # ── 内网连接：自签证书 + 出网网段校验 ──────────────────────
    @staticmethod
    def _build_http_client(config: Any, row: MCPServerModel):
        """自建 httpx2 客户端，支持自签证书。

        官方 ``create_mcp_http_client()`` 只有 headers/timeout/auth 三个参数，
        **没有 verify** —— 内网服务普遍自签 CA，走官方工厂会在握手阶段
        直接失败，而上游没有留替换点。

        这里自建客户端并交给 ``streamable_http_client(http_client=...)``，
        不改 site-packages。
        """
        import httpx2

        from mcp.client.streamable_http import httpx2 as sdk_httpx2

        timeout = sdk_httpx2.Timeout(config.timeout)
        verify = bool(row.verify_tls)
        kwargs: dict[str, Any] = {
            "timeout": timeout,
            "verify": verify,
        }
        headers = dict(config.headers or {})
        if headers:
            kwargs["headers"] = headers
        return httpx2.AsyncClient(**kwargs)

    @staticmethod
    def _check_server_url(url: str | None, row: MCPServerModel) -> None:
        """校验平台连 MCP 服务这一跳的地址。

        只有管理员显式配置了 ``allowed_cidrs`` 才限制 —— 默认不限制，
        避免破坏既有的公网 MCP 用法。
        """
        cidrs = (row.allowed_cidrs or "").strip()
        if not cidrs or not url:
            return
        from app.services.intranet_policy import check_url

        decision = check_url(url, allowed_cidrs=cidrs, egress_allowlist="")
        if not decision.allowed:
            raise PermissionError(f"MCP 服务器地址不在允许网段内：{decision.reason}")

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
            await self._connect_servers(config)
            # 注意：错误要在**连接之后**再取 —— 之前的写法在连接前就把
            # ``_server_errors`` 快照走，导致 last_error 反映的是上一次
            # 连接的状态（本次失败/本次成功都被吃掉）。
            server_errors = dict(self._server_errors)
            if server_errors:
                self._last_error = "; ".join(f"{k}: {v}" for k, v in server_errors.items())
            elif not self._tools and config.mcp_servers:
                self._last_error = "已连接但未发现可用工具"
            else:
                self._last_error = None
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

        **「不影响其他」必须真的成立**：连接一个不可达的 MCP 服务时，
        SDK 的 streamable HTTP 传输在 anyio cancel scope 里发起 POST，
        失败后以 ``CancelledError``（**BaseException**）的形式冒出来 ——
        上游 ``connect()`` 只 catch ``Exception``，接不住它，于是它会
        一路穿透到我们这里，把**整个** ``connect()`` 掀翻：本来健康的
        MCP 服务也拿不到工具。

        平台侧的对策：每个服务器在**独立 task** 里连接。
        子任务里的 ``CancelledError`` 不会污染父任务的 ``cancelling()``，
        于是既能把它识别成「这个服务器连不上」，又不会误吞外层的真取消。
        """
        from wuwei.mcp import HTTPMCPClient, StdioMCPClient

        # 服务器配置行（用于自签证书 / 网段 / 凭据来源）
        rows_by_name: dict[str, MCPServerModel] = {}

        def _load_rows() -> dict[str, MCPServerModel]:
            with create_db_session() as db:
                return {
                    r.name: r
                    for r in db.scalars(select(MCPServerModel)).all()
                }

        rows_by_name = await asyncio.to_thread(_load_rows)

        self._clients = {}
        self._server_errors = {}
        self._tools = []
        for name, server_cfg in config.mcp_servers.items():
            row = rows_by_name.get(name)
            # 每个服务器在独立 task 里连接 —— 这样「子任务被传输层取消」
            # 与「外层真的被取消」可以区分开（见上面的说明）。
            task = asyncio.create_task(
                self._connect_one(
                    name, server_cfg, row, HTTPMCPClient, StdioMCPClient
                )
            )
            try:
                client, tools, error = await task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling() > 0:
                    # 外层任务确实被取消 → 继续往上抛，不吞
                    raise
                # 子任务被 MCP 传输层的 anyio cancel scope 取消
                # （典型的「服务地址不可达」）→ 记为该服务器失败
                client, tools, error = None, [], "连接被传输层取消（服务不可达？）"
            except BaseException as exc:  # noqa: BLE001
                client, tools, error = None, [], str(exc) or exc.__class__.__name__

            if error is not None:
                logger.warning("MCP 服务器 %s 连接失败: %s", name, error)
                self._server_errors[name] = error
                await self._mark_server_error(name, error)
                continue
            assert client is not None  # noqa: S101 —— error 为 None 时必有 client
            self._clients[name] = client
            # ── 登记凭据来源（$CREDENTIAL.<字段> 从哪取）──
            set_credential_scope(
                name, row.external_system_id if row is not None else None
            )
            self._tools.extend(tools)
            logger.info("MCP server %s: %d tools", name, len(tools))
            await self._mark_server_error(name, None)

    async def _connect_one(
        self,
        name: str,
        server_cfg: Any,
        row: MCPServerModel | None,
        http_cls: Any,
        stdio_cls: Any,
    ) -> tuple[Any | None, list, str | None]:
        """连接单个 MCP 服务器。返回 ``(client, tools, error)``。

        失败时返回 ``error`` 字符串（而不是抛异常），保证「一个挂掉不影响
        其他」。同时负责把半开的连接清理掉 —— 上游在 ``CancelledError``
        路径上不会关 ``_stack``，会漏传输层。

        注意这里只 catch ``Exception``：``CancelledError`` 是 BaseException，
        必须让它冒到调用方，由调用方判断是「传输层取消」还是「外层取消」。
        """
        client: Any | None = None
        ok = False
        try:
            from wuwei.mcp import MCPToolAdapter

            if server_cfg.transport == "stdio":
                client = stdio_cls(server_cfg)
            else:
                # ── 内网适配：自签证书 + 出网网段校验 ──
                if row is not None:
                    self._check_server_url(server_cfg.url, row)
                client = http_cls(server_cfg)
                if row is not None and not row.verify_tls:
                    # 官方客户端走默认 verify=True，自签证书握手必失败。
                    # 这里替换成平台自建客户端（不改 site-packages）。
                    client = _VerifiableHTTPMCPClient(
                        server_cfg, verify_tls=False
                    )
            await client.connect()
            adapter = MCPToolAdapter(client, name)
            tools = await adapter.discover_tools()
            # ── 平台侧包装：凭据注入 + 用户追问 ──
            ok = True
            return client, [wrap_mcp_tool(t) for t in tools], None
        except Exception as exc:  # noqa: BLE001
            return None, [], str(exc) or exc.__class__.__name__
        finally:
            if client is not None and not ok:
                # 半开的连接必须关掉，否则传输层泄漏
                try:
                    await client.disconnect()
                except (Exception, asyncio.CancelledError):
                    logger.debug(
                        "MCP 失败连接的清理异常 server=%s", name, exc_info=True
                    )

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

    def get_tools_for_profile(self, profile_id: int | None) -> list:
        """按 profile 过滤 MCP 工具 —— dsh 说的「按需挂载」。

        此前 MCP 工具是**全局注册**到每一个 Agent 的（factory.py 里无条件
        register），任何智能体都能调用任意 MCP 服务器的工具。内网爬虫类
        服务能访问内网站点，这种全局可见不可接受。

        规则：

        - ``user_accessible=False`` 的服务器**只有**在 profile 显式授权后
          才可用（内网爬虫的默认形态）。
        - ``user_accessible=True`` 的服务器对所有 profile 可见（保持既有
          公网 MCP 的行为不变）。
        """
        if profile_id is None:
            return list(self._tools)

        allowed = self._authorized_servers(profile_id)
        if not allowed:
            return []
        return [t for t in self._tools if self._server_of_tool(t.name) in allowed]

    @staticmethod
    def _server_of_tool(tool_name: str) -> str:
        """从 ``mcp__<server>__<tool>`` 反解服务器名。

        服务器名按惯例不含 ``__``；工具名可以含 —— 所以从**左侧**切第一个
        分隔符，而不是从右侧切最后一个。
        """
        parts = tool_name.split("__", 2)
        if len(parts) < 3 or parts[0] != "mcp":
            return ""
        return parts[1]

    def _authorized_servers(self, profile_id: int) -> set[str]:
        """该 profile 可用的 MCP 服务器名集合。"""
        from app.db.models import AgentProfileMCPServerModel

        def _load() -> tuple[set[str], set[str]]:
            with create_db_session() as db:
                granted = set(
                    db.scalars(
                        select(AgentProfileMCPServerModel.server_name).where(
                            AgentProfileMCPServerModel.profile_id == profile_id,
                            AgentProfileMCPServerModel.enabled.is_(True),
                        )
                    ).all()
                )
                open_access = set(
                    db.scalars(
                        select(MCPServerModel.name).where(
                            MCPServerModel.enabled.is_(True),
                            MCPServerModel.user_accessible.is_(True),
                        )
                    ).all()
                )
                return granted, open_access

        try:
            granted, open_access = _load()
        except Exception:  # noqa: BLE001 —— 取不到就按「全部需授权」处理
            logger.debug("读取 MCP 授权失败 profile=%s", profile_id, exc_info=True)
            return set()
        return granted | open_access

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
        """关闭所有 MCP 连接。

        注意：``_session_manager`` 从未被本服务赋值（我们走自己的
        ``_connect_servers``），所以**必须**显式关闭 ``_clients`` 里的每个
        连接 —— 否则「连接并发现工具」每次重连都会泄漏一批旧连接
        （旧连接还占着 socket 与 anyio task group）。
        """
        if self._session_manager:
            try:
                await self._session_manager.disconnect_all()
            except Exception:  # noqa: BLE001
                logger.debug("MCP 断开失败", exc_info=True)
            self._session_manager = None

        clients = list(self._clients.values())
        self._clients = {}
        for client in clients:
            try:
                await client.disconnect()
            except (Exception, asyncio.CancelledError):
                # 单个连接断开失败不影响其他；CancelledError 也要接住
                # —— 否则一个坏连接会让后面的连接都不关（泄漏）。
                logger.debug("MCP 客户端断开失败", exc_info=True)

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
        "verify_tls": bool(row.verify_tls),
        "allowed_cidrs": row.allowed_cidrs or "",
        "user_accessible": bool(row.user_accessible),
        "external_system_id": row.external_system_id,
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
        # ── 内网接入选项 ──
        # verify_tls 缺失时保持原值（不传 = 不变），避免前端没带这个字段
        # 就把「已放行自签证书」重置回校验。
        if "verify_tls" in payload and payload["verify_tls"] is not None:
            row.verify_tls = bool(payload["verify_tls"])
        if "allowed_cidrs" in payload and payload["allowed_cidrs"] is not None:
            row.allowed_cidrs = str(payload["allowed_cidrs"])
        if "user_accessible" in payload and payload["user_accessible"] is not None:
            row.user_accessible = bool(payload["user_accessible"])
        if "external_system_id" in payload:
            ext_id = payload["external_system_id"]
            row.external_system_id = int(ext_id) if ext_id else None
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


# ── profile 级授权（按需挂载）──────────────────────────────────────────


def list_profile_servers(profile_id: int) -> list[dict[str, Any]]:
    """该 profile 显式授权的 MCP 服务器。"""
    from app.db.models import AgentProfileMCPServerModel

    with create_db_session() as db:
        rows = db.scalars(
            select(AgentProfileMCPServerModel).where(
                AgentProfileMCPServerModel.profile_id == profile_id
            )
        ).all()
        return [
            {"server_name": r.server_name, "enabled": bool(r.enabled)} for r in rows
        ]


def apply_profile_servers(profile_id: int, refs: list[dict[str, Any]]) -> None:
    """覆盖式设置 profile 的 MCP 服务器授权。

    整体替换而非增量 —— 与 ``apply_profile_systems`` 的语义一致，
    前端提交什么就是什么，不留陈旧授权。
    """
    from app.db.models import AgentProfileMCPServerModel

    with create_db_session() as db:
        db.query(AgentProfileMCPServerModel).filter(
            AgentProfileMCPServerModel.profile_id == profile_id
        ).delete()
        for ref in refs:
            name = (ref.get("server_name") or "").strip()
            if not name:
                continue
            db.add(
                AgentProfileMCPServerModel(
                    profile_id=profile_id,
                    server_name=name,
                    enabled=bool(ref.get("enabled", True)),
                )
            )
        db.commit()
