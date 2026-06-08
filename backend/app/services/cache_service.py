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

    # Redis key 统一前缀
    KEY_PREFIX = "agenticos:"

    def __init__(self):
        self._input_cache_loaded = False

    @classmethod
    def _key(cls, name: str) -> str:
        """添加统一前缀"""
        return f"{cls.KEY_PREFIX}{name}"

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
        """记录用户输入到补全缓存（按标点拆分为短语）"""
        if not text or len(text) < 2:
            return
        redis = get_redis()
        key = self._key(f"suggest:user:{user_id}")
        segments = self._split_segments(text)
        now = time.time()
        # 用时间戳作为 score，便于按时间排序
        mapping = {seg: now for seg in segments}
        if mapping:
            await redis.zadd(key, mapping)
        # 限制每个用户最多 500 条
        await redis.zremrangebyscore(key, 0, now - 30 * 86400)  # 保留 30 天
        count = await redis.zcard(key)
        if count > 500:
            await redis.zremrangebyscore(key, 0, now - 7 * 86400)  # 压缩到 7 天

    async def suggest_input(self, user_id: int, query: str, limit: int = 5) -> list[str]:
        """子串匹配 + 续写预测

        返回格式：原始完整文本（前端从中截取续写部分）
        评分：前缀匹配 > 子串匹配，最近使用 > 早期使用

        当查询包含标点时，取最后一个片段进行匹配。
        例如输入 "帮我写文章，请用" → 用 "请用" 去匹配
        """
        if not query or len(query) < 2:
            return []
        redis = get_redis()
        key = self._key(f"suggest:user:{user_id}")
        items = await redis.zrevrange(key, 0, -1)  # 按时间降序
        # 取最后一个片段作为查询词
        search_query = self._extract_last_segment(query)
        return self._match_and_rank(items, search_query, limit)

    async def add_global_input(self, text: str) -> None:
        """记录全局输入（按标点拆分为短语，所有用户共享）"""
        if not text or len(text) < 2:
            return
        redis = get_redis()
        key = self._key("suggest:global")
        segments = self._split_segments(text)
        now = time.time()
        mapping = {seg: now for seg in segments}
        if mapping:
            await redis.zadd(key, mapping)
        # 限制全局最多 2000 条
        count = await redis.zcard(key)
        if count > 2000:
            await redis.zremrangebyscore(key, 0, now - 7 * 86400)

    async def suggest_global(self, query: str, limit: int = 5) -> list[str]:
        """全局子串匹配 + 续写预测

        当查询包含标点时，取最后一个片段进行匹配。
        """
        if not query or len(query) < 2:
            return []
        redis = get_redis()
        key = self._key("suggest:global")
        items = await redis.zrevrange(key, 0, -1)
        search_query = self._extract_last_segment(query)
        return self._match_and_rank(items, search_query, limit)

    @staticmethod
    def _split_segments(text: str) -> list[str]:
        """按标点符号和换行符拆分为短语

        拆分规则：
        - 中文标点：。！？；：、，…—
        - 英文标点：. ! ? ; : , \n
        - 过滤掉长度 < 2 的片段
        - 去除首尾空白
        """
        import re
        # 按中英文标点和换行拆分
        parts = re.split(r'[。！？；：、，…—.!?;:,\n]+', text)
        segments = []
        for part in parts:
            seg = part.strip()
            if len(seg) >= 2:
                segments.append(seg)
        return segments

    @staticmethod
    def _extract_last_segment(text: str) -> str:
        """从查询文本中提取最后一个片段作为搜索词

        例如：
        - "帮我写文章，请用" → "请用"
        - "你好世界" → "你好世界"（无标点，返回原文）
        - "Hello, world" → "world"
        """
        import re
        # 按中英文标点和换行拆分
        parts = re.split(r'[。！？；：、，…—.!?;:,\n]+', text)
        # 取最后一个非空片段
        for part in reversed(parts):
            seg = part.strip()
            if len(seg) >= 1:
                return seg
        return text

    @staticmethod
    def _match_and_rank(items: list[str], query: str, limit: int) -> list[str]:
        """子串匹配 + 评分排序

        评分规则：
        - 前缀匹配：1.0 分（用户输入是文本开头）
        - 子串匹配：0.7 分（用户输入在文本中间）
        - 位置靠前加分：匹配位置越靠前，分越高
        """
        query_lower = query.lower()
        scored: list[tuple[str, float]] = []

        for text in items:
            text_lower = text.lower()
            idx = text_lower.find(query_lower)
            if idx < 0:
                continue
            # 前缀匹配得 1.0，子串匹配得 0.7，位置越靠前越高
            base_score = 1.0 if idx == 0 else 0.7
            # 位置惩罚：每偏移一个字符扣 0.02
            pos_penalty = min(idx * 0.02, 0.3)
            score = base_score - pos_penalty
            scored.append((text, score))

        # 按分数降序，同分按长度升序（短的优先）
        scored.sort(key=lambda x: (-x[1], len(x[0])))
        return [text for text, _ in scored[:limit]]

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
        full_key = self._key(f"ratelimit:{key}")

        current = await redis.incr(full_key)
        if current == 1:
            await redis.expire(full_key, window_seconds)

        remaining = max(0, max_attempts - current)
        allowed = current <= max_attempts
        return allowed, remaining

    async def is_blocked(self, key: str) -> bool:
        """检查是否被封禁"""
        redis = get_redis()
        return await redis.exists(self._key(f"ratelimit:block:{key}"))

    async def block(self, key: str, seconds: int) -> None:
        """封禁"""
        redis = get_redis()
        await redis.set(self._key(f"ratelimit:block:{key}"), "1", ex=seconds)

    async def get_rate_limit_ttl(self, key: str) -> int:
        """获取频率限制剩余时间"""
        redis = get_redis()
        return await redis.ttl(self._key(f"ratelimit:{key}"))

    # ============================================================
    # 3. 在线用户 — Set
    # ============================================================

    async def user_online(self, user_id: int) -> None:
        """标记用户在线"""
        redis = get_redis()
        await redis.sadd(self._key("online:users"), str(user_id))
        await redis.set(self._key(f"online:user:{user_id}"), str(int(time.time())), ex=300)

    async def user_offline(self, user_id: int) -> None:
        """标记用户离线"""
        redis = get_redis()
        await redis.srem(self._key("online:users"), str(user_id))
        await redis.delete(self._key(f"online:user:{user_id}"))

    async def get_online_users(self) -> set[str]:
        """获取在线用户列表"""
        redis = get_redis()
        return await redis.smembers(self._key("online:users"))

    async def get_online_count(self) -> int:
        """获取在线用户数"""
        redis = get_redis()
        return await redis.scard(self._key("online:users"))

    # ============================================================
    # 4. 会话缓存 — Hash
    # ============================================================

    async def cache_session(self, session_id: str, data: dict[str, Any], ttl: int = 3600) -> None:
        """缓存会话数据"""
        redis = get_redis()
        key = self._key(f"session:{session_id}")
        for k, v in data.items():
            await redis.hset(key, field=k, value=json.dumps(v) if not isinstance(v, str) else v)
        await redis.expire(key, ttl)

    async def get_cached_session(self, session_id: str) -> dict[str, Any] | None:
        """获取缓存的会话数据"""
        redis = get_redis()
        key = self._key(f"session:{session_id}")
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
        await redis.delete(self._key(f"session:{session_id}"))

    # ============================================================
    # 5. 审批队列 — List
    # ============================================================

    async def push_approval(self, session_id: str, approval_data: dict[str, Any]) -> None:
        """推送审批请求到队列"""
        redis = get_redis()
        key = self._key(f"approvals:{session_id}")
        await redis.rpush(key, json.dumps(approval_data, ensure_ascii=False))

    async def pop_approval(self, session_id: str) -> dict[str, Any] | None:
        """弹出审批请求"""
        redis = get_redis()
        key = self._key(f"approvals:{session_id}")
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
        await redis.set(self._key(key), json.dumps(data, ensure_ascii=False), ex=ttl)

    async def get_cached_json(self, key: str) -> Any | None:
        """获取缓存的 JSON 数据"""
        redis = get_redis()
        raw = await redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    # ---- 验证码 ----

    async def set_verify_code(self, email: str, purpose: str, code: str, ttl: int = 300) -> None:
        """存储验证码，默认 5 分钟过期"""
        redis = get_redis()
        key = self._key(f"verify:{purpose}:{email}")
        val = code if isinstance(code, bytes) else code.encode()
        await redis.set(key, val, ex=ttl)

    async def get_verify_code(self, email: str, purpose: str) -> str | None:
        """获取验证码"""
        redis = get_redis()
        key = self._key(f"verify:{purpose}:{email}")
        raw = await redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw

    async def delete_verify_code(self, email: str, purpose: str) -> None:
        """验证成功后删除验证码"""
        redis = get_redis()
        key = self._key(f"verify:{purpose}:{email}")
        await redis.delete(key)

    async def check_verify_send_rate(self, email: str, purpose: str) -> bool:
        """检查验证码发送频率，每分钟最多 1 次。返回 True 表示可以发送"""
        redis = get_redis()
        key = self._key(f"verify:rate:{purpose}:{email}")
        # nx=True 只在 key 不存在时设置，ex=60 60秒过期
        result = await redis.set(key, b"1", ex=60, nx=True)
        return result is not None


# 全局单例
_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    """获取缓存服务单例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
