"""M6-A5：LLM 全局并发闸。

解决的问题：上游 LLM 供应商有并发配额，多实例部署时每个实例各自计数会
把总并发打穿配额（设计稿目标：全局 ≤ 60，可配）。

两层结构：
1. **本地兜底**：每实例一个 ``asyncio.Semaphore``，保证单实例内不会因为
   调度抖动超发，且 Redis 挂了也不至于完全裸奔。
2. **跨实例共享**：Redis 计数器 + TTL 租约。拿到本地槽位后再向 Redis 申请
   一个全局槽位（INCR），计数超过上限则回退本地（本次放行，不无限排队）。

降级策略（保可用不保精确）：任何 Redis 异常都只 log warning 并放行，
绝不因闸门故障阻塞用户请求。等待上限 ``LLM_GATE_WAIT_SECONDS`` 同理 ——
超时后放行并告警，宁可短暂超发也不要把 SSE 挂死。

幂等释放：每次成功获取全局槽位都会生成唯一 token，释放时用 Lua 脚本做
"仅当 token 存在时 DECR 并 DEL"，重复释放不会重复减计数；租约 TTL 保证
进程崩溃后槽位最多占用 ``LLM_GATE_LEASE_SECONDS`` 自动回收。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import AsyncIterator

from app.core.config import Settings, get_settings
from app.core.redis import get_redis_sync, is_redis_memory

_logger = logging.getLogger("llm_gate")

# 全局槽位登记表（同一 token 只会登记一次）
_GATE_KEY = "agenticos:llm_gate:slots"

# 幂等释放：token 存在才 DECR，然后删 token。
# 用 Lua 保证「判断 + 减计数」是原子的，避免重复释放把计数减成负数。
_RELEASE_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then
    local v = redis.call('DECR', KEYS[1])
    if v <= 0 then
        redis.call('SET', KEYS[1], '0')
    end
    redis.call('DEL', KEYS[2])
    return 1
end
return 0
"""


class LLMConcurrencyGate:
    """LLM 全局并发闸（进程级单例）。

    ``slot()`` 是唯一入口：

        async with llm_gate.slot():
            await call_llm(...)

    一次 ``run`` 包一次 —— 语义是"这个 SSE 运行期间占用一个 LLM 会话时段"，
    而不是"每个 HTTP 请求包一次"（一个 run 内部可能有多次 LLM 往返）。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._local: asyncio.Semaphore | None = None
        self._local_limit = 0
        # 本进程当前持有的全局 token（进程级集合，释放钩子用）
        self._held_tokens: set[str] = set()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def configure(self, settings: Settings | None = None) -> None:
        """（lifespan 启动时）按最新配置重建本地信号量。

        本地信号量必须在事件循环内创建（asyncio.Semaphore 绑定 loop），
        所以延迟到 lifespan 里 configure，而不是模块导入时。
        """
        if settings is not None:
            self._settings = settings
        limit = max(1, int(self._settings.llm_gate_max_concurrency))
        if self._local is None or self._local_limit != limit:
            self._local = asyncio.Semaphore(limit)
            self._local_limit = limit
            _logger.info(
                "LLM gate configured: local=%d global=%d lease=%ss",
                limit,
                limit,
                self._settings.llm_gate_lease_seconds,
            )

    @property
    def enabled(self) -> bool:
        return bool(self._settings.llm_gate_enabled)

    @property
    def max_concurrency(self) -> int:
        return max(1, int(self._settings.llm_gate_max_concurrency))

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """占用一个 LLM 并发槽位。

        关闭闸门（``LLM_GATE_ENABLED=false``）时是纯 no-op。
        Redis 不可用/异常时只走本地信号量。
        """
        if not self.enabled:
            yield
            return

        self.configure()
        assert self._local is not None
        local = self._local

        acquired_local = False
        token: str | None = None
        try:
            # 先抢本地槽位（本地不会失败）
            await asyncio.wait_for(local.acquire(), timeout=self._settings.llm_gate_wait_seconds)
            acquired_local = True
            # 再申请全局槽位（可能失败 —— 失败只降级不阻断）
            token = await self._acquire_global()
            yield
        finally:
            if token is not None:
                self._release_global(token)
            if acquired_local:
                local.release()

    # ------------------------------------------------------------------
    # 全局计数（Redis）
    # ------------------------------------------------------------------

    async def _acquire_global(self) -> str | None:
        """申请全局槽位，返回 token（None 表示降级到纯本地）。"""
        if is_redis_memory():
            return None
        client = get_redis_sync()
        if client is None:
            return None

        token = uuid.uuid4().hex
        deadline = time.monotonic() + self._settings.llm_gate_wait_seconds
        try:
            while True:
                # 同步 Redis 客户端会阻塞事件循环，放到线程里执行
                count = await asyncio.to_thread(client.incr, _GATE_KEY)
                if count == 1:
                    # 计数器刚建立才设 TTL，避免计数先于 TTL 存在导致永不过期
                    await asyncio.to_thread(
                        client.expire, _GATE_KEY, self._settings.llm_gate_lease_seconds
                    )
                if count <= self.max_concurrency:
                    # 登记 token：key 自带 TTL，进程崩溃后自动回收
                    await asyncio.to_thread(
                        client.set,
                        f"{_GATE_KEY}:{token}",
                        "1",
                        ex=self._settings.llm_gate_lease_seconds,
                    )
                    self._held_tokens.add(token)
                    return token
                # 超限：撤销本次 INCR 并等待重试
                await asyncio.to_thread(client.decr, _GATE_KEY)
                if time.monotonic() >= deadline:
                    _logger.warning(
                        "LLM gate: waited %.0fs for global slot, proceeding locally",
                        self._settings.llm_gate_wait_seconds,
                    )
                    return None
                await asyncio.sleep(0.2)
        except Exception as e:  # noqa: BLE001 —— Redis 抖动一律降级
            _logger.warning("LLM gate: global acquire failed, falling back to local semaphore: %s", e)
            return None

    def _release_global(self, token: str) -> None:
        """幂等释放全局槽位（Lua 保证重复调用安全）。"""
        self._held_tokens.discard(token)
        if is_redis_memory():
            return
        client = get_redis_sync()
        if client is None:
            return
        try:
            client.eval(_RELEASE_LUA, 2, _GATE_KEY, f"{_GATE_KEY}:{token}")
        except Exception as e:  # noqa: BLE001 —— 释放失败靠租约 TTL 兜底
            _logger.warning("LLM gate: global release failed for token %s: %s", token, e)

    def shutdown(self) -> None:
        """释放本进程仍持有的全部全局槽位（lifespan 关闭钩子）。

        正常路径下 slot() 的 finally 已经归还；这里覆盖进程被取消 /
        事件循环提前关闭的边界。幂等 —— 重复释放不会把计数减成负数。
        """
        if not self._held_tokens:
            return
        pending = list(self._held_tokens)
        _logger.info("LLM gate shutdown: releasing %d held slot(s)", len(pending))
        for token in pending:
            self._release_global(token)

    def current_global_count(self) -> int | None:
        """当前全局占用数（诊断用；Redis 不可用返回 None）。"""
        client = get_redis_sync()
        if client is None or is_redis_memory():
            return None
        try:
            value = client.get(_GATE_KEY)
            return int(value) if value is not None else 0
        except Exception:  # noqa: BLE001
            return None


_gate = LLMConcurrencyGate()


def get_llm_gate() -> LLMConcurrencyGate:
    """获取全局 LLM 并发闸单例。"""
    return _gate