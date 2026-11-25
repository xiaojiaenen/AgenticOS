"""任务队列运维台测试（注册表 / 列表 / 队列深度 / 重试）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services import task_queue as tq


@pytest.fixture
def fake_redis(monkeypatch):
    """进程内存储模拟 Redis 的 hgetall/zrevrange/zadd/xlen。"""
    store: dict = {}
    zsets_: dict = {}

    class _Pipe:
        def __init__(self, redis):
            self._redis = redis
            self._ops = []

        def hset(self, key, mapping=None):
            self._ops.append(("hset", key, mapping))
            return self

        def expire(self, key, ttl):
            self._ops.append(("expire", key, ttl))
            return self

        def zadd(self, key, mapping):
            self._ops.append(("zadd", key, mapping))
            return self

        def zremrangebyrank(self, key, lo, hi):
            self._ops.append(("zrem", key, lo, hi))
            return self

        async def execute(self):
            for op in self._ops:
                if op[0] == "hset":
                    self._redis.hashes.setdefault(op[1], {}).update(op[2])
                elif op[0] == "zadd":
                    self._redis.zsets.setdefault(op[1], {}).update(op[2])
                elif op[0] == "zrem":
                    members = self._redis.zsets.get(op[1], {})
                    ordered = sorted(members.items(), key=lambda kv: kv[1])
                    lo, hi = op[2], op[3]
                    n = len(ordered)
                    start = lo if lo >= 0 else max(n + lo, 0)
                    end = n + hi + 1 if hi < 0 else min(hi + 1, n)
                    for k, _ in ordered[start:end]:
                        members.pop(k, None)

    class _FakeRedis:
        hashes = store
        zsets = zsets_  # noqa: F821 —— 闭包变量

        def pipeline(self, transaction=False):
            return _Pipe(self)

        async def hgetall(self, key):
            return dict(store.get(key, {}))

        async def zrevrange(self, key, lo, hi):
            entries = sorted(zsets_.get(key, {}).items(), key=lambda kv: -kv[1])
            return [k for k, _ in entries[lo : hi + 1 if hi >= 0 else None]]

        async def xlen(self, key):
            return 0

        async def zcard(self, key):
            return len(zsets_.get(key, {}))

    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.core.redis.get_redis", lambda: fake, raising=False
    )
    # 结果 backend 直连 broker Redis —— 单测里统一当作「尚无结果」（pending）
    monkeypatch.setattr(
        "app.services.task_queue_taskiq.get_result_raw",
        AsyncMock(return_value=None),
        raising=False,
    )
    # get_redis 在 task_queue 里是函数内 import，monkeypatch 目标应为 app.core.redis
    return fake


@pytest.mark.asyncio
async def test_record_and_list_task(fake_redis):
    await tq.record_task_submission(
        "task-1", "export_pptx_task", {"artifact_id": "a1"}, user_id=7,
    )
    listing = await tq.list_queue_tasks()
    assert listing["total_indexed"] == 1
    item = listing["items"][0]
    assert item["task_id"] == "task-1"
    assert item["name"] == "export_pptx_task"
    assert item["user_id"] == 7
    assert item["kwargs"] == {"artifact_id": "a1"}
    assert item["status"] in ("pending", "unknown")  # 无 result backend → pending/unknown


@pytest.mark.asyncio
async def test_record_skips_audit_tasks(fake_redis):
    await tq.record_task_submission("t-a", "write_audit_log_task", {"p": 1})
    await tq.record_task_submission("t-b", "export_pptx_task", {})
    listing = await tq.list_queue_tasks()
    names = [t["name"] for t in listing["items"]]
    assert "write_audit_log_task" not in names
    assert "export_pptx_task" in names


@pytest.mark.asyncio
async def test_list_filters(fake_redis):
    await tq.record_task_submission("t1", "export_pptx_task", {}, user_id=1)
    await tq.record_task_submission("t2", "build_website_task", {}, user_id=2)
    by_name = await tq.list_queue_tasks(name_filter="website")
    assert [t["name"] for t in by_name["items"]] == ["build_website_task"]


@pytest.mark.asyncio
async def test_retry_unknown_task(fake_redis):
    with pytest.raises(KeyError):
        await tq.retry_task("no-such-task")


@pytest.mark.asyncio
async def test_retry_resubmits_registered_task(fake_redis, monkeypatch):
    await tq.record_task_submission(
        "origin-1", "export_pptx_task",
        {"artifact_id": "a1", "use_native_shapes": True}, user_id=3,
    )
    # 模拟重投：patch export_pptx.kiq
    sent = {}

    async def _fake_kiq(**kwargs):
        sent.update(kwargs)
        return type("T", (), {"task_id": "new-1"})()

    monkeypatch.setattr(tq.export_pptx, "kiq", _fake_kiq)
    result = await tq.retry_task("origin-1", user_id=9)
    assert result["task_id"] == "new-1"
    assert sent["artifact_id"] == "a1"
    assert "user_id" not in sent, "重投参数不应携带 user_id（归属由调用方登记）"
    # 新任务也被登记
    meta = await tq.get_task_meta("new-1")
    assert meta is not None and meta["name"] == "export_pptx_task"
    assert meta["user_id"] == 9


@pytest.mark.asyncio
async def test_queue_stats_shape(fake_redis):
    await tq.record_task_submission("t1", "export_pptx_task", {})
    stats = await tq.queue_stats()
    assert stats["broker"] == "taskiq"
    assert "queue_depth" in stats
    assert "pending" in stats["recent"] or "unknown" in stats["recent"]


@pytest.mark.asyncio
async def test_index_bounded(fake_redis):
    for i in range(tq.TASK_INDEX_MAX_ENTRIES + 20):
        await tq.record_task_submission(f"t-{i}", "export_pptx_task", {})
    from app.core.redis import get_redis

    redis = get_redis()
    import app.services.task_queue as m

    ids = await redis.zrevrange(m.TASK_INDEX_KEY, 0, -1)
    assert len(ids) <= tq.TASK_INDEX_MAX_ENTRIES
