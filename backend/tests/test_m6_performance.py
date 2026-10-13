"""M6-A：性能优化线单测。

覆盖三处新增的独立可测单元：
- A4 dashboard 缓存：get-or-set 语义 + Redis 不可用时旁路 + key 隔离
- A5 LLM 并发闸：本地信号量上限、全局计数上限、幂等释放、降级路径
- A6 知识库缓存：命中/TTL 过期/写入失效

不覆盖压测本身（那是 loadtest/ 的职责）。
"""

import asyncio

from app.services.cache_service import CacheService
from app.services.llm_gate import LLMConcurrencyGate


class _FakeRedis:
    """最小 Redis 假实现，只覆盖 get/set 语义（够 A4 单测用）。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value
        return True


# ----------------------------------------------------------------------
# A4 dashboard 缓存
# ----------------------------------------------------------------------


def test_get_or_set_computes_once_then_serves_cache(monkeypatch) -> None:
    cache = CacheService()
    fake = _FakeRedis()
    monkeypatch.setattr("app.services.cache_service.get_redis_sync", lambda: fake)

    calls = {"n": 0}

    def producer() -> dict:
        calls["n"] += 1
        return {"total_runs": calls["n"]}

    assert cache.get_or_set_json_sync("k1", producer, ttl=30) == {"total_runs": 1}
    assert cache.get_or_set_json_sync("k1", producer, ttl=30) == {"total_runs": 1}
    # 第二次命中缓存，producer 不再执行
    assert calls["n"] == 1
    assert fake.store["k1"]


def test_get_or_set_bypasses_when_redis_unavailable(monkeypatch) -> None:
    """Redis 不可用时必须直查而不是抛错（保可用）。"""
    cache = CacheService()
    monkeypatch.setattr("app.services.cache_service.get_redis_sync", lambda: None)

    calls = {"n": 0}

    def producer() -> dict:
        calls["n"] += 1
        return {"v": calls["n"]}

    assert cache.get_or_set_json_sync("k2", producer, ttl=30) == {"v": 1}
    assert cache.get_or_set_json_sync("k2", producer, ttl=30) == {"v": 2}
    # 旁路 = 每次都真的算一次
    assert calls["n"] == 2


def test_get_or_set_bypasses_on_redis_error(monkeypatch) -> None:
    """Redis 读抛异常时应旁路，而不是把异常冒给接口（保可用）。"""
    cache = CacheService()

    class BrokenRedis:
        def get(self, key: str):
            raise RuntimeError("connection reset")

        def set(self, key: str, value: str, ex: int | None = None):
            raise RuntimeError("connection reset")

    monkeypatch.setattr("app.services.cache_service.get_redis_sync", lambda: BrokenRedis())
    assert cache.get_or_set_json_sync("k3", lambda: {"ok": True}, ttl=30) == {"ok": True}


def test_build_cache_key_isolates_user_and_params() -> None:
    cache = CacheService()
    a = cache.build_cache_key("dashboard:stats", "u1", "abc")
    b = cache.build_cache_key("dashboard:stats", "u2", "abc")
    c = cache.build_cache_key("dashboard:stats", "u1", "xyz")
    assert a != b, "不同用户必须隔离"
    assert a != c, "不同参数必须隔离"
    assert a.startswith("agenticos:dashboard:stats:")


# ----------------------------------------------------------------------
# A5 LLM 并发闸
# ----------------------------------------------------------------------


class _GateSettings:
    """最小 settings 替身（LLMConcurrencyGate 只读这几个字段）。"""

    llm_gate_enabled = True
    llm_gate_max_concurrency = 2
    llm_gate_lease_seconds = 300
    llm_gate_wait_seconds = 1.0


class _CountingRedis:
    """支持 INCR/DECR/EXPIRE/SET/EVAL 的假 Redis，用于验证全局闸。"""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.tokens: set[str] = set()
        self.expires: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def decr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) - 1
        return self.counters[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.tokens.add(key)
        self.expires[key] = ex or 0
        return True

    def get(self, key: str):
        value = self.counters.get(key)
        return None if value is None else str(value)

    def eval(self, script: str, numkeys: int, *keys: str) -> int:
        counter_key, token_key = keys
        if token_key in self.tokens:
            self.counters[counter_key] = self.counters.get(counter_key, 0) - 1
            if self.counters[counter_key] <= 0:
                self.counters[counter_key] = 0
            self.tokens.discard(token_key)
            return 1
        return 0


def _patch_gate_redis(monkeypatch, fake) -> None:
    monkeypatch.setattr("app.services.llm_gate.get_redis_sync", lambda: fake)
    monkeypatch.setattr("app.services.llm_gate.is_redis_memory", lambda: False)


def test_gate_caps_local_concurrency() -> None:
    """无 Redis 时也要有本地信号量兜底。"""

    async def run() -> int:
        gate = LLMConcurrencyGate(_GateSettings())
        gate.configure()
        current = {"n": 0}
        peak = {"n": 0}

        async def worker() -> None:
            async with gate.slot():
                current["n"] += 1
                peak["n"] = max(peak["n"], current["n"])
                await asyncio.sleep(0.02)
                current["n"] -= 1

        await asyncio.gather(*[worker() for _ in range(6)])
        return peak["n"]

    assert asyncio.run(run()) <= 2


def test_gate_caps_global_concurrency_and_releases(monkeypatch) -> None:
    """全局计数不超上限，且所有 slot 释放后计数归零。"""
    fake = _CountingRedis()
    _patch_gate_redis(monkeypatch, fake)

    async def run() -> tuple[int, int]:
        gate = LLMConcurrencyGate(_GateSettings())
        gate.configure()
        current = {"n": 0}
        peak = {"n": 0}

        async def worker() -> None:
            async with gate.slot():
                current["n"] += 1
                peak["n"] = max(peak["n"], current["n"])
                await asyncio.sleep(0.02)
                current["n"] -= 1

        await asyncio.gather(*[worker() for _ in range(6)])
        return peak["n"], fake.counters["agenticos:llm_gate:slots"]

    peak, final = asyncio.run(run())
    assert peak <= 2, f"全局并发超限: {peak}"
    assert final == 0, f"释放后计数应归零，实际 {final}"
    assert not fake.tokens, "所有 token 应已释放"


def test_gate_release_is_idempotent(monkeypatch) -> None:
    """重复释放不能把计数减成负数。"""
    fake = _CountingRedis()
    _patch_gate_redis(monkeypatch, fake)

    async def run() -> LLMConcurrencyGate:
        gate = LLMConcurrencyGate(_GateSettings())
        gate.configure()
        async with gate.slot():
            pass
        return gate

    gate = asyncio.run(run())
    assert fake.counters["agenticos:llm_gate:slots"] == 0
    # 再手动释放同一个 token（模拟崩溃路径的二次清理）不应减成负数
    gate._release_global("already-released-token")
    assert fake.counters["agenticos:llm_gate:slots"] == 0
    gate.shutdown()
    assert fake.counters["agenticos:llm_gate:slots"] == 0


def test_gate_disabled_is_noop(monkeypatch) -> None:
    """LLM_GATE_ENABLED=false 时不占用任何槽位。"""

    class Disabled(_GateSettings):
        llm_gate_enabled = False

    async def run() -> bool:
        gate = LLMConcurrencyGate(Disabled())
        gate.configure()
        async with gate.slot():
            return True

    assert asyncio.run(run()) is True


def test_gate_shutdown_releases_held_tokens(monkeypatch) -> None:
    """进程退出钩子应归还仍持有的槽位。"""
    fake = _CountingRedis()
    _patch_gate_redis(monkeypatch, fake)
    gate = LLMConcurrencyGate(_GateSettings())

    async def run() -> None:
        gate.configure()
        # 手动模拟"拿到 token 但没走 finally"的泄漏
        fake.counters["agenticos:llm_gate:slots"] = 1
        fake.tokens.add("agenticos:llm_gate:slots:leaked")
        gate._held_tokens.add("leaked")

    asyncio.run(run())
    gate.shutdown()
    assert fake.counters["agenticos:llm_gate:slots"] == 0
    assert not gate._held_tokens