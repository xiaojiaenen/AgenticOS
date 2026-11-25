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

import logging
from typing import Any

_logger = logging.getLogger("redis")


def parse_cluster_nodes(url: str) -> tuple[list[tuple[str, int]], str | None, str | None]:
    """解析逗号分隔的多节点 URL: redis://user:pass@host1:6379,...

    模块级函数：manager 之外自建客户端的模块（session_artifacts 等）也要
    支持 cluster，不能各自再抄一份解析。

    Returns:
        (nodes, username, password)
    """
    from urllib.parse import unquote, urlparse

    nodes: list[tuple[str, int]] = []
    password = None
    username = None
    for item in url.split(","):
        item = item.strip()
        if not item:
            continue
        parsed = urlparse(item)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        if parsed.password and not password:
            password = unquote(parsed.password)
        if parsed.username and not username:
            username = unquote(parsed.username)
        nodes.append((host, port))
    return nodes, username, password


class MemoryRedis:
    """内存 Redis fallback —— **fakeredis 实现**（战线 B3 自研归位）。

    原先这里是一份 280 行的手写模拟（string/set/zset/hash/list/pubsub 各写
    一套），语义漂移要自己兜：``SET nx`` 是踩过坑补的、``zrangebylex`` 是
    按项目需要魔改的前缀匹配、pubsub 直接返回 asyncio.Queue（与真实客户端
    API 不兼容，迫使 redis_relay.py 绕道）。

    现在直接换成 **fakeredis**（BSD-3，redis-py 的 drop-in 替身）：真实
    Redis 的命令语义/pubsub/过期/TTL 全部保真，自研字典全部删除。仅用于
    开发/测试 fallback —— 生产必须配真实 Redis（多实例下内存态会静默退化，
    见 init() 里的强告警）。
    """

    def __init__(self) -> None:
        from fakeredis import FakeAsyncRedis

        # decode_responses=True 与 RedisManager 外部模式的真实客户端保持一致
        self._client = FakeAsyncRedis(decode_responses=True)

    def __getattr__(self, name: str):  # 代理全部 Redis 命令
        return getattr(self._client, name)

    async def ping(self) -> bool:
        return await self._client.ping()

    async def close(self) -> None:
        try:
            aclose = getattr(self._client, "aclose", None)
            if callable(aclose):
                await aclose()
            else:
                await self._client.close()
        except Exception:  # noqa: BLE001 —— 关闭失败无需上抛
            pass


class RedisManager:
    """Redis 连接管理器，支持单机/集群/内存 fallback。"""

    def __init__(self) -> None:
        self._client = None
        self._is_memory = True
        self._url = ""
        self._cluster = False

    def parse_cluster_nodes(self) -> tuple[list[tuple[str, int]], str | None, str | None]:
        """解析逗号分隔的多节点 URL: redis://user:pass@host1:6379,...

        Returns:
            (nodes, username, password)
        """
        return parse_cluster_nodes(self._url)

    async def init(self, redis_url: str = "", cluster: bool = False) -> None:
        self._url = redis_url
        self._cluster = cluster
        if not redis_url:
            self._client = MemoryRedis()
            self._is_memory = True
            if _is_production_env():
                # 战线横切 P0（系统改造总方案 9.4）：生产禁止静默内存 fallback。
                # 多实例部署下缓存/限流/审批广播/任务派发全部退化为进程内状态
                # ——这不是"降级可用"，是数据不一致。CRITICAL 级别保证在结构化
                # 日志/告警管道里一定被看到。
                _logger.critical(
                    "【配置错误】生产环境未配置 REDIS_URL，正在使用进程内存 fallback："
                    "缓存、限流、审批 pub/sub、任务队列都会退化为单进程状态，"
                    "多实例部署必然不一致。请立即配置 REDIS_URL 并重启。"
                    "（若确属单机开发/演示部署，请把 ENVIRONMENT 设为 development 消除本告警）"
                )
            else:
                _logger.info("REDIS_URL 未配置，使用内存 fallback（fakeredis）")
            return

        try:
            import redis.asyncio as aioredis

            if cluster:
                from redis.asyncio.cluster import ClusterNode, RedisCluster

                nodes, username, password = self.parse_cluster_nodes()
                if not nodes:
                    raise ValueError(
                        "REDIS_CLUSTER=true 但 REDIS_URL 里解析不出任何节点。"
                        "集群模式的 URL 必须是逗号分隔的多节点，"
                        "例如 redis://user:pass@host1:6379,redis://user:pass@host2:6379"
                        "（不要带 /0 之类的 db 路径）"
                    )
                kwargs = {"startup_nodes": [ClusterNode(host, port) for host, port in nodes], "password": password, "decode_responses": True}
                if username:
                    kwargs["username"] = username
                self._client = RedisCluster(**kwargs)
                _logger.info(f"Redis 集群模式: {len(nodes)} 个节点, 用户名: {username or '(无)'}")
            else:
                self._client = aioredis.from_url(redis_url, decode_responses=True)
                _logger.info(f"Redis 单机模式: {redis_url}")

            await self._client.ping()
            self._is_memory = False
            _logger.info("Redis 连接成功")
        except (AttributeError, TypeError, NameError, ImportError):
            # 编程错误（方法名写错、签名不符、缺依赖）绝不能被当成"连不上"
            # 然后静默 fallback —— 集群模式曾因 `self._parse_cluster_nodes()`
            # 与实际定义 `parse_cluster_nodes` 差一个下划线，永远连不上，
            # 而日志只说"连接失败"，排查方向全被带偏到网络和密码上。
            # 这类错误直接抛出去，让启动失败、问题立刻暴露。
            _logger.error("Redis 初始化代码错误，不是网络问题", exc_info=True)
            raise
        except Exception as e:
            # 真正的连接类错误（DNS、拒绝连接、认证失败、集群不可用）才 fallback。
            # 内存 fallback 是单机/开发可接受，多实例部署时功能会残缺（缓存、
            # 限流、任务派发都退化成进程内状态），因此日志要显眼。
            level = _logger.critical if _is_production_env() else _logger.warning
            level(
                "Redis 连接失败: %s，fallback 到内存 —— "
                "多实例部署下缓存/限流/任务派发会退化为进程内状态，请尽快修复",
                e,
            )
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

    @property
    def url(self) -> str:
        return self._url

    @property
    def cluster(self) -> bool:
        return self._cluster

    async def close(self) -> None:
        if self._client and not self._is_memory:
            # redis-py 5.x 起 close() 已废弃，要用 aclose()；两者在旧版等价。
            # 直接调 close() 会打 DeprecationWarning，测试输出被噪声占满。
            aclose = getattr(self._client, "aclose", None)
            if callable(aclose):
                await aclose()
            else:  # pragma: no cover —— 兼容更老的 redis 客户端
                await self._client.close()


# 全局单例
_manager = RedisManager()


async def init_redis(redis_url: str = "", cluster: bool = False) -> None:
    """初始化 Redis 连接"""
    await _manager.init(redis_url, cluster)


def get_redis():
    """获取 Redis 客户端（开发环境返回内存 fallback）"""
    return _manager.client


# 同步客户端懒加载缓存（限流等同步上下文使用）
_sync_client = None
_sync_client_checked = False


def get_redis_sync():
    """获取同步 Redis 客户端，供同步上下文（如线程池中的登录限流）使用。

    - 未配置 REDIS_URL 或异步管理器处于内存 fallback 时返回 None，
      调用方应使用进程内 fallback（见 app/services/rate_limiter.py）；
    - 已配置 Redis 时懒创建并缓存同步客户端（单机/集群同 URL 配置），
      连接失败返回 None 并告警。
    """
    global _sync_client, _sync_client_checked
    if _manager.is_memory or not _manager.url:
        return None
    if _sync_client_checked:
        return _sync_client
    _sync_client_checked = True
    try:
        import redis

        if _manager.cluster:
            from redis.cluster import RedisCluster

            nodes, username, password = _manager.parse_cluster_nodes()
            kwargs: dict[str, Any] = {
                "startup_nodes": [redis.cluster.ClusterNode(host, port) for host, port in nodes],
                "password": password,
                "decode_responses": True,
            }
            if username:
                kwargs["username"] = username
            _sync_client = RedisCluster(**kwargs)
        else:
            _sync_client = redis.Redis.from_url(_manager.url, decode_responses=True)
        assert _sync_client is not None
        _sync_client.ping()
        _logger.info("Redis 同步客户端连接成功")
    except Exception as e:
        _logger.warning(f"Redis 同步客户端连接失败: {e}，限流将使用进程内 fallback")
        _sync_client = None
    return _sync_client


def mark_sync_client_unusable() -> None:
    """标记同步客户端失效（连接中断等），下次 get_redis_sync() 重建。"""
    global _sync_client, _sync_client_checked
    _sync_client = None
    _sync_client_checked = False


def is_redis_memory() -> bool:
    """是否使用内存 fallback"""
    return _manager.is_memory


def _is_production_env() -> bool:
    """当前是否生产环境（横切 P0：生产禁静默内存 fallback，见 init()）。"""
    try:
        from app.core.config import get_settings

        return (get_settings().environment or "").lower() in {"production", "prod"}
    except Exception:  # noqa: BLE001 —— 配置未就绪时按非生产处理（开发期行为不变）
        return False


async def close_redis() -> None:
    """关闭 Redis 连接"""
    await _manager.close()
