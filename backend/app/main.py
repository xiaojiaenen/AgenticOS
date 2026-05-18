import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import init_db

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        init_db()
    except Exception:
        logger.critical("Database initialization failed. Check DATABASE_URL and disk space.", exc_info=True)
        raise
    yield


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


@app.get("/", tags=["元信息"])
def read_root() -> dict[str, str]:
    return {
        "message": f"{settings.app_name} 服务运行中",
        "docs_url": "/docs",
        "environment": settings.environment,
    }
