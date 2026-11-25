from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/", summary="健康检查")
async def health_check() -> dict[str, str]:
    """存活探针。

    必须是 ``async def``：写成同步函数时 FastAPI 会把它丢进 anyio 线程池执行，
    而线程池默认只有 40 个 slot。容器线程/进程上限打满（pthread_create
    返回 EAGAIN）时，这个探针会排不到线程、直接超时 —— 表现为容器
    healthcheck 一直 unhealthy，依赖它的前端永远卡在 created。
    这里只返回一个常量，放在事件循环里跑没有任何阻塞风险。
    """
    return {"status": "ok"}


@router.get("/components", summary="依赖级健康探针（DB / Redis / 引擎配置）")
async def health_components() -> dict[str, object]:
    """系统健康页（战线 E-P1 8.5.5）。

    逐项探测并给出 ok/degraded；单点失败不影响整体结构 —— LB 存活探针
    仍用 ``GET /health``（常量），本端点供后台健康页与运维排查。
    """
    import time

    components: dict[str, object] = {}

    # DB
    started = time.monotonic()
    try:
        from sqlalchemy import text

        from app.db.session import create_db_session

        with create_db_session() as db:
            db.execute(text("SELECT 1"))
        components["database"] = {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        components["database"] = {"ok": False, "error": str(exc)[:160]}

    # Redis（内存 fallback 标记 degraded —— 单实例可用但多实例不一致）
    try:
        from app.core.redis import get_redis, is_redis_memory

        redis = get_redis()
        started = time.monotonic()
        await redis.ping()
        components["redis"] = {
            "ok": True,
            "mode": "memory-fallback" if is_redis_memory() else "redis",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "degraded": is_redis_memory(),
        }
    except Exception as exc:  # noqa: BLE001
        components["redis"] = {"ok": False, "error": str(exc)[:160]}

    # 可观测 / 沙箱 / 引擎 当前档位（配置面，不探测）
    from app.services.sandbox import resolve_backend

    settings = get_settings()
    components["config"] = {
        "ok": True,
        "agent_engine": settings.agent_engine,
        "sandbox_backend": resolve_backend(),
        "otel_enabled": settings.otel_enabled,
        "version": settings.app_version,
        "environment": settings.environment,
    }

    # 限流降级 metrics（3.3 P0：Redis 故障静默超发 → 超发指标可观测）
    try:
        from app.services.rate_limiter import get_degrade_stats

        degrade = get_degrade_stats()
        components["rate_limit"] = {
            "ok": sum(degrade.values()) == 0,
            "degraded": sum(degrade.values()) > 0,
            "degrade_counts": degrade,
        }
    except Exception as exc:  # noqa: BLE001
        components["rate_limit"] = {"ok": False, "error": str(exc)[:160]}

    overall_ok = all(
        bool(v.get("ok")) and not v.get("degraded", False)
        for v in components.values()
        if isinstance(v, dict)
    )
    return {"status": "ok" if overall_ok else "degraded", "components": components}
