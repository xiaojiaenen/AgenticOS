"""会话产物的持久化队列（A2UI 界面消息 / 图表消息）。

为什么要存在：这两个通道原来是**进程内 dict**，工具把消息塞进去，
run 结束才挂到 assistant 消息的 metadata 落库。中间任何一次进程重启
（发版、OOM、崩溃）都会把还没落库的界面/图表**整轮丢掉**——用户刷新
后只剩一段干巴巴的文本；图表的 ``_emitted`` 游标丢了还会把同一张图
重复下发、重复落库。

现在：Redis（AOF + 数据卷持久化）作为事实源，工具 push 时**立即**
写入；读侧照旧。Redis 不可用（未配置 / 内存 fallback）时退回原来的
进程内 dict —— 单测与本地开发行为不变。

Key 约定：
- ``sart:{kind}:{sid}``       LIST，每条消息一个 JSON 元素（RPUSH 原子追加，
                              并发工具同时 push 不丢）
- ``sart:{kind}:emi:{sid}``   INT，已下发游标（仅 chart 用）
- TTL 7 天：正常流程 run 结束即 clear；TTL 只防泄漏
"""

from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger("session_artifacts")

_TTL_SECONDS = 7 * 24 * 3600

# 进程内 fallback（Redis 不可用时的事实源）
_mem_lists: dict[str, dict[str, list[dict[str, Any]]]] = {"a2ui": {}, "chart": {}}
_mem_emitted: dict[str, dict[str, int]] = {"a2ui": {}, "chart": {}}

KINDS = ("a2ui", "chart")


def _key(kind: str, session_id: str) -> str:
    return f"sart:{kind}:{session_id}"


def _emi_key(kind: str, session_id: str) -> str:
    return f"sart:{kind}:emi:{session_id}"


_sync_client = None


def _redis():
    """同步 Redis 客户端；不可用返回 None（调用方走内存 fallback）。

    注意用同步客户端：push/accumulate 是工具线程里的**同步函数**，
    拿不到事件循环。

    刻意**不依赖** redis manager 的 is_memory 状态：manager 只在 app
    lifespan 里初始化，独立脚本/worker/初始化顺序里它都是"未连接"，
    依赖它会让持久化静默降级成内存（真发生过）。这里直连 URL + ping，
    失败才回退。
    """
    global _sync_client
    try:
        from app.core.config import get_settings

        url = get_settings().redis_url
        if not url:
            return None
        if _sync_client is None:
            import redis

            _sync_client = redis.from_url(url, decode_responses=True, socket_timeout=5)
        _sync_client.ping()
        return _sync_client
    except Exception:  # noqa: BLE001
        return None


def append(kind: str, session_id: str, messages: list[dict[str, Any]]) -> None:
    """把若干条消息追加到该会话该通道。即时持久化（Redis 路径）。"""
    if kind not in KINDS or not session_id or not messages:
        return
    client = _redis()
    if client is None:
        bucket = _mem_lists[kind].setdefault(session_id, [])
        bucket.extend(messages)
        return
    try:
        pipe = client.pipeline()
        for message in messages:
            pipe.rpush(_key(kind, session_id), json.dumps(message, ensure_ascii=False, default=str))
        pipe.expire(_key(kind, session_id), _TTL_SECONDS)
        pipe.execute()
    except Exception:  # noqa: BLE001 -- 持久化失败退内存，工具不能炸
        _logger.warning("session_artifacts append failed (kind=%s sid=%s)", kind, session_id[:12], exc_info=True)
        bucket = _mem_lists[kind].setdefault(session_id, [])
        bucket.extend(messages)


def read_all(kind: str, session_id: str) -> list[dict[str, Any]]:
    """读该会话该通道的全部消息（run 结束挂 metadata / 下发 SSE 用）。"""
    if kind not in KINDS or not session_id:
        return []
    client = _redis()
    if client is None:
        return list(_mem_lists[kind].get(session_id) or [])
    try:
        raw = client.lrange(_key(kind, session_id), 0, -1)
        out: list[dict[str, Any]] = []
        for item in raw:
            try:
                out.append(json.loads(item))
            except (TypeError, json.JSONDecodeError):
                continue
        return out
    except Exception:  # noqa: BLE001
        _logger.warning("session_artifacts read_all failed (kind=%s)", kind, exc_info=True)
        return list(_mem_lists[kind].get(session_id) or [])


def get_emitted(kind: str, session_id: str) -> int:
    """已下发游标（防同一张图重复发事件/重复落库）。"""
    if kind not in KINDS or not session_id:
        return 0
    client = _redis()
    if client is None:
        return _mem_emitted[kind].get(session_id, 0)
    try:
        value = client.get(_emi_key(kind, session_id))
        return int(value or 0)
    except Exception:  # noqa: BLE001
        return _mem_emitted[kind].get(session_id, 0)


def set_emitted(kind: str, session_id: str, count: int) -> None:
    if kind not in KINDS or not session_id:
        return
    client = _redis()
    if client is None:
        _mem_emitted[kind][session_id] = count
        return
    try:
        client.set(_emi_key(kind, session_id), int(count), ex=_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        _mem_emitted[kind][session_id] = count


def clear(kind: str, session_id: str) -> None:
    """run 结束落库后清空（列表 + 游标）。"""
    if kind not in KINDS or not session_id:
        return
    client = _redis()
    if client is None:
        _mem_lists[kind].pop(session_id, None)
        _mem_emitted[kind].pop(session_id, None)
        return
    try:
        client.delete(_key(kind, session_id), _emi_key(kind, session_id))
    except Exception:  # noqa: BLE001
        _logger.warning("session_artifacts clear failed (kind=%s)", kind, exc_info=True)
    _mem_lists[kind].pop(session_id, None)
    _mem_emitted[kind].pop(session_id, None)
