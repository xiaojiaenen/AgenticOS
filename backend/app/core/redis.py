"""Redis 连接管理器，支持单机/集群模式，开发环境 fallback 到内存。

使用方式：
    from app.core.redis import get_redis
    redis = get_redis()
    await redis.set("key", "value", ex=60)
    value = await redis.get("key")

配置：
    REDIS_URL=redis://localhost:6379/0     # 单机模式
    REDIS_URL=redis://host1:6379,host2:6379  # 集群模式（配合 REDIS_CLUSTER=true）
    REDIS_URL=                             # 留空使用内存 fallback（开发环境）
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

_logger = logging.getLogger("redis")


class MemoryRedis:
    """内存 Redis fallback，开发环境使用。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expires: dict[str, float] = {}
        self._sets: dict[str, set[str]] = {}
        self._sorted_sets: dict[str, list[tuple[str, float]]] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._lists: dict[str, list[str]] = {}

    def _is_expired(self, key: str) -> bool:
        if key in self._expires and time.time() > self._expires[key]:
            del self._expires[key]
            self._data.pop(key, None)
            self._sets.pop(key, None)
            self._sorted_sets.pop(key, None)
            self._hashes.pop(key, None)
            self._lists.pop(key, None)
            return True
        return False

    async def get(self, key: str) -> str | None:
        if self._is_expired(key):
            return None
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._data[key] = value
        if ex:
            self._expires[key] = time.time() + ex
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
            self._expires.pop(key, None)
            self._sets.pop(key, None)
            self._sorted_sets.pop(key, None)
            self._hashes.pop(key, None)
            self._lists.pop(key, None)
        return count

    async def incr(self, key: str) -> int:
        val = int(self._data.get(key, "0")) + 1
        self._data[key] = str(val)
        return val

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self._data:
            self._expires[key] = time.time() + seconds
            return True
        return False

    async def ttl(self, key: str) -> int:
        if key not in self._data:
            return -2
        if key not in self._expires:
            return -1
        remaining = int(self._expires[key] - time.time())
        return remaining if remaining > 0 else -2

    # --- Set 操作 ---
    async def sadd(self, key: str, *values: str) -> int:
        if key not in self._sets:
            self._sets[key] = set()
        before = len(self._sets[key])
        self._sets[key].update(values)
        return len(self._sets[key]) - before

    async def srem(self, key: str, *values: str) -> int:
        if key not in self._sets:
            return 0
        before = len(self._sets[key])
        self._sets[key] -= set(values)
        return before - len(self._sets[key])

    async def smembers(self, key: str) -> set[str]:
        self._is_expired(key)
        return self._sets.get(key, set()).copy()

    async def scard(self, key: str) -> int:
        self._is_expired(key)
        return len(self._sets.get(key, set()))

    # --- Sorted Set 操作 ---
    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        if key not in self._sorted_sets:
            self._sorted_sets[key] = []
        existing = {m[0]: i for i, m in enumerate(self._sorted_sets[key])}
        added = 0
        for member, score in mapping.items():
            if member in existing:
                self._sorted_sets[key][existing[member]] = (member, score)
            else:
                self._sorted_sets[key].append((member, score))
                added += 1
        self._sorted_sets[key].sort(key=lambda x: x[1], reverse=True)
        return added

    async def zrangebylex(self, key: str, min_val: str, max_val: str, start: int = 0, num: int = -1) -> list[str]:
        self._is_expired(key)
        items = self._sorted_sets.get(key, [])
        # 前缀匹配：min_val 是 [prefix，max_val 是 [prefix\xff
        prefix = min_val.lstrip("[(")
        results = []
        for member, score in items:
            if member.startswith(prefix):
                results.append(member)
        # 按 score 降序排列（最近使用的在前）
        results.sort(key=lambda m: next((s for mb, s in items if mb == m), 0), reverse=True)
        if num > 0:
            results = results[start:start + num]
        return results

    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        self._is_expired(key)
        items = self._sorted_sets.get(key, [])
        if end == -1:
            end = len(items) - 1
        return [m[0] for m in items[start:end + 1]]

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        if key not in self._sorted_sets:
            return 0
        before = len(self._sorted_sets[key])
        self._sorted_sets[key] = [
            (m, s) for m, s in self._sorted_sets[key]
            if not (min_score <= s <= max_score)
        ]
        return before - len(self._sorted_sets[key])

    async def zcard(self, key: str) -> int:
        self._is_expired(key)
        return len(self._sorted_sets.get(key, []))

    # --- Hash 操作 ---
    async def hset(self, key: str, field: str | None = None, value: str | None = None, mapping: dict | None = None) -> int:
        if key not in self._hashes:
            self._hashes[key] = {}
        added = 0
        if field and value:
            if field not in self._hashes[key]:
                added = 1
            self._hashes[key][field] = value
        if mapping:
            for k, v in mapping.items():
                if k not in self._hashes[key]:
                    added += 1
                self._hashes[key][k] = str(v)
        return added

    async def hget(self, key: str, field: str) -> str | None:
        self._is_expired(key)
        return self._hashes.get(key, {}).get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        self._is_expired(key)
        return self._hashes.get(key, {}).copy()

    async def hdel(self, key: str, *fields: str) -> int:
        if key not in self._hashes:
            return 0
        count = 0
        for field in fields:
            if field in self._hashes[key]:
                del self._hashes[key][field]
                count += 1
        return count

    # --- List 操作 ---
    async def lpush(self, key: str, *values: str) -> int:
        if key not in self._lists:
            self._lists[key] = []
        for v in values:
            self._lists[key].insert(0, v)
        return len(self._lists[key])

    async def rpush(self, key: str, *values: str) -> int:
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].extend(values)
        return len(self._lists[key])

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        self._is_expired(key)
        items = self._lists.get(key, [])
        if end == -1:
            end = len(items) - 1
        return items[start:end + 1]

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        if key in self._lists:
            if end == -1:
                end = len(self._lists[key]) - 1
            self._lists[key] = self._lists[key][start:end + 1]
        return True

    async def llen(self, key: str) -> int:
        self._is_expired(key)
        return len(self._lists.get(key, []))

    # --- 通用操作 ---
    async def exists(self, key: str) -> bool:
        self._is_expired(key)
        return key in self._data or key in self._sets or key in self._sorted_sets or key in self._hashes or key in self._lists

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        all_keys = set(self._data.keys()) | set(self._sets.keys()) | set(self._sorted_sets.keys()) | set(self._hashes.keys()) | set(self._lists.keys())
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern) and not self._is_expired(k)]

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class RedisManager:
    """Redis 连接管理器，支持单机/集群/内存 fallback。"""

    def __init__(self) -> None:
        self._client = None
        self._is_memory = True

    async def init(self, redis_url: str = "", cluster: bool = False) -> None:
        if not redis_url:
            _logger.info("REDIS_URL 未配置，使用内存 fallback")
            self._client = MemoryRedis()
            self._is_memory = True
            return

        try:
            import redis.asyncio as aioredis

            if cluster:
                from redis.asyncio.cluster import RedisCluster
                self._client = RedisCluster.from_url(redis_url)
                _logger.info(f"Redis 集群模式: {redis_url}")
            else:
                self._client = aioredis.from_url(redis_url, decode_responses=True)
                _logger.info(f"Redis 单机模式: {redis_url}")

            await self._client.ping()
            self._is_memory = False
            _logger.info("Redis 连接成功")
        except Exception as e:
            _logger.warning(f"Redis 连接失败: {e}，fallback 到内存")
            self._client = MemoryRedis()
            self._is_memory = True

    @property
    def client(self):
        if self._client is None:
            self._client = MemoryRedis()
        return self._client

    @property
    def is_memory(self) -> bool:
        return self._is_memory

    async def close(self) -> None:
        if self._client and not self._is_memory:
            await self._client.close()


# 全局单例
_manager = RedisManager()


async def init_redis(redis_url: str = "", cluster: bool = False) -> None:
    """初始化 Redis 连接"""
    await _manager.init(redis_url, cluster)


def get_redis():
    """获取 Redis 客户端（开发环境返回内存 fallback）"""
    return _manager.client


def is_redis_memory() -> bool:
    """是否使用内存 fallback"""
    return _manager.is_memory


async def close_redis() -> None:
    """关闭 Redis 连接"""
    await _manager.close()
