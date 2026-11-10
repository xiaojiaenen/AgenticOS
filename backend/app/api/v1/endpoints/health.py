from fastapi import APIRouter

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
