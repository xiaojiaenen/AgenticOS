"""验证 MCP 连接跨任务调用的健壮性。

生产环境里，MCP 连接的建立与工具调用的**任务上下文不同**：

- ``McpService.connect()`` —— 在管理后台的「连接并发现工具」请求里执行；
- ``call_tool`` —— 在智能体流式对话的任务里执行。

MCP 2.x 的 ``streamable_http_client`` 内部用 anyio 的 cancel scope，
而 cancel scope **绑定到进入它的那个任务**。若跨任务使用会抛
``Attempted to exit cancel scope in a different task than it was entered in``。

这个测试连**真实的 MCP 服务**验证：连接在任务 A 建立，调用在任务 B 进行。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
CRAWLER_DIR = BACKEND.parent / "deploy" / "intranet" / "crawler_mcp"

PORT = 8932


@pytest.fixture(scope="module")
def live_mcp_server():
    env = {
        **os.environ,
        "CRAWLER_HOST": "127.0.0.1",
        "CRAWLER_PORT": str(PORT),
        "CRAWLER_ALLOWED_CIDRS": "127.0.0.0/8",
        "PYTHONPATH": str(CRAWLER_DIR),
    }
    code = (
        "import crawler_mcp, uvicorn\n"
        "app = crawler_mcp.server.streamable_http_app()\n"
        "uvicorn.run(app, host=crawler_mcp.HOST, port=crawler_mcp.PORT)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        import socket

        for _ in range(100):
            if proc.poll() is not None:
                out, err = proc.communicate()
                raise RuntimeError(
                    f"MCP 服务启动失败：{err.decode(errors='replace')[-2000:]}"
                )
            with socket.socket() as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", PORT)) == 0:
                    time.sleep(0.6)
                    break
            time.sleep(0.15)
        else:
            raise RuntimeError("MCP 服务启动超时")
        yield f"http://127.0.0.1:{PORT}/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_connect_and_call_in_different_tasks(live_mcp_server):
    """连接在任务 A，调用在任务 B —— 生产环境的真实形态。"""
    from app.services.mcp_service import McpService, upsert_server

    upsert_server(
        {
            "name": "cross_task_crawler",
            "transport": "http",
            "url": live_mcp_server,
            "user_accessible": True,
        }
    )

    service = McpService()
    connected: dict = {}

    async def _connect_task():
        """任务 A：建立连接（模拟管理后台的连接请求）。"""
        ok = await service.connect()
        connected["ok"] = ok
        connected["error"] = service.last_error

    async def _call_task():
        """任务 B：调用工具（模拟智能体流式对话）。"""
        tool = next(
            t for t in service.get_tools() if t.name.endswith("extract_table")
        )
        html = "<table><tr><th>列</th></tr><tr><td>值</td></tr></table>"
        result = await tool.handler(html=html)
        return result

    async def _main():
        # 关键：两个任务**不是**同一个
        await asyncio.create_task(_connect_task())
        assert connected["ok"], f"连接失败：{connected['error']}"

        result = await asyncio.create_task(_call_task())
        return result

    result = asyncio.run(_main())

    import json

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["row_count"] == 1
    assert payload["rows"][0]["列"] == "值"
