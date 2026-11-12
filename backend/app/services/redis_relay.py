"""Redis pub/sub → 本地 asyncio.Queue 的转发助手。

ApprovalManager 与 InteractionBroker 是同构的「等人」协调器，都需要两段一样的
管道代码：

1. **事件转发**：外部 Redis 模式下订阅会话频道，把 publish 的交互事件写进
   SSE pump 消费的本地队列（内存 Redis 模式由请求方直投，无需 listener）；
2. **决策转发**：外部 Redis 模式下订阅 per-interaction 决策频道，把 resolve
   的决定写进等待方的本地队列。

抽到这里是为了两处共享同一份实现（连接关闭、异常吞噬、bytes 解码），改一处
两处生效。等待方不直接对 redis.asyncio 客户端调用 subscribe() —— MemoryRedis
的 subscribe 返回 Queue 而真实客户端返回 PubSub 对象，两者 API 不兼容，统一走
本模块的 listener 任务。
"""

from __future__ import annotations

import asyncio
import json
import logging

_logger = logging.getLogger("redis_relay")


async def close_pubsub(pubsub, channel: str | None = None) -> None:
    """尽力关闭 pubsub 连接（兼容 redis.asyncio 与测试 fake 的不同关闭接口）。"""
    if pubsub is None:
        return
    try:
        if channel is not None:
            await pubsub.unsubscribe(channel)
        else:
            await pubsub.unsubscribe()
    except Exception:  # noqa: BLE001
        pass
    for closer in ("aclose", "close"):
        fn = getattr(pubsub, closer, None)
        if fn is not None:
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                pass
            break


async def forward_channel_to_queue(
    redis,
    channel: str,
    queue: asyncio.Queue,
    *,
    parse_json: bool = True,
) -> None:
    """订阅 channel，把消息转发进 queue，作为可 cancel 的后台任务运行。

    - ``parse_json=True``：消息为 JSON dict 时入队（解析失败跳过）——事件频道用；
    - ``parse_json=False``：原始 str/bytes 直接入队 —— 决策频道用（等待方自己解析）。
    """
    pubsub = None
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if not isinstance(message, dict) or message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8", errors="replace")
            if parse_json:
                try:
                    event = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue
                await queue.put(event)
            else:
                await queue.put(data)
    except asyncio.CancelledError:
        raise
    except Exception:
        _logger.exception("redis relay failed: channel=%s", channel)
    finally:
        await close_pubsub(pubsub, channel)
