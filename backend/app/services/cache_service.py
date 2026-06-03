"""缓存服务，基于 Redis 实现各种缓存场景。

支持的场景：
1. 输入补全 — Sorted Set 前缀匹配
2. 频率限制 — String INCR + EXPIRE
3. 在线用户 — Set
4. 会话缓存 — Hash
5. 审批队列 — List + Pub/Sub
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.core.redis import get_redis

_logger = logging.getLogger("cache")


class CacheService:
    """缓存服务"""

    def __init__(self):
        self._input_cache_loaded = False

    async def load_history_from_db(self) -> None:
        """启动时从数据库加载历史用户输入到缓存"""
        if self._input_cache_loaded:
            return
        self._input_cache_loaded = True
        try:
            from app.db.session import create_db_session
            from app.db.models import AgentMessageModel
            from sqlalchemy import select

            def _load():
                with create_db_session() as db:
                    rows = db.scalars(
                        select(AgentMessageModel.message_json)
                        .order_by(AgentMessageModel.id.desc())
                        .limit(2000)
                    ).all()
                    return rows

            import asyncio
            rows = await asyncio.to_thread(_load)
            count = 0
            for raw in rows:
                try:
                    import json
                    data = json.loads(raw)
                    if data.get("role") == "user" and data.get("content"):
                        text = data["content"].strip()
                        if len(text) >= 2:
                            await self.add_global_input(text)
                            count += 1
                except Exception:
                    continue
            _logger.info(f"Loaded {count} historical inputs into cache")
        except Exception as e:
            _logger.warning(f"Failed to load history into cache: {e}")

    # ============================================================
    # 1. 输入补全 — Sorted Set 前缀匹配
    # ============================================================

    async def add_user_input(self, user_id: int, text: str) -> None:
        """记录用户输入到补全缓存"""
        if not text or len(text) < 2:
            return
        redis = get_redis()
        key = f"suggest:user:{user_id}"
        # 用时间戳作为 score，便于按时间排序
        await redis.zadd(key, {text: time.time()})
        # 限制每个用户最多 500 条
        await redis.zremrangebyscore(key, 0, time.time() - 30 * 86400)  # 保留 30 天
        count = await redis.zcard(key)
        if count > 500:
            await redis.zremrangebyscore(key, 0, time.time() - 7 * 86400)  # 压缩到 7 天

    async def suggest_input(self, user_id: int, prefix: str, limit: int = 5) -> list[str]:
        """根据前缀匹配用户历史输入"""
        if not prefix or len(prefix) < 2:
            return []
        redis = get_redis()
        key = f"suggest:user:{user_id}"
        # 使用 ZRANGEBYLEX 进行前缀匹配
        # Redis lexicographic range: [prefix to prefix\xff
        results = await redis.zrangebylex(key, f"[{prefix}", f"[{prefix}\xff", 0, limit)
        return results

    async def add_global_input(self, text: str) -> None:
        """记录全局输入（所有用户共享）"""
        if not text or len(text) < 2:
            return
        redis = get_redis()
        key = "suggest:global"
        await redis.zadd(key, {text: time.time()})
        # 限制全局最多 2000 条
        count = await redis.zcard(key)
        if count > 2000:
            await redis.zremrangebyscore(key, 0, time.time() - 7 * 86400)

    async def suggest_global(self, prefix: str, limit: int = 5) -> list[str]:
        """全局前缀匹配"""
        if not prefix or len(prefix) < 2:
            return []
        redis = get_redis()
        key = "suggest:global"
        return await redis.zrangebylex(key, f"[{prefix}", f"[{prefix}\xff", 0, limit)

    # ============================================================
    # 2. 频率限制 — String INCR + EXPIRE
    # ============================================================

    async def check_rate_limit(
        self,
        key: str,
        max_attempts: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """检查频率限制

        返回: (是否允许, 剩余次数)
        """
        redis = get_redis()
        full_key = f"ratelimit:{key}"

        current = await redis.incr(full_key)
        if current == 1:
            await redis.expire(full_key, window_seconds)

        remaining = max(0, max_attempts - current)
        allowed = current <= max_attempts
        return allowed, remaining

    async def is_blocked(self, key: str) -> bool:
        """检查是否被封禁"""
        redis = get_redis()
        return await redis.exists(f"ratelimit:block:{key}")

    async def block(self, key: str, seconds: int) -> None:
        """封禁"""
        redis = get_redis()
        await redis.set(f"ratelimit:block:{key}", "1", ex=seconds)

    async def get_rate_limit_ttl(self, key: str) -> int:
        """获取频率限制剩余时间"""
        redis = get_redis()
        return await redis.ttl(f"ratelimit:{key}")

    # ============================================================
    # 3. 在线用户 — Set
    # ============================================================

    async def user_online(self, user_id: int) -> None:
        """标记用户在线"""
        redis = get_redis()
        await redis.sadd("online:users", str(user_id))
        await redis.set(f"online:user:{user_id}", str(int(time.time())), ex=300)

    async def user_offline(self, user_id: int) -> None:
        """标记用户离线"""
        redis = get_redis()
        await redis.srem("online:users", str(user_id))
        await redis.delete(f"online:user:{user_id}")

    async def get_online_users(self) -> set[str]:
        """获取在线用户列表"""
        redis = get_redis()
        return await redis.smembers("online:users")

    async def get_online_count(self) -> int:
        """获取在线用户数"""
        redis = get_redis()
        return await redis.scard("online:users")

    # ============================================================
    # 4. 会话缓存 — Hash
    # ============================================================

    async def cache_session(self, session_id: str, data: dict[str, Any], ttl: int = 3600) -> None:
        """缓存会话数据"""
        redis = get_redis()
        key = f"session:{session_id}"
        for k, v in data.items():
            await redis.hset(key, field=k, value=json.dumps(v) if not isinstance(v, str) else v)
        await redis.expire(key, ttl)

    async def get_cached_session(self, session_id: str) -> dict[str, Any] | None:
        """获取缓存的会话数据"""
        redis = get_redis()
        key = f"session:{session_id}"
        data = await redis.hgetall(key)
        if not data:
            return None
        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result

    async def invalidate_session_cache(self, session_id: str) -> None:
        """清除会话缓存"""
        redis = get_redis()
        await redis.delete(f"session:{session_id}")

    # ============================================================
    # 5. 审批队列 — List
    # ============================================================

    async def push_approval(self, session_id: str, approval_data: dict[str, Any]) -> None:
        """推送审批请求到队列"""
        redis = get_redis()
        key = f"approvals:{session_id}"
        await redis.rpush(key, json.dumps(approval_data, ensure_ascii=False))

    async def pop_approval(self, session_id: str) -> dict[str, Any] | None:
        """弹出审批请求"""
        redis = get_redis()
        key = f"approvals:{session_id}"
        items = await redis.lrange(key, 0, 0)
        if not items:
            return None
        await redis.ltrim(key, 1, -1)
        return json.loads(items[0])

    # ============================================================
    # 6. 通用工具
    # ============================================================

    async def cache_json(self, key: str, data: Any, ttl: int = 300) -> None:
        """缓存 JSON 数据"""
        redis = get_redis()
        await redis.set(key, json.dumps(data, ensure_ascii=False), ex=ttl)

    async def get_cached_json(self, key: str) -> Any | None:
        """获取缓存的 JSON 数据"""
        redis = get_redis()
        raw = await redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None


# 全局单例
_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    """获取缓存服务单例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
