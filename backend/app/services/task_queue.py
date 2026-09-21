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

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 任务定义
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    status: str  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None


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
        result = process_document_ingest(document_id, knowledge_base_id)
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
    import subprocess
    from pathlib import Path
    
    logger.info(f"[Worker] Building website: {project_path}")
    
    try:
        project_dir = Path(project_path)
        
        # npm install
        result = subprocess.run(
            ["npm", "install", "--ignore-scripts"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return {"status": "failed", "error": f"npm install failed: {result.stderr}"}
        
        # npm run build
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            return {"status": "failed", "error": f"npm run build failed: {result.stderr}"}
        
        logger.info(f"[Worker] Website built: {project_path}")
        return {"status": "completed", "path": str(project_dir / "dist")}
        
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "Build timed out"}
    except Exception as e:
        logger.error(f"[Worker] Website build failed: {e}")
        return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Worker 配置
# ---------------------------------------------------------------------------


class WorkerSettings:
    """ARQ Worker 配置"""
    
    functions = [
        export_pptx_task,
        compile_document_task,
        build_website_task,
    ]
    
    # Redis 连接
    @classmethod
    def redis_settings(cls) -> RedisSettings:
        settings = get_settings()
        redis_url = settings.redis_url or "redis://localhost:6379"
        
        from urllib.parse import urlparse
        parsed = urlparse(redis_url)
        return RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            database=int(parsed.path.lstrip("/") or 0),
        )
    
    # 并发任务数
    max_jobs = 10
    
    # 任务超时（秒）
    job_timeout = 600
    
    # 健康检查
    health_check_interval = 30


# ---------------------------------------------------------------------------
# 任务提交辅助函数
# ---------------------------------------------------------------------------


async def get_arq_pool():
    """获取 ARQ 连接池"""
    settings = get_settings()
    redis_url = settings.redis_url or "redis://localhost:6379"
    
    from urllib.parse import urlparse
    parsed = urlparse(redis_url)
    redis_settings = RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
    )
    
    return await create_pool(redis_settings)


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
    return job.job_id


async def get_task_status(task_id: str) -> TaskResult:
    """查询任务状态"""
    pool = await get_arq_pool()
    job = await pool.queued_jobs()
    
    # 查找任务
    for j in job:
        if j.job_id == task_id:
            return TaskResult(
                task_id=task_id,
                status="pending",
            )
    
    # 检查正在运行的任务
    running = await pool.incomplete_jobs()
    for j in running:
        if j.job_id == task_id:
            return TaskResult(
                task_id=task_id,
                status="running",
            )
    
    # 检查已完成的任务
    try:
        result = await pool.job_result(task_id)
        if result is not None:
            if result.success:
                return TaskResult(
                    task_id=task_id,
                    status="completed",
                    result=result.result,
                )
            else:
                return TaskResult(
                    task_id=task_id,
                    status="failed",
                    error=str(result.result),
                )
    except Exception:
        pass
    
    return TaskResult(
        task_id=task_id,
        status="unknown",
    )
