"""邮件工具的同步网络 IO 必须移出 asyncio 事件循环的回归测试。

每个 async 邮件工具都是 asyncio.to_thread 的薄包装，真正的 IMAP/SMTP 连接、
登录、FETCH/SEARCH/发送在线程池里执行，不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import threading
import types

from app.tools import email_tools
from app.services.agent.native.tool_registry import ToolRegistry


CREDS = {
    "email": "tester@example.com",
    "password": "pw",
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_ssl": True,
    "smtp_host": "smtp.example.com",
    "smtp_port": 465,
    "smtp_ssl": True,
}


def _fake_imap():
    """最小 IMAP 桩：只满足 list_email_folders 的路径。"""
    class _Imap:
        def login(self, *a):
            pass

        def list(self):
            return "OK", [b'(\\HasNoChildren) "/" "INBOX"']

        def logout(self):
            pass

    return _Imap()


def test_email_tools_run_network_io_in_worker_thread(monkeypatch):
    loop_thread = threading.get_ident()
    imap_threads: list[int] = []
    smtp_threads: list[int] = []

    monkeypatch.setattr(email_tools, "_get_credentials", lambda: dict(CREDS))

    def fake_imap_connect(host, port, ssl):
        imap_threads.append(threading.get_ident())
        return _fake_imap()

    def fake_smtp_connect(host, port, ssl):
        smtp_threads.append(threading.get_ident())

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def login(self, *a):
                pass

            def send_message(self, *a):
                pass

        return _Ctx()

    monkeypatch.setattr(email_tools, "_imap_connect", fake_imap_connect)
    monkeypatch.setattr(email_tools, "_smtp_connect", fake_smtp_connect)

    async def main():
        # 通过 registry 拿到真实的异步包装函数（与线上调用链一致）
        registry = ToolRegistry()
        email_tools.register_email_tools(registry)
        result = await registry.get("list_email_folders").handler()
        assert "📁" in result

        # send_notification_email 是模块级公共函数，直接 await
        sent = await email_tools.send_notification_email(CREDS, "to@example.com", "s", "b")
        assert sent is True

    asyncio.run(main())

    assert imap_threads, "list_email_folders 未触发 IMAP 连接"
    assert smtp_threads, "send_notification_email 未触发 SMTP 连接"
    assert all(t != loop_thread for t in imap_threads + smtp_threads), (
        "邮件网络 IO 仍在事件循环线程执行"
    )


def test_all_email_tools_use_to_thread():
    """六个注册工具 + send_notification_email 都是 to_thread 包装。"""
    import inspect

    src = inspect.getsource(email_tools)
    assert src.count("await asyncio.to_thread(") >= 7
