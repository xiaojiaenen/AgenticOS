"""taskiq 队列适配层：在 arq 语义之上包一层 taskiq。

## 为什么迁到 taskiq

arq 0.28 的 ``ArqRedis`` 是普通 ``redis.asyncio.Redis``，且消费端重度依赖
``pipeline(transaction=True)`` 认领任务。而：

- 普通客户端连 Redis Cluster 节点 → key 不归该节点管就 ``MOVED``；
- ``RedisCluster.pipeline(transaction=True)`` 在 redis-py 里**无条件抛异常**
  （"transaction is deprecated in cluster mode"），与 key 是否同槽无关；
- 所以 arq 在集群上无解，不是配置问题。

taskiq-redis 提供原生 cluster 类，实现上**完全不用事务**：

| 类 | 命令 | cluster 安全 |
|---|---|---|
| ``RedisStreamClusterBroker`` | ``xadd`` / ``xreadgroup`` / ``xack`` | 单流，带 ACK |
| ``RedisAsyncClusterResultBackend`` | ``get`` / ``set`` | 单 key |
| ``RedisClusterScheduleSource`` | ``scan_iter`` / ``get`` | scan 跨节点 |

已在内网 6 节点集群（3 主 3 从）实测通过；同一集群上复现了 arq 的做法
30 个 key 有 15 个抛 ``MovedError``。

## 选型

用 ``RedisStreamClusterBroker``（消费组 + ACK），不用 ``ListQueueClusterBroker``：
PPT 导出 / 网站构建是长任务，worker 中途崩溃时只有 stream 的 ACK 机制能保证
任务被重新投递；list 的 ``brpop`` 一旦取走消息，进程死掉就永久丢失。

## 兼容性

对外仍暴露原来的 ``submit_*`` / ``get_task_status`` / ``TaskResult``，
调用方（``api/v1/endpoints/tasks.py`` 等）一行都不用改。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from taskiq import TaskiqMiddleware

logger = logging.getLogger(__name__)

#: 队列名。taskiq 所有 key 都基于它，单 key 操作所以无需 hash tag。
QUEUE_NAME = "agenticos"


def _queue_url() -> str:
    """队列 Redis 端点。

    优先级：``ARQ_REDIS_URL``（沿用旧变量名，避免运维改两套配置）→ ``REDIS_URL``。
    taskiq 原生支持 cluster，所以**不再拒绝多节点 URL** —— 这正是迁移目的。
    """
    from app.core.config import get_settings

    settings = get_settings()
    url = (settings.arq_redis_url or "").strip() or (settings.redis_url or "").strip()
    if not url:
        url = "redis://127.0.0.1:6379"
    return url


def is_cluster() -> bool:
    """是否使用集群版 broker。

    两种都算集群：
    - URL 是多节点（逗号分隔）—— 标准集群写法；
    - 显式 ``REDIS_CLUSTER=true`` —— 即使只填了一个节点地址，那个节点也是
      集群成员，普通客户端连上去照样 MOVED，必须用 cluster 版。
    """
    if "," in _queue_url():
        return True
    from app.core.config import get_settings

    return bool(get_settings().redis_cluster)


def _connection_kwargs() -> dict[str, Any]:
    """底层 Redis 连接的超时/保活参数（broker/结果后端/schedule 共用）。

    内网 6 节点集群上 taskiq 的阻塞 ``xreadgroup`` 期间偶发节点响应慢，
    若 socket 读超时短于 block 时长会抛 ``TimeoutError`` 直接把 worker 带崩
    （72h 重启 9000+ 次）。这里把 socket_timeout 设为远大于 xread_block，
    并开 keepalive + retry_on_timeout，让瞬时慢节点重试而非杀进程。
    """
    return {
        "socket_timeout": 60.0,        # 远大于 xread_block（5s），阻塞读不会误触超时
        "socket_connect_timeout": 10.0,
        "socket_keepalive": True,
        "health_check_interval": 30,
    }


_broker = None
_result_backend = None
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """懒创建锁：worker / app 在不同事件循环中导入，锁须绑定当前 loop。"""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _install_cluster_url_patch() -> None:
    """让 ``RedisCluster.from_url`` 支持逗号分隔的多节点 URL。

    taskiq-redis 的 cluster 类只接受一个 ``url`` 并直接
    ``RedisCluster.from_url(url)``，而 redis-py 的 ``from_url`` 走 ``urlparse``
    —— 多节点 URL（``redis://h1:6379,redis://h2:6379``）会把
    ``6379,redis:`` 当成端口，报 ``Port could not be cast to integer``。

    这里包一层：检测到逗号就自己解析出 ``startup_nodes`` 再构造，
    其余情况原样交给 redis-py。幂等，重复调用安全。
    """
    from redis.asyncio.cluster import ClusterNode, RedisCluster

    if getattr(RedisCluster.from_url, "_agenticos_patched", False):
        return

    _orig = RedisCluster.from_url.__func__

    def _from_url(cls, url: str, **kwargs: Any):
        if isinstance(url, str) and "," in url:
            from app.core.redis import parse_cluster_nodes

            nodes, username, password = parse_cluster_nodes(url)
            if not nodes:
                raise ValueError(f"无法从多节点 URL 解析出集群节点: {url!r}")
            kwargs.setdefault("startup_nodes", [ClusterNode(h, p) for h, p in nodes])
            if password:
                kwargs.setdefault("password", password)
            if username:
                kwargs.setdefault("username", username)
            return cls(**kwargs)
        return _orig(cls, url, **kwargs)

    _from_url._agenticos_patched = True  # type: ignore[attr-defined]
    RedisCluster.from_url = classmethod(_from_url)


def build_broker():
    """按 URL 形态选 broker：集群用 cluster 版，单机用普通版。"""
    url = _queue_url()
    if is_cluster():
        _install_cluster_url_patch()
        from taskiq_redis import RedisStreamClusterBroker

        # xread_block 5s：阻塞窗口远小于 socket_timeout(60s)，慢节点不会拖垮进程。
        return RedisStreamClusterBroker(
            url=url,
            queue_name=QUEUE_NAME,
            consumer_group_name="agenticos",
            xread_block=5000,
            **_connection_kwargs(),
        )

    from taskiq_redis import RedisStreamBroker

    return RedisStreamBroker(
        url=url,
        queue_name=QUEUE_NAME,
        consumer_group_name="agenticos",
        **_connection_kwargs(),
    )


def build_result_backend():
    url = _queue_url()
    if is_cluster():
        _install_cluster_url_patch()
        from taskiq_redis import RedisAsyncClusterResultBackend

        return RedisAsyncClusterResultBackend(
            redis_url=url, keep_results=True, **_connection_kwargs()
        )

    from taskiq_redis import RedisAsyncResultBackend

    return RedisAsyncResultBackend(redis_url=url, keep_results=True, **_connection_kwargs())


def build_schedule_source(prefix: str = "agenticos:schedule"):
    """定时任务的 schedule source。

    集群用 ``RedisClusterScheduleSource``（内部 ``scan_iter`` 由 redis-py
    跨节点处理，其余全是单 key），单机用 ``ListRedisScheduleSource``。
    """
    url = _queue_url()
    if is_cluster():
        _install_cluster_url_patch()
        from taskiq_redis import RedisClusterScheduleSource

        return RedisClusterScheduleSource(url=url, prefix=prefix, **_connection_kwargs())

    from taskiq_redis import ListRedisScheduleSource

    return ListRedisScheduleSource(url=url, prefix=prefix, **_connection_kwargs())


#: 测试用别名（语义更明确）
build_schedule_source_for_test = build_schedule_source


def build_broker_with_backend():
    """构造 broker 并挂上结果后端（taskiq 标准做法）。

    任务通过 ``@broker.task`` 注册，投递用 ``task.kiq(...)``，结果由
    ``result_backend.get_result`` 读。这样 ACK、重投、结果存储全部由
    taskiq 自己处理，不用手写消费循环。
    """
    broker = build_broker()
    broker.with_result_backend(build_result_backend())
    return broker


class AgenticosWorkerMiddleware(TaskiqMiddleware):
    """worker 生命周期钩子。

    worker 不走 backend 的 FastAPI lifespan，需要单独初始化「每个进程一份」
    的全局状态：

    - **Redis manager**：不初始化的话 manager 永远是内存 fallback / 未设置
      cluster 标志，worker 里所有 ``get_redis*()`` 都会连错（cluster 部署下
      ``llm_gate`` 等直接 MOVED，真出过事故）。
    - **外部厂商预设**：PPT 导出等任务在 worker 里跑，预设没加载时 worker
      解析 provider 拿不到 base_url / 模型名。

    taskiq 0.13 的 broker 没有 ``add_startup_hook``，只有 middleware 的
    ``startup`` / ``shutdown`` —— 所以用 middleware 承载。
    """

    async def startup(self) -> None:
        _log = logging.getLogger("agenticos.worker")

        from app.core.config import get_settings
        from app.core.redis import init_redis

        settings = get_settings()
        try:
            await init_redis(settings.redis_url, settings.redis_cluster)
        except Exception:  # noqa: BLE001 -- init 内部已对连接错误做内存降级
            _log.exception("worker Redis 初始化失败（部分功能降级）")

        try:
            from app.services.llm_providers.presets import load_external_presets

            loaded = load_external_presets()
            if loaded:
                _log.info("外部厂商预设已加载：%s", ", ".join(loaded))
        except Exception:
            _log.exception("Failed to load external provider presets")

    async def shutdown(self) -> None:
        from app.core.redis import close_redis

        try:
            await close_redis()
        except Exception:  # noqa: BLE001
            logging.getLogger("agenticos.worker").warning("关闭 Redis 失败", exc_info=True)


async def get_broker():
    """获取并启动 broker（单例）。"""
    global _broker
    if _broker is None:
        async with _get_lock():
            if _broker is None:
                broker = build_broker_with_backend()
                await broker.startup()
                _broker = broker
    return _broker


async def close_broker() -> None:
    """关闭 broker（优雅退出）。"""
    global _broker
    if _broker is None:
        return
    try:
        await _broker.shutdown()
    except Exception:  # noqa: BLE001
        logger.warning("关闭 taskiq broker 失败", exc_info=True)
    finally:
        _broker = None


async def get_result_raw(task_id: str):
    """读取任务结果（不阻塞）。未完成 / 不存在返回 None。

    taskiq 的 ``AsyncResultBackend.get_result`` 在「还没结果」时抛
    ``ResultIsReadyError``（或各实现自己的异常），这里统一吞掉转成 None，
    让调用方只关心「有 / 没有」。
    """
    broker = await get_broker()
    backend = getattr(broker, "result_backend", None)
    if backend is None:
        return None
    try:
        return await backend.get_result(task_id, with_logs=False)
    except Exception:  # noqa: BLE001 -- 未完成时异常类型随实现而异
        return None


__all__ = [
    "QUEUE_NAME",
    "build_broker",
    "build_broker_with_backend",
    "build_result_backend",
    "build_schedule_source",
    "close_broker",
    "get_broker",
    "get_result_raw",
    "is_cluster",
]
