"""任务队列配置回归（taskiq × Redis Cluster）。

历史背景：队列曾用 arq，而 arq 0.28 的 ArqRedis 是普通 redis 客户端 ——
连 cluster 节点 MOVED、RedisCluster 又拒绝 arq 依赖的事务，导致集群部署下
队列完全不可用（内网实测 30 个 key 有 15 个抛 MovedError）。

已迁到 taskiq（taskiq-redis 提供原生 cluster broker / backend / schedule
source，全单 key 操作）。所以：

- **多节点 URL 不再被拒**，这正是迁移目的；
- ``REDIS_CLUSTER=true`` 或 URL 含逗号 → 选 cluster 版 broker；
- ``ARQ_REDIS_URL``（变量名沿用）优先于 ``REDIS_URL``，用于把队列与业务
  缓存分开指向不同 Redis。
"""
from __future__ import annotations

import pytest

from app.services import task_queue_taskiq as tqt


class _FakeSettings:
    def __init__(self, redis_url="", arq_redis_url="", redis_cluster=False):
        self.redis_url = redis_url
        self.arq_redis_url = arq_redis_url
        self.redis_cluster = redis_cluster


def _patch(monkeypatch, settings: _FakeSettings) -> None:
    # _queue_url / is_cluster 内部都走 get_settings()
    import app.core.config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: settings)


def test_single_node_non_cluster_uses_plain_broker(monkeypatch):
    _patch(monkeypatch, _FakeSettings(redis_url="redis://default:pw@127.0.0.1:6379/0"))
    assert tqt._queue_url() == "redis://default:pw@127.0.0.1:6379/0"
    assert tqt.is_cluster() is False
    from taskiq_redis import RedisStreamBroker

    assert isinstance(tqt.build_broker(), RedisStreamBroker)


def test_multi_node_url_selects_cluster_broker(monkeypatch):
    """多节点 URL 现在被接受，且必须走 cluster 版 broker。"""
    url = "redis://default:pw@172.73.1.87:6379,redis://default:pw@172.73.1.88:6379"
    _patch(monkeypatch, _FakeSettings(redis_url=url))
    assert tqt.is_cluster() is True
    from taskiq_redis import RedisStreamClusterBroker

    assert isinstance(tqt.build_broker(), RedisStreamClusterBroker)


def test_cluster_flag_with_single_node_url_still_uses_cluster_broker(monkeypatch):
    """REDIS_CLUSTER=true 但只填一个节点：那个节点是集群成员，普通客户端
    连上去照样 MOVED，所以必须走 cluster 版。"""
    _patch(
        monkeypatch,
        _FakeSettings(redis_url="redis://default:pw@172.73.1.87:6379/0", redis_cluster=True),
    )
    assert tqt.is_cluster() is True
    from taskiq_redis import RedisStreamClusterBroker

    assert isinstance(tqt.build_broker(), RedisStreamClusterBroker)


def test_arq_redis_url_takes_priority(monkeypatch):
    """ARQ_REDIS_URL 优先，用于队列与业务缓存分开部署。"""
    _patch(
        monkeypatch,
        _FakeSettings(
            redis_url="redis://default:pw@10.0.0.1:6379/0",
            arq_redis_url="redis://default:pw@10.0.0.9:6380/0",
        ),
    )
    assert tqt._queue_url() == "redis://default:pw@10.0.0.9:6380/0"


def test_empty_url_falls_back_to_loopback(monkeypatch):
    _patch(monkeypatch, _FakeSettings())
    assert tqt._queue_url() == "redis://127.0.0.1:6379"


def test_result_backend_matches_mode(monkeypatch):
    from taskiq_redis import (
        RedisAsyncClusterResultBackend,
        RedisAsyncResultBackend,
    )

    _patch(monkeypatch, _FakeSettings(redis_url="redis://127.0.0.1:6379/0"))
    assert isinstance(tqt.build_result_backend(), RedisAsyncResultBackend)

    _patch(monkeypatch, _FakeSettings(redis_url="redis://h1:6379,redis://h2:6379"))
    assert isinstance(tqt.build_result_backend(), RedisAsyncClusterResultBackend)


def test_schedule_source_matches_mode(monkeypatch):
    from taskiq_redis import ListRedisScheduleSource, RedisClusterScheduleSource

    _patch(monkeypatch, _FakeSettings(redis_url="redis://127.0.0.1:6379/0"))
    assert isinstance(tqt.build_schedule_source_for_test(), ListRedisScheduleSource)

    _patch(monkeypatch, _FakeSettings(redis_url="redis://h1:6379,redis://h2:6379"))
    assert isinstance(tqt.build_schedule_source_for_test(), RedisClusterScheduleSource)


# ── 任务注册与对外接口 ────────────────────────────────────────────────


def test_all_tasks_registered():
    """8 个任务都要注册到 broker（迁 taskiq 后不能漏）。"""
    from app.services import task_queue as tq

    expected = {
        "export_pptx_task",
        "compile_document_task",
        "build_website_task",
        "write_audit_log_task",
        "purge_audit_logs_task",
        "scan_knowledge_conflicts_task",
        "refresh_llm_provider_cookies_task",
        "send_annual_wrapped_task",
    }
    assert set(tq._registered.keys()) == expected


def test_public_api_unchanged():
    """调用方（tasks.py / knowledge.py / audit_service.py）依赖这些函数。"""
    from app.services import task_queue as tq

    for name in (
        "submit_ppt_export",
        "submit_document_compilation",
        "submit_website_build",
        "submit_audit_log",
        "get_task_status",
        "close_arq_pool",
    ):
        assert callable(getattr(tq, name)), f"{name} 缺失"


def test_cron_schedules_match_arq_era():
    """cron 频率必须与 arq 时代一致（Cookie 续期漏跑会导致网关 401）。"""
    from app.services.task_queue import CRON_SCHEDULES

    got = dict(CRON_SCHEDULES)
    assert got["purge_audit_logs_task"] == "17 3 * * *"
    assert got["scan_knowledge_conflicts_task"] == "23 4 * * 1"
    assert got["refresh_llm_provider_cookies_task"] == "7,27,47 * * * *"


def test_tasks_registered_under_bare_task_name():
    """5.1 回归：taskiq 0.13 的 task() 首个参数是 task_name。

    写成 name= 会被当作 label 吞掉，任务以模块限定名注册
    （app.services.task_queue:xxx），而 scheduler/生产者发裸名，worker
    find_task(裸名) 查不到 → 所有后台任务静默不执行。
    """
    from app.services import task_queue as tq

    for name in tq._registered:
        task = tq._registered[name]
        assert getattr(task, "task_name", None) == name
        assert ":" not in (getattr(task, "task_name", "") or "")


def test_cluster_connection_kwargs_prevent_xread_timeout():
    """5.2 回归：socket_timeout 必须远大于 xread_block，且参数被 RedisCluster 接受。

    RedisCluster 默认 socket_timeout=5s，而阻塞 xreadgroup 原为 10s ——
    节点稍慢就抛 TimeoutError 把 worker 进程带崩。必须显式放大。
    """
    import inspect

    from redis.asyncio.cluster import RedisCluster

    from app.services.task_queue_taskiq import _connection_kwargs

    kw = _connection_kwargs()
    assert kw["socket_timeout"] >= 60
    assert kw["socket_keepalive"] is True
    accepted = set(inspect.signature(RedisCluster.__init__).parameters)
    assert set(kw) <= accepted, f"RedisCluster 不接受的参数: {set(kw) - accepted}"


def test_cluster_broker_builds_with_socket_timeout(monkeypatch):
    """5.2：集群 broker 用放大的超时构造，且 xread_block < socket_timeout。"""
    from app.services import task_queue_taskiq as t

    monkeypatch.setattr(t, "is_cluster", lambda: True)
    monkeypatch.setattr(
        t, "_queue_url", lambda: "redis://10.0.0.1:6379,redis://10.0.0.2:6379"
    )
    broker = t.build_broker()
    assert broker.block == 5000
    redis_kw = broker.redis.get_connection_kwargs()
    assert redis_kw.get("socket_timeout") == 60.0
    assert redis_kw.get("socket_keepalive") is True


def test_asyncio_imported_in_task_queue():
    """5.4 回归：compile_document_task 用 asyncio.to_thread，顶层必须已导入。"""
    from app.services import task_queue as tq

    assert hasattr(tq, "asyncio")
