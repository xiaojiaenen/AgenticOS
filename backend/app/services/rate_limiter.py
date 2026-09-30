"""登录/注册限流 — Redis 原子固定窗口实现。

取代旧的 ``AuthRateLimitModel``（MySQL 行级状态机）实现，消除先读后写竞态：

- 计数：``INCR`` 固定窗口计数 key，首次（返回 1）立刻 ``EXPIRE window_seconds``；
  达到 ``auth_rate_limit_max_attempts`` 后写封禁 key（TTL = ``auth_rate_limit_block_seconds``）。
- 封禁期内请求：直接拒绝并返回封禁剩余时间（向上取整到分钟，与旧行为一致）。
- 维度：沿用旧实现的 key 组合方式 ``{scope}:{email}:{ip}``（email 与 IP 组合为
  一个 key，而非两个独立计数），保证外部行为等价。
- Redis 不可用（REDIS_URL 未配置 / 连接失败 / 运行中连接断开）时降级为进程内
  ``threading.Lock`` 保护的计数表，开发/测试环境功能不变。

注意：调用点位于同步上下文（AuthService 在 ``asyncio.to_thread``/线程池中执行），
因此这里使用 ``app.core.redis.get_redis_sync()`` 提供的同步客户端。
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time

from app.core.config import Settings
from app.core.redis import get_redis_sync

_logger = logging.getLogger(__name__)

_COUNT_PREFIX = "auth:ratelimit:count:"
_BLOCK_PREFIX = "auth:ratelimit:block:"


def rate_limit_key(scope: str, *, email: str | None = None, client_ip: str | None = None) -> str:
    """与旧 AuthRateLimitModel 的主键格式保持一致：``{scope}:{email}:{ip}``"""
    normalized_ip = (client_ip or "unknown").strip().lower() or "unknown"
    normalized_email = (email or "").strip().lower()
    return f"{scope}:{normalized_email}:{normalized_ip}"


def _keys(scope: str, *, email: str | None = None, client_ip: str | None = None) -> tuple[str, str]:
    key = rate_limit_key(scope, email=email, client_ip=client_ip)
    return _COUNT_PREFIX + key, _BLOCK_PREFIX + key


class _MemoryRateLimitStore:
    """进程内限流存储（Redis 不可用时的 fallback）。

    threading.Lock 保证 INCR 语义的原子性；过期条目在写入时惰性清理。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # counter key -> (count, expires_at epoch seconds)
        self._counters: dict[str, tuple[int, float]] = {}
        # block key -> block_until epoch seconds
        self._blocks: dict[str, float] = {}

    def _purge_locked(self, now: float) -> None:
        for k in [k for k, (_, exp) in self._counters.items() if exp <= now]:
            del self._counters[k]
        for k in [k for k, until in self._blocks.items() if until <= now]:
            del self._blocks[k]

    def incr_and_maybe_block(
        self, count_key: str, block_key: str, *, window_seconds: int, max_attempts: int, block_seconds: int
    ) -> int:
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            count, expires_at = self._counters.get(count_key, (0, 0.0))
            if expires_at <= now:
                count = 0
                expires_at = now + window_seconds
            count += 1
            self._counters[count_key] = (count, expires_at)
            if count >= max_attempts:
                self._blocks[block_key] = now + block_seconds
            return count

    def blocked_remaining(self, block_key: str) -> int:
        now = time.time()
        with self._lock:
            until = self._blocks.get(block_key, 0.0)
            if until > now:
                return int(until - now)
            self._blocks.pop(block_key, None)
            return 0

    def clear(self, count_key: str, block_key: str) -> None:
        with self._lock:
            self._counters.pop(count_key, None)
            self._blocks.pop(block_key, None)

    def clear_pattern(self, pattern: str) -> None:
        with self._lock:
            now = time.time()
            self._purge_locked(now)
            for k in [k for k in self._counters if fnmatch.fnmatch(k, pattern)]:
                del self._counters[k]
            for k in [k for k in self._blocks if fnmatch.fnmatch(k, pattern)]:
                del self._blocks[k]


_memory = _MemoryRateLimitStore()


def check_rate_limit(
    settings: Settings, scope: str, *, email: str | None = None, client_ip: str | None = None
) -> int:
    """检查是否处于封禁期。返回封禁剩余秒数（0 表示放行）。"""
    _, block_key = _keys(scope, email=email, client_ip=client_ip)
    client = get_redis_sync()
    if client is not None:
        try:
            ttl = client.ttl(block_key)
            return ttl if isinstance(ttl, int) and ttl > 0 else 0
        except Exception as e:  # 连接中断 → 降级进程内计数
            _logger.warning("Redis 限流查询失败: %s，使用进程内 fallback", e)
            _set_sync_client_unusable()
    return _memory.blocked_remaining(block_key)


def record_failed_attempt(
    settings: Settings, scope: str, *, email: str | None = None, client_ip: str | None = None
) -> None:
    """记录一次失败尝试；达到上限时设置封禁 key（TTL = block_seconds）。"""
    count_key, block_key = _keys(scope, email=email, client_ip=client_ip)
    client = get_redis_sync()
    if client is not None:
        try:
            count = client.incr(count_key)
            if count == 1:
                # 仅首个进入窗口的请求设置 TTL，固定窗口由此自然滚动
                client.expire(count_key, settings.auth_rate_limit_window_seconds)
            if count >= settings.auth_rate_limit_max_attempts:
                client.set(block_key, "1", ex=settings.auth_rate_limit_block_seconds)
            return
        except Exception as e:
            _logger.warning("Redis 限流写入失败: %s，使用进程内 fallback", e)
            _set_sync_client_unusable()
    _memory.incr_and_maybe_block(
        count_key,
        block_key,
        window_seconds=settings.auth_rate_limit_window_seconds,
        max_attempts=settings.auth_rate_limit_max_attempts,
        block_seconds=settings.auth_rate_limit_block_seconds,
    )


def clear_rate_limit(
    settings: Settings, scope: str, *, email: str | None = None, client_ip: str | None = None
) -> None:
    """成功登录/注册后清除该维度的计数与封禁。"""
    count_key, block_key = _keys(scope, email=email, client_ip=client_ip)
    client = get_redis_sync()
    if client is not None:
        try:
            client.delete(count_key, block_key)
            return
        except Exception as e:
            _logger.warning("Redis 限流清除失败: %s，使用进程内 fallback", e)
            _set_sync_client_unusable()
    _memory.clear(count_key, block_key)


def clear_rate_limit_by_email(settings: Settings, scope: str, *, email: str) -> None:
    """按 email 前缀清除所有 IP 维度的限流状态（管理端解封用户时使用）。"""
    normalized_email = (email or "").strip().lower()
    count_pattern = f"{_COUNT_PREFIX}{scope}:{normalized_email}:*"
    block_pattern = f"{_BLOCK_PREFIX}{scope}:{normalized_email}:*"
    client = get_redis_sync()
    if client is not None:
        try:
            count_keys = list(client.scan_iter(match=count_pattern))
            block_keys = list(client.scan_iter(match=block_pattern))
            keys = count_keys + block_keys
            if keys:
                client.delete(*keys)
            return
        except Exception as e:
            _logger.warning("Redis 限流按邮箱清除失败: %s，使用进程内 fallback", e)
            _set_sync_client_unusable()
    _memory.clear_pattern(count_pattern)
    _memory.clear_pattern(block_pattern)


def _set_sync_client_unusable() -> None:
    """Redis 连接已中断：标记同步客户端需重建，避免每次请求都白等超时。

    下次 ``get_redis_sync()`` 会重新尝试建连。
    """
    import app.core.redis as redis_module

    redis_module.mark_sync_client_unusable()
