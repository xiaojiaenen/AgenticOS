"""
ARQ 任务队列

用于处理重计算任务（PPT 导出、npm build、知识编译等），
避免阻塞 API 事件循环。

启动 worker:
    arq app.services.task_queue.WorkerSettings

提交任务:
    from app.services.task_queue import submit_ppt_export
    task = await submit_ppt_export(artifact_id, ...)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 任务定义
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    status: str  # pending, running, completed, failed, unknown
    result: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# LLM 网关（知识摄入用；本文件内创建，不依赖 agent_service）
# ---------------------------------------------------------------------------


def build_llm_gateway():
    """为知识摄入构建 LLMGateway；无 key / 失败时返回 None 并 warning 降级。"""
    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY 未配置，知识摄入将降级为规则编译（不调用 LLM）")
        return None
    try:
        from wuwei.llm import LLMGateway

        return LLMGateway.from_env(
            max_tokens=settings.agent_max_tokens,
            timeout=settings.llm_timeout,
        )
    except Exception as e:
        logger.warning(f"构建 LLMGateway 失败，知识摄入降级为规则编译: {e}")
        return None


# ---------------------------------------------------------------------------
# 任务函数
# ---------------------------------------------------------------------------


async def export_pptx_task(
    ctx: dict,
    artifact_id: str,
    canvas_format: Optional[str] = None,
    theme: Optional[str] = None,
    use_native_shapes: bool = True,
    use_compat_mode: bool = False,
    transition: Optional[str] = None,
    animation: Optional[str] = None,
    enable_notes: bool = True,
) -> dict:
    """PPTX 导出任务（在 worker 进程中执行）"""
    from app.services.agent_service import get_agent_service

    logger.info(f"[Worker] Exporting PPTX: {artifact_id}")

    try:
        agent_service = get_agent_service()
        pptx_bytes = await agent_service.export_pptx(
            artifact_id,
            canvas_format=canvas_format,
            theme=theme,
            use_native_shapes=use_native_shapes,
            use_compat_mode=use_compat_mode,
            transition=transition,
            animation=animation,
            enable_notes=enable_notes,
        )

        # 保存到文件
        from app.core.data_path import DATA_DIR
        output_path = DATA_DIR / "ppt-output" / f"{artifact_id}.pptx"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pptx_bytes)

        logger.info(f"[Worker] PPTX exported: {output_path}")
        return {"status": "completed", "path": str(output_path)}

    except Exception as e:
        logger.error(f"[Worker] PPTX export failed: {e}")
        return {"status": "failed", "error": str(e)}


async def compile_document_task(
    ctx: dict,
    document_id: int,
    knowledge_base_id: int,
) -> dict:
    """知识库文档编译任务（在 worker 进程中执行）"""
    from app.services.knowledge.ingest_pipeline import process_document_ingest

    logger.info(f"[Worker] Compiling document: {document_id}")

    try:
        llm_gateway = build_llm_gateway()
        result = await asyncio.to_thread(
            process_document_ingest,
            document_id,
            knowledge_base_id,
            llm_gateway,
        )
        logger.info(f"[Worker] Document compiled: {document_id}")
        return result
    except Exception as e:
        logger.error(f"[Worker] Document compilation failed: {e}")
        return {"status": "failed", "error": str(e)}


async def build_website_task(
    ctx: dict,
    project_path: str,
) -> dict:
    """网站构建任务（npm install + npm run build）"""
    import asyncio
    import shutil
    from pathlib import Path

    logger.info(f"[Worker] Building website: {project_path}")

    try:
        project_dir = Path(project_path)

        async def _run_npm(step: str, args: list[str], timeout: int) -> None:
            # Windows 下 npm 实际是 npm.cmd，用 shutil.which 解析出可执行文件
            npm = shutil.which("npm") or "npm"
            proc = await asyncio.create_subprocess_exec(
                npm,
                *args,
                cwd=project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise
            if proc.returncode != 0:
                raise RuntimeError(
                    f"{step} failed: {stderr.decode(errors='replace').strip()}"
                )

        try:
            await _run_npm("npm install", ["install", "--ignore-scripts"], timeout=300)
            await _run_npm("npm run build", ["run", "build"], timeout=180)
        except RuntimeError as e:
            return {"status": "failed", "error": str(e)}

        logger.info(f"[Worker] Website built: {project_path}")
        return {"status": "completed", "path": str(project_dir / "dist")}

    except asyncio.TimeoutError:
        return {"status": "failed", "error": "Build timed out"}
    except Exception as e:
        logger.error(f"[Worker] Website build failed: {e}")
        return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Worker 配置
# ---------------------------------------------------------------------------


def _redis_settings_from_url() -> RedisSettings:
    settings = get_settings()
    # Prefer explicit REDIS_URL; default to IPv4 loopback — Windows `localhost`
    # often resolves to ::1 first and arq/asyncio then times out.
    redis_url = settings.redis_url or "redis://127.0.0.1:6379"
    return RedisSettings.from_dsn(redis_url)


class WorkerSettings:
    """ARQ Worker 配置

    redis_settings 必须是类属性上的 RedisSettings 实例（arq 的 get_kwargs
    从 settings_cls.__dict__ 读取，classmethod 会导致 worker 启动失败）。
    """

    functions = [
        export_pptx_task,
        compile_document_task,
        build_website_task,
    ]

    # Redis 连接（类属性实例，非 classmethod）
    redis_settings: RedisSettings = _redis_settings_from_url()

    # 并发任务数
    max_jobs = 10

    # 任务超时（秒）
    job_timeout = 600

    # 健康检查
    health_check_interval = 30


# ---------------------------------------------------------------------------
# 任务提交辅助函数
# ---------------------------------------------------------------------------


_pool = None
_pool_lock: Optional[asyncio.Lock] = None


def _get_pool_lock() -> asyncio.Lock:
    """懒创建锁：arq worker / app 在不同事件循环中导入本模块，锁须绑定当前 loop。"""
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    return _pool_lock


async def get_arq_pool():
    """获取 ARQ 连接池（模块级缓存复用）；Redis 不可用时抛出连接错误，由调用方映射 503。"""
    global _pool
    if _pool is None:
        async with _get_pool_lock():
            if _pool is None:
                _pool = await create_pool(_redis_settings_from_url())
    return _pool


async def close_arq_pool() -> None:
    """关闭并清空缓存的 ARQ 连接池（供优雅关闭时调用）。"""
    global _pool
    if _pool is None:
        return
    async with _get_pool_lock():
        if _pool is not None:
            try:
                await _pool.aclose()
            except AttributeError:
                await _pool.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("close_arq_pool failed: %s", e)
            finally:
                _pool = None


async def submit_ppt_export(
    artifact_id: str,
    canvas_format: Optional[str] = None,
    theme: Optional[str] = None,
    use_native_shapes: bool = True,
    use_compat_mode: bool = False,
    transition: Optional[str] = None,
    animation: Optional[str] = None,
    enable_notes: bool = True,
) -> str:
    """提交 PPTX 导出任务，返回 task_id"""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "export_pptx_task",
        artifact_id,
        canvas_format=canvas_format,
        theme=theme,
        use_native_shapes=use_native_shapes,
        use_compat_mode=use_compat_mode,
        transition=transition,
        animation=animation,
        enable_notes=enable_notes,
    )
    if job is None:
        raise RuntimeError("enqueue_job returned None (job may already exist)")
    return job.job_id


async def submit_document_compilation(
    document_id: int,
    knowledge_base_id: int,
) -> str:
    """提交文档编译任务，返回 task_id"""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "compile_document_task",
        document_id,
        knowledge_base_id,
    )
    if job is None:
        raise RuntimeError("enqueue_job returned None (job may already exist)")
    return job.job_id


async def submit_website_build(
    project_path: str,
) -> str:
    """提交网站构建任务，返回 task_id"""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "build_website_task",
        project_path,
    )
    if job is None:
        raise RuntimeError("enqueue_job returned None (job may already exist)")
    return job.job_id


async def get_task_status(task_id: str) -> TaskResult:
    """查询任务状态（使用 arq Job API：status / result_info）"""
    pool = await get_arq_pool()
    job = Job(task_id, redis=pool)
    status = await job.status()

    if status in (JobStatus.deferred, JobStatus.queued):
        return TaskResult(task_id=task_id, status="pending")

    if status == JobStatus.in_progress:
        return TaskResult(task_id=task_id, status="running")

    if status == JobStatus.complete:
        info = await job.result_info()
        if info is None:
            return TaskResult(task_id=task_id, status="completed")
        if info.success:
            result = info.result
            if result is not None and not isinstance(result, dict):
                result = {"value": result}
            return TaskResult(task_id=task_id, status="completed", result=result)
        return TaskResult(task_id=task_id, status="failed", error=str(info.result))

    # JobStatus.not_found
    return TaskResult(task_id=task_id, status="unknown")
