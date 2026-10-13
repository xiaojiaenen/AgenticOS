"""M6-A8：AgenticOS locust 压测脚本。

三档场景，用环境变量 ``LOCUST_SCENARIO`` 选择（smoke / standard / target），
用户数与时长由 README 里的命令给出；三档共用同一份任务权重，便于纵向对比。

**必须用 mock 模式起后端**（``LLM_MOCK_ENABLED=true``），否则会打真实模型、
产生真实费用，且延迟口径完全被模型首 token 时间主导，压不出服务端能力。

任务权重按设计稿 1.3 的业务流配比：聊天为主，登录/建会话/历史/看板为辅。
SSE 用独立的 ``SSEStreamer`` 用户类建模 —— 长连接的资源画像（FD、worker、
持续内存驻留）和普通 API 完全不同，混在同一个用户类里会让 P95 失真。

跑法见同目录 README.md，基线数据见 baseline.md。
"""

from __future__ import annotations

import json
import os
import random
import time

from locust import HttpUser, between, events, task
from locust.exception import StopUser

# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------

API = os.getenv("LOADTEST_API", "/api/v1")

# 压测账号池：压测前用同目录 seed_loadtest_users.py 预生成。
# 让压测用户现场注册会把注册接口本身变成瓶颈，掩盖被测路径。
USER_POOL_SIZE = int(os.getenv("LOADTEST_USER_POOL", "50"))
SSE_USER_POOL_SIZE = int(os.getenv("LOADTEST_SSE_POOL", "100"))

USER_POOL = [
    {
        "email": f"lt{i:04d}@test.local",
        "password": os.getenv("LOADTEST_PASSWORD", "Loadtest123!"),
    }
    for i in range(1, USER_POOL_SIZE + 1)
]

SAMPLE_MESSAGES = [
    "帮我总结一下这份文档的要点",
    "写一封客户跟进邮件草稿",
    "解释一下缓存雪崩是什么，以及怎么应对",
    "列出新员工入职需要准备的材料",
    "把上面的内容整理成一份检查清单",
]


def _first_session_id(sse_text: str) -> str | None:
    """从 SSE 原始文本里抠出 session_id（session 事件带 data: 行）。"""
    for line in sse_text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[5:].strip())
        except (json.JSONDecodeError, TypeError):
            continue
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid:
            return sid
    return None


def _has_done_event(sse_text: str) -> bool:
    """确认流真的收到了 done 事件。

    只看 HTTP 200 会把半截流算成成功 —— SSE 最常见的失败就是连上之后
    中途断掉，两种情况的状态码完全一样。
    事件类型在 ``event:`` 行上（``done`` 事件的 data 里没有 "done" 字样）。
    """
    return any(line.strip() == "event: done" for line in sse_text.splitlines())


class _AuthMixin:
    """登录并持有 token，被所有用户类复用。"""

    def login(self) -> None:
        creds = random.choice(USER_POOL)
        with self.client.post(
            f"{API}/auth/login",
            json=creds,
            name="POST /auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login failed: {resp.status_code} {resp.text[:200]}")
                raise StopUser()
            resp.success()
            self.token = resp.json()["access_token"]

    @property
    def auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


class ChatApiUser(_AuthMixin, HttpUser):
    """普通 API 用户：建会话 + 短消息(SSE) + 拉历史 + 看板查询。"""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.login()
        self.session_id: str | None = None

    @task(3)
    def send_message(self) -> None:
        payload = {
            "message": random.choice(SAMPLE_MESSAGES),
            "response_mode": "general",
            "session_id": self.session_id or "",
        }
        with self.client.post(
            f"{API}/agent/stream",
            json=payload,
            headers=self.auth,
            name="POST /agent/stream (SSE)",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"stream failed: {resp.status_code} {resp.text[:200]}")
                return
            if not _has_done_event(resp.text):
                resp.failure("stream ended without done event")
                return
            resp.success()
            if self.session_id is None:
                self.session_id = _first_session_id(resp.text)

    @task(2)
    def new_session(self) -> None:
        """开新会话。

        注意：后端**没有** POST /agent/sessions —— 会话是在第一次
        /agent/stream 时由服务端创建的（session_id 传空串）。所以
        "建会话" 在协议层就是发一条不带 session_id 的流消息。
        这里用一条最短的流消息来产生新会话，而不是调一个不存在的端点。
        """
        with self.client.post(
            f"{API}/agent/stream",
            json={"message": "新会话", "response_mode": "general", "session_id": ""},
            headers=self.auth,
            name="POST /agent/stream (new session)",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200 or not _has_done_event(resp.text):
                resp.failure(f"new session failed: {resp.status_code}")
                return
            resp.success()
            self.session_id = _first_session_id(resp.text)

    @task(2)
    def list_sessions(self) -> None:
        self.client.get(
            f"{API}/agent/sessions",
            headers=self.auth,
            name="GET /agent/sessions",
        )

    @task(1)
    def dashboard_stats(self) -> None:
        self.client.get(
            f"{API}/dashboard/stats",
            headers=self.auth,
            name="GET /dashboard/stats",
        )

    @task(1)
    def dashboard_analytics(self) -> None:
        self.client.get(
            f"{API}/dashboard/analytics",
            headers=self.auth,
            name="GET /dashboard/analytics",
        )


class SSEStreamer(_AuthMixin, HttpUser):
    """独立 SSE 长连接用户（target 档的 100 条常驻流）。

    与 ChatApiUser 的差别：不轮询其他接口，只反复建长连接把整条流读完，
    模拟真实长会话。这样 SSE 的连接成本不会被其他请求的排队掩盖。
    """

    wait_time = between(2, 5)

    def on_start(self) -> None:
        self.login()

    @task
    def hold_stream(self) -> None:
        payload = {
            "message": random.choice(SAMPLE_MESSAGES),
            "response_mode": "general",
        }
        started = time.monotonic()
        with self.client.post(
            f"{API}/agent/stream",
            json=payload,
            headers=self.auth,
            name="POST /agent/stream (SSE dedicated)",
            catch_response=True,
        ) as resp:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if resp.status_code != 200:
                resp.failure(f"sse failed: {resp.status_code}")
                return
            if not _has_done_event(resp.text):
                resp.failure(f"sse truncated after {elapsed_ms}ms")
                return
            resp.success()


@events.test_start.add_listener
def _on_test_start(environment, **_kwargs) -> None:
    scenario = os.getenv("LOCUST_SCENARIO", "smoke")
    print(f"\n[loadtest] scenario={scenario}  host={environment.host}")
    print(f"[loadtest] API 用户池={USER_POOL_SIZE}  SSE 池={SSE_USER_POOL_SIZE}")
    print("[loadtest] 请确认后端已开 LLM_MOCK_ENABLED=true（否则会打真实模型）\n")