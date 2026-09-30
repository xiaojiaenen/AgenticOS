import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

# 在读取 Settings 之前，将 .env 加载到 os.environ
# 这样 wuwei 等直接读 os.environ 的库也能拿到配置
#
# override=False：已存在的环境变量优先于 .env。
#  - 容器/CI 注入的环境变量必须能覆盖 .env 中的开发默认值；
#  - 测试通过 os.environ 注入临时 DATABASE_URL，不能被 .env 覆盖回去。
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file, override=False)

from app.api.router import api_router
from app.core.config import get_settings
from app.core.redis import init_redis, close_redis
from app.db.session import init_db

logger = logging.getLogger(__name__)

settings = get_settings()
# Ensure process env matches Settings so libraries that only read os.environ
# (wuwei LLMGateway, etc.) use the same backend/.env values.
if settings.openai_api_key:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
if settings.openai_base_url:
    os.environ["OPENAI_BASE_URL"] = settings.openai_base_url
if settings.openai_model:
    os.environ["OPENAI_MODEL"] = settings.openai_model
if settings.redis_url:
    os.environ.setdefault("REDIS_URL", settings.redis_url)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        init_db()
    except Exception:
        logger.critical("Database initialization failed. Check DATABASE_URL and disk space.", exc_info=True)
        raise

    # 初始化 Redis（留空则使用内存 fallback）
    await init_redis(settings.redis_url, settings.redis_cluster)

    # 上游 agents.gree.com cookie 续期循环（与 sesame 一致的自动登录流程）
    upstream_refresh_task = None
    if settings.upstream_auto_login_enabled:
        try:
            from app.services.upstream.login_orchestrator import start_cookie_refresh_loop

            upstream_refresh_task = start_cookie_refresh_loop()
            logger.info(
                "Upstream cookie refresh loop started: base=%s interval_min=%s",
                settings.upstream_base_url,
                settings.upstream_cookie_refresh_minutes,
            )
        except Exception:
            logger.exception("Failed to start upstream cookie refresh loop")

    # 从数据库加载历史输入到缓存
    from app.services.cache_service import get_cache_service
    await get_cache_service().load_history_from_db()

    yield

    if upstream_refresh_task is not None:
        upstream_refresh_task.cancel()

    # 关闭 ARQ 连接池与 Redis
    from app.services.task_queue import close_arq_pool
    try:
        await close_arq_pool()
    except Exception:
        logger.warning("Failed to close ARQ pool on shutdown", exc_info=True)
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AgenticOS 的 FastAPI 后端服务。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Resource already exists or conflicts with existing data."},
    )


@app.exception_handler(OperationalError)
async def operational_error_handler(_request: Request, exc: OperationalError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "A database error occurred. Please try again later."},
    )


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    max_size = 32 * 1024 * 1024  # 32 MB
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_size:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large."},
        )
    return await call_next(request)
app.include_router(api_router, prefix=settings.api_v1_prefix)

# OpenAI 兼容上游网关 /v1/*（外部软件用 sk-agenticos-* 调用）
from app.api.gateway_v1 import router as gateway_v1_router

app.include_router(gateway_v1_router)


# 静态文件服务：网站预览
# 挂载 data/websites 和 data/nginx-serve 目录，用于预览已构建的网站
from fastapi.staticfiles import StaticFiles
from app.core.data_path import DATA_DIR

_websites_dir = DATA_DIR / "websites"
_nginx_serve_dir = DATA_DIR / "nginx-serve"

# 确保目录存在
_websites_dir.mkdir(parents=True, exist_ok=True)
_nginx_serve_dir.mkdir(parents=True, exist_ok=True)

# 挂载网站预览服务
# 访问 /sites/{project_slug}/dist/index.html 预览网站
app.mount("/sites", StaticFiles(directory=str(_nginx_serve_dir)), name="sites")
# 访问 /preview/{project_slug}/dist/index.html 预览构建中的网站
app.mount("/preview", StaticFiles(directory=str(_websites_dir)), name="preview")


@app.get("/", tags=["元信息"])
def read_root() -> dict[str, str]:
    return {
        "message": f"{settings.app_name} 服务运行中",
        "docs_url": "/docs",
        "environment": settings.environment,
    }
# Force reload
