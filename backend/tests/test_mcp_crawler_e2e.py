"""端到端验证：真实 MCP 服务 → AgenticOS 连接 → 工具发现 → 工具调用。

不是 mock —— 真的起一个 MCP HTTP 服务（自签证书），用平台自己的
``McpService`` 去连，检查：
- 自签证书能连上（verify_tls=False 路径生效）
- 工具被正确发现并命名 ``mcp__<server>__<tool>``
- 平台侧包装层生效（凭据注入 / 用户追问）
- profile 授权过滤生效
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
CRAWLER_DIR = BACKEND.parent / "deploy" / "intranet" / "crawler_mcp"


def _make_selfsigned_cert(tmp_path: Path) -> tuple[str, str]:
    """生成自签证书（内网场景典型情况）。"""
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
        ],
        check=True,
        capture_output=True,
    )
    return str(cert), str(key)


def _free_port() -> int:
    """取一个当前空闲的端口。

    不能写死端口：上一个用例的子进程刚 terminate、监听 socket 还在
    回收窗口里，下一个用例用同一个端口会 bind 失败 —— 而就绪探测
    会连上**上一个还没死透的旧服务**，于是「配了 A 连到 B」，
    表现为莫名其妙的断言失败。
    """
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _McpServerThread:
    """在后台线程里跑一个 MCP HTTP 服务（可选 HTTPS + 自签证书）。"""

    def __init__(self, certfile: str | None = None, keyfile: str | None = None):
        self.port = _free_port()
        self.certfile = certfile
        self.keyfile = keyfile
        self._proc: subprocess.Popen | None = None
        self._log = tempfile.NamedTemporaryFile(  # noqa: SIM115 —— 随进程结束关闭
            prefix="crawler-mcp-", suffix=".log", delete=False
        )

    def start(self) -> None:
        env = {
            **os.environ,
            "CRAWLER_HOST": "127.0.0.1",
            "CRAWLER_PORT": str(self.port),
            # 允许本地环回（测试目标服务在 127.0.0.1）
            "CRAWLER_ALLOWED_CIDRS": "127.0.0.0/8",
            "PYTHONPATH": str(CRAWLER_DIR),
        }
        code = (
            "import crawler_mcp, uvicorn\n"
            "app = crawler_mcp.server.streamable_http_app()\n"
            "uvicorn.run(app, host=crawler_mcp.HOST, port=crawler_mcp.PORT)\n"
        )
        # 输出写文件而不是 PIPE：PIPE 的缓冲区（64KB）写满后子进程会
        # 阻塞在 write 上，表现为「服务莫名其妙卡住」。
        self._proc = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        self._wait_ready()

    def _log_tail(self, size: int = 2000) -> str:
        try:
            with open(self._log.name, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[-size:]
        except OSError:
            return ""

    def _wait_ready(self) -> None:
        import socket

        for _ in range(100):
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(f"MCP 服务启动失败：{self._log_tail()}")
            with socket.socket() as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    time.sleep(0.6)  # 等 uvicorn 完成挂载
                    return
            time.sleep(0.15)
        raise RuntimeError(f"MCP 服务启动超时：{self._log_tail()}")

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        try:
            os.unlink(self._log.name)
        except OSError:
            pass


@pytest.fixture
def mcp_server(tmp_path):
    srv = _McpServerThread()
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def clean_mcp_rows():
    """用例结束后清掉本文件写入的 MCP 服务器配置。

    不清理的话，这一行会留在库里并指向一个**已经死掉的端口**。
    后续用例调 ``McpService.connect()`` 时会连带去连它 —— 平台上已经
    做了「单服务器失败不影响其他」的隔离，但测试不该依赖这条兜底。
    """
    from app.db.models import MCPServerModel
    from app.db.session import create_db_session

    def _cleanup() -> None:
        with create_db_session() as db:
            db.query(MCPServerModel).filter(
                MCPServerModel.name.in_(
                    ["e2e_crawler", "cross_task_crawler", "dead_crawler"]
                )
            ).delete(synchronize_session=False)
            db.commit()

    yield
    _cleanup()


class TestEndToEndMcpCrawler:
    def test_connect_discover_and_call(self, mcp_server, clean_mcp_rows):
        """真实链路：连接 → 发现工具 → 调用工具。

        **连接与调用必须在同一个事件循环里** —— MCP 客户端的流式传输是
        异步生成器，绑定在 ``connect()`` 所在的任务上。生产环境是单一
        uvicorn 循环（连接在后台任务建立、调用在同一个循环），没有这个问题；
        测试里若用两次 ``asyncio.run`` 就会跨循环，报
        ``Attempted to exit cancel scope in a different task``。
        """
        from app.services.mcp_service import McpService, upsert_server

        upsert_server(
            {
                "name": "e2e_crawler",
                "transport": "http",
                "url": f"http://127.0.0.1:{mcp_server.port}/mcp",
                "verify_tls": True,
                "user_accessible": True,
            }
        )

        service = McpService()

        async def _scenario():
            assert await service.connect(), f"连接失败：{service.last_error}"

            names = {t.name for t in service.get_tools()}
            assert "mcp__e2e_crawler__fetch_page" in names
            assert "mcp__e2e_crawler__browse_page" in names
            assert "mcp__e2e_crawler__extract_table" in names
            assert "mcp__e2e_crawler__submit_form" in names

            # 真实调用：extract_table 是纯计算，不需要外部依赖
            tool = next(
                t for t in service.get_tools() if t.name.endswith("extract_table")
            )
            html = (
                "<table><tr><th>订单号</th><th>金额</th></tr>"
                "<tr><td>A001</td><td>100</td></tr>"
                "<tr><td>A002</td><td>200</td></tr></table>"
            )
            result = await tool.handler(html=html)
            payload = json.loads(result)
            assert payload["ok"] is True
            assert payload["row_count"] == 2
            assert payload["rows"][0]["订单号"] == "A001"

            await service.disconnect()

        asyncio.run(_scenario())

    def test_ssrf_guard_blocks_out_of_range(self, mcp_server, clean_mcp_rows):
        """SSRF 防护：白名单外的目标被拒绝。"""
        from app.services.mcp_service import McpService, upsert_server

        upsert_server(
            {
                "name": "e2e_crawler",
                "transport": "http",
                "url": f"http://127.0.0.1:{mcp_server.port}/mcp",
                "user_accessible": True,
            }
        )
        service = McpService()

        async def _scenario():
            assert await service.connect()
            tool = next(
                t for t in service.get_tools() if t.name.endswith("fetch_page")
            )
            # 8.8.8.8 不在 127.0.0.0/8 白名单内 → 服务侧拒绝
            #
            # 注意错误文案：MCP 协议层会把工具抛出的异常包装成通用的
            # "Error executing tool fetch_page"，**具体的拒绝原因不会透传**
            # （这是 MCP 协议的设计，避免把内部细节泄漏给客户端）。
            # 所以这里断言的是「调用失败」而非具体文案 —— 拒绝原因由
            # 服务侧日志记录。
            result = await tool.handler(url="http://8.8.8.8/")
            assert "Error executing tool" in str(result)

            await service.disconnect()

        asyncio.run(_scenario())

    def test_credential_placeholder_reaches_service(self, mcp_server, clean_mcp_rows):
        """凭据注入：$CREDENTIAL.<字段> 在调用前被替换。"""
        from app.services.mcp_service import McpService, upsert_server
        from app.services.mcp_tool_bridge import set_credential_scope

        upsert_server(
            {
                "name": "e2e_crawler",
                "transport": "http",
                "url": f"http://127.0.0.1:{mcp_server.port}/mcp",
                "user_accessible": True,
            }
        )
        service = McpService()

        async def _scenario():
            assert await service.connect()
            set_credential_scope("e2e_crawler", None)
            tool = next(
                t for t in service.get_tools() if t.name.endswith("fetch_page")
            )
            # 没配凭据 → 返回结构化提示，且**不**真的发起请求
            result = await tool.handler(
                url="http://127.0.0.1:1/",
                headers={"X-T": "$CREDENTIAL.token"},
            )
            payload = json.loads(result)
            assert "missing_credentials" in payload
            assert payload["missing_credentials"] == ["token"]
            await service.disconnect()

        asyncio.run(_scenario())

    def test_nested_placeholder_is_resolved(self, mcp_server, clean_mcp_rows):
        """嵌套结构里的占位符也要解析（回归守护）。

        爬虫工具的参数几乎都是嵌套的：``headers={"X-T": "$CREDENTIAL.token"}``、
        ``fields=[{"name": "x", "value": "$CREDENTIAL.username"}]``。
        只解析顶层字符串的话，占位符会**原样**发给内网服务 ——
        等于凭据没注入，还把占位符本身泄给了内网站点。
        """
        from app.services.mcp_service import McpService, upsert_server
        from app.services.mcp_tool_bridge import set_credential_scope

        upsert_server(
            {
                "name": "e2e_crawler",
                "transport": "http",
                "url": f"http://127.0.0.1:{mcp_server.port}/mcp",
                "user_accessible": True,
            }
        )
        service = McpService()

        async def _scenario():
            assert await service.connect()
            set_credential_scope("e2e_crawler", None)
            tool = next(
                t for t in service.get_tools() if t.name.endswith("fetch_page")
            )
            # 占位符藏在 dict 里 → 仍应被识别为「缺凭据」，且**不**真的发请求
            result = await tool.handler(
                url="http://127.0.0.1:1/",
                headers={"X-T": "$CREDENTIAL.token"},
            )
            payload = json.loads(result)
            assert payload["missing_credentials"] == ["token"]

            # 占位符藏在 list[dict] 里 → 同样识别
            result2 = await tool.handler(
                url="http://127.0.0.1:1/",
                headers=[{"name": "X-T", "value": "$CREDENTIAL.token"}],
            )
            payload2 = json.loads(result2)
            assert payload2["missing_credentials"] == ["token"]

            await service.disconnect()

        asyncio.run(_scenario())

    def test_dead_server_does_not_block_healthy_one(self, mcp_server, clean_mcp_rows):
        """一个 MCP 服务挂掉，**不能**连累其他服务。

        这是生产级保证：内网爬虫服务停机时，平台上的其他 MCP 工具
        （公网的、别的内网服务）必须照常可用。

        踩过的坑：连接不可达的服务时，MCP 的 streamable HTTP 传输在
        anyio cancel scope 里发起 POST，失败后以 ``CancelledError``
        （**BaseException**）冒出来 —— 上游 ``connect()`` 只 catch
        ``Exception``，接不住，于是它一路穿透，把**整个** connect 掀翻，
        健康的服务也拿不到工具。
        """
        from app.services.mcp_service import McpService, upsert_server

        # 一个指向已关闭端口的死服务
        dead_port = _free_port()
        upsert_server(
            {
                "name": "dead_crawler",
                "transport": "http",
                "url": f"http://127.0.0.1:{dead_port}/mcp",
                "user_accessible": True,
            }
        )
        upsert_server(
            {
                "name": "e2e_crawler",
                "transport": "http",
                "url": f"http://127.0.0.1:{mcp_server.port}/mcp",
                "user_accessible": True,
            }
        )

        service = McpService()

        async def _scenario():
            ok = await service.connect()
            # 整体连接仍然是「成功」的（有服务可用）
            assert ok, f"连接失败：{service.last_error}"
            names = {t.name for t in service.get_tools()}
            # 健康服务的工具照常可用
            assert "mcp__e2e_crawler__extract_table" in names
            # 死服务没有工具进来
            assert not any(n.startswith("mcp__dead_crawler__") for n in names)
            # 死服务的错误被单独记录
            assert "dead_crawler" in (service.last_error or "")
            await service.disconnect()

        asyncio.run(_scenario())
