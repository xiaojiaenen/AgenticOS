"""内存 Redis fallback 回归（docs/design/系统改造总方案.md 战线 B3）。

自研归位：``core/redis.py`` 的 280 行手写 MemoryRedis 换成 fakeredis
（redis-py 的 drop-in 替身）。本文件锁住三件事：

1. 项目用到的 Redis 命令族在 fallback 下语义与真实 Redis 一致
   （string/set/zset/hash/list/TTL/pattern）；
2. pubsub 走标准 ``redis.pubsub()`` API（redis_relay / approval_manager
   的跨进程转发依赖它）；
3. RedisManager 内存模式初始化可用（开发环境无 Redis 时的主路径）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.core.redis import MemoryRedis, RedisManager


async def _make() -> MemoryRedis:
    return MemoryRedis()


@pytest.mark.asyncio
async def test_string_ops():
    r = await _make()
    try:
        assert await r.set("k", "v", ex=60) is True
        assert await r.get("k") == "v"
        # nx 失败返回 None（redis-py 标准语义；cache_service.check_verify_send_rate 依赖）
        assert await r.set("k", "v2", nx=True) is None
        assert await r.get("k") == "v"
        assert await r.incr("counter") == 1
        assert await r.incr("counter") == 2
        assert await r.delete("k", "counter") == 2
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_ttl():
    r = await _make()
    try:
        await r.set("k", "v")
        assert await r.expire("k", 100) in (True, 1)
        ttl = await r.ttl("k")
        assert 0 < ttl <= 100
        await r.delete("k")
        assert await r.ttl("k") == -2
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_hash_ops():
    r = await _make()
    try:
        await r.hset("h", mapping={"a": "1", "b": "2"})
        assert await r.hget("h", "a") == "1"
        assert (await r.hgetall("h")) == {"a": "1", "b": "2"}
        assert await r.hdel("h", "a") == 1
        assert await r.hget("h", "a") is None
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_set_ops():
    r = await _make()
    try:
        assert await r.sadd("s", "x", "y") == 2
        assert await r.scard("s") == 2
        assert "x" in await r.smembers("s")
        assert await r.srem("s", "x") == 1
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_zset_ops_standard_semantics():
    """cache_service（在线状态/近期会话）依赖的标准 zset 命令。"""
    r = await _make()
    try:
        await r.zadd("z", {"u1": 100.0, "u2": 200.0})
        assert await r.zcard("z") == 2
        assert await r.zrevrange("z", 0, -1) == ["u2", "u1"]
        assert await r.zrangebyscore("z", 0, 150) == ["u1"]
        assert await r.zremrangebyscore("z", 0, 150) == 1
        assert await r.zrem("z", "u2") == 1
        assert await r.zcard("z") == 0
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_list_ops():
    r = await _make()
    try:
        await r.rpush("l", "a", "b")
        await r.lpush("l", "c")
        assert await r.lrange("l", 0, -1) == ["c", "a", "b"]
        await r.ltrim("l", 0, 0)
        assert await r.llen("l") == 1
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_keys_pattern():
    r = await _make()
    try:
        await r.set("prefix:1", "a")
        await r.set("prefix:2", "b")
        await r.set("other", "c")
        keys = await r.keys("prefix:*")
        assert set(keys) == {"prefix:1", "prefix:2"}
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_pubsub_standard_api():
    """跨进程转发（redis_relay.forward_channel_to_queue）的契约。"""
    r = await _make()
    try:
        pubsub = r.pubsub()
        await pubsub.subscribe("chan")
        await r.publish("chan", json.dumps({"kind": "approval", "id": 1}))
        got = None
        for _ in range(5):
            message = await pubsub.get_message(timeout=2)
            if message and message.get("type") == "message":
                got = message.get("data")
                break
        assert got is not None
        assert json.loads(got)["kind"] == "approval"
        await pubsub.unsubscribe("chan")
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_pubsub_listen_iteration():
    """redis_relay 用 ``async for message in pubsub.listen()`` 消费。"""
    r = await _make()
    try:
        pubsub = r.pubsub()
        await pubsub.subscribe("ch2")
        await r.publish("ch2", "payload")

        async def _drain():
            async for message in pubsub.listen():
                if isinstance(message, dict) and message.get("type") == "message":
                    return message.get("data")

        got = await asyncio.wait_for(_drain(), timeout=3)
        assert got == "payload"
        await pubsub.unsubscribe("ch2")
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_manager_memory_mode():
    manager = RedisManager()
    await manager.init("", False)
    assert manager.is_memory
    await manager.client.set("mk", "mv")
    assert await manager.client.get("mk") == "mv"
    await manager.close()
