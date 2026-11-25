"""验证码服务测试（verification_service.py）。

覆盖：码格式与长度 / 发送频率限制（每分钟 1 次）/ 未配置系统邮箱拒绝 /
正确验证成功并消费（一次性）/ 错误码累计尝试次数 / 超过 5 次验证码立即失效 /
verify_code_sync 三种运行上下文（主循环复用 / 无循环 asyncio.run / 独立线程）。

SMTP 真实发送按集成边界 mock 掉（executor 路径断言参数正确）。"""

from __future__ import annotations

import asyncio
import pytest

from app.services import verification_service as vs
from app.services.cache_service import get_cache_service


@pytest.fixture()
def redis_env():
    """fakeredis fallback（空 URL）+ 独立事件循环。

    被测服务通过 _main_event_loop 复用这个 loop（capture_loop fixture）。"""
    from app.core.redis import init_redis

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_redis(""))
    vs._main_event_loop = loop
    yield loop
    vs._main_event_loop = None
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def smtp_configured(monkeypatch):
    """配置系统邮箱（发码前置条件）+ mock 真实 SMTP 发送。"""
    from app.core.config import get_settings
    monkeypatch.setattr(
        type(get_settings()), "notify_email_address",
        property(lambda self: "noreply@agenticos.dev"), raising=False,
    )
    monkeypatch.setattr(
        type(get_settings()), "notify_smtp_host",
        property(lambda self: "smtp.local"), raising=False,
    )
    sent: list[dict] = []

    def _fake_sync_send(creds, to, subject, html_body):
        sent.append({"to": to, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr(vs, "_send_code_email_sync", _fake_sync_send)
    return sent





def _run(coro):
    """在 fixture 建立的独立 loop 上执行协程（与被测服务共享 Redis 客户端）。"""
    loop = vs._main_event_loop
    assert loop is not None and not loop.is_closed()
    return loop.run_until_complete(coro)


def _stored_code(email: str, purpose: str = "login") -> str | None:
    return _run(get_cache_service().get_verify_code(email, purpose))


def _clear_rate_key(email: str, purpose: str = "login"):
    """清发送频率 key（测试里模拟 60s 窗口滑过）。"""
    from app.core.redis import get_redis

    return get_redis().delete(f"agenticos:verify:rate:{purpose}:{email}")


# ── 发送 ─────────────────────────────────────────────────────────────────


def test_send_generates_six_digit_code_and_mails(redis_env, smtp_configured):
    result = _run(vs.send_verification_code("user@test.local", "login"))
    assert result == {"success": True}
    stored = _stored_code("user@test.local", "login")
    assert stored and len(stored) == 6 and stored.isdigit()
    assert len(smtp_configured) == 1
    assert smtp_configured[0]["to"] == "user@test.local"
    assert "登录" in smtp_configured[0]["subject"]
    assert stored in smtp_configured[0]["html"]  # 验证码出现在邮件正文


def test_send_rate_limited_within_one_minute(redis_env, smtp_configured):
    email = "ratelimit@test.local"
    assert _run(vs.send_verification_code(email, "login")) == {"success": True}
    # 60s 内第二次 → 频率限制
    second = _run(vs.send_verification_code(email, "login"))
    assert second == {"error": "发送太频繁，请稍后再试"}
    assert len(smtp_configured) == 1  # 没有真的发第二封


def test_send_refused_when_system_email_unconfigured(redis_env, smtp_configured, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(
        type(get_settings()), "notify_smtp_host",
        property(lambda self: ""), raising=False,
    )
    result = _run(vs.send_verification_code("nobody@test.local", "register"))
    assert result == {"error": "系统邮箱未配置，无法发送验证码"}
    assert smtp_configured == []


def test_purpose_namespace_isolates_codes(redis_env, smtp_configured):
    """login 与 register 的码互相独立（同邮箱双用途不串）。"""
    email = "purpose@test.local"
    assert _run(vs.send_verification_code(email, "login")) == {"success": True}
    # register 用途无频率限制冲突（不同 purpose 的 rate key 独立）
    assert _run(vs.send_verification_code(email, "register")) == {"success": True}
    login_code = _stored_code(email, "login")
    register_code = _stored_code(email, "register")
    assert login_code != register_code


# ── 验证 ─────────────────────────────────────────────────────────────────


def test_verify_correct_code_consumes_it(redis_env, smtp_configured):
    email = "verify@test.local"
    _run(vs.send_verification_code(email, "login"))
    code = _stored_code(email, "login")

    assert _run(vs.verify_code(email, code, "login")) is True
    # 一次性：验证成功后码被删除，同一码第二次验证失败
    assert _run(vs.verify_code(email, code, "login")) is False


def test_verify_wrong_code_counts_attempts_and_invalidates_after_5(redis_env, smtp_configured):
    email = "attempts@test.local"
    _run(vs.send_verification_code(email, "login"))
    code = _stored_code(email, "login")

    # 前 4 次错码：False，但码仍有效
    for i in range(4):
        assert _run(vs.verify_code(email, "000000", "login")) is False
    assert _stored_code(email, "login") == code

    # 第 5 次（达到 MAX_VERIFY_ATTEMPTS）→ 码立即失效
    assert _run(vs.verify_code(email, "000000", "login")) is False
    assert _stored_code(email, "login") is None

    # 即使随后输入正确码也失败（已失效）
    assert _run(vs.verify_code(email, code, "login")) is False


def test_verify_nonexistent_code_is_false(redis_env):
    assert _run(vs.verify_code("ghost@test.local", "123456", "login")) is False


def test_new_send_resets_attempt_counter(redis_env, smtp_configured):
    """重发新码会清零尝试次数（防「3 次错码后重发仍被旧计数卡死」）。"""
    email = "reset@test.local"
    _run(vs.send_verification_code(email, "login"))
    # 错 2 次
    _run(vs.verify_code(email, "000000", "login"))
    _run(vs.verify_code(email, "000000", "login"))
    # 重发（清零计数）—— 但 60s 频率限制会拦截，先清 rate key
    _run(_clear_rate_key(email))
    assert _run(vs.send_verification_code(email, "login")) == {"success": True}
    # 新码下错 4 次仍不到 5 次上限（计数确实被重置了）
    for _ in range(4):
        assert _run(vs.verify_code(email, "000000", "login")) is False
    assert _stored_code(email, "login") is not None


# ── verify_code_sync 三种上下文 ──────────────────────────────────────────


def test_sync_verify_reuses_main_loop(redis_env, smtp_configured):
    email = "sync@test.local"
    _run(vs.send_verification_code(email, "login"))
    code = _stored_code(email, "login")
    # 同步调用（当前线程无 loop 的模拟：直接函数调用）
    assert vs.verify_code_sync(email, code, "login") is True
    assert vs.verify_code_sync(email, code, "login") is False  # 已消费


def test_sync_verify_in_worker_thread(redis_env, smtp_configured):
    """线程池场景（当前线程无事件循环）→ asyncio.run 路径。"""
    import threading

    email = "thread@test.local"
    _run(vs.send_verification_code(email, "login"))
    code = _stored_code(email, "login")

    results: dict = {}

    def _worker():
        # 工作线程没有 running loop → verify_code_sync 走 asyncio.run
        results["ok"] = vs.verify_code_sync(email, code, "login")

    t = threading.Thread(target=_worker)
    t.start()
    t.join(timeout=20)
    assert results["ok"] is True


def test_code_is_random_per_send(redis_env, smtp_configured):
    email = "random@test.local"
    _run(vs.send_verification_code(email, "login"))
    first = _stored_code(email, "login")
    _run(_clear_rate_key(email))
    _run(vs.send_verification_code(email, "login"))
    second = _stored_code(email, "login")
    assert first != second  # 6 位数字码连续两次相同的概率 1e-6
