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
from types import SimpleNamespace
from typing import Any, Optional

from arq import create_pool
from arq.connections import RedisSettings
from arq.cron import cron
from arq.jobs import Job, JobStatus

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# worker 进程拿不到请求上下文，任务归属只能随任务一起投递；
# 查询状态时靠这个 key 做归属校验，避免凭 task_id 读到他人工件路径。
TASK_OWNER_KEY = "agenticos:task:owner:{task_id}"
TASK_OWNER_TTL_SECONDS = 24 * 60 * 60


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
    """为知识摄入构建 LLMGateway；不可用时返回 None 并 warning 降级。

    走统一的 ``build_llm_optional``，不再自己判断 ``OPENAI_API_KEY`` ——
    那个判断本身就把「管理员配了企业网关」的部署挡在门外了：没有
    ``OPENAI_API_KEY`` 但有可用提供商时，旧实现会直接降级成规则编译。
    """
    from app.services.llm_factory import build_llm_optional

    return build_llm_optional(role="fast", purpose="知识摄入")


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
    user_id: Optional[int] = None,
) -> dict:
    """PPTX 导出任务（在 worker 进程中执行）"""
    from app.services.agent_service import get_agent_service

    logger.info(f"[Worker] Exporting PPTX: {artifact_id}")

    try:
        # 归属校验：worker 没有请求上下文，用投递时带过来的 user_id 还原最小身份
        current_user = None
        if user_id is not None:
            from app.db.models import UserModel
            from app.db.session import create_db_session

            def _load_owner():
                with create_db_session() as db:
                    row = db.get(UserModel, user_id)
                    if row is None or not row.is_active:
                        return None
                    # 只带出校验所需字段，避免 ORM 对象在 session 关闭后失效
                    return SimpleNamespace(id=row.id, role=row.role)

            current_user = _load_owner()
            if current_user is None:
                return {"status": "failed", "error": "任务发起用户不存在或已停用"}

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
            current_user=current_user,
        )

        # 保存到文件
        from app.core.data_path import DATA_DIR
        output_path = DATA_DIR / "ppt-output" / f"{artifact_id}.pptx"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pptx_bytes)

        logger.info(f"[Worker] PPTX exported: {output_path}")
        return {"status": "completed", "path": str(output_path)}

    except PermissionError as e:
        # 归属校验失败：不把内部细节回传给调用方
        logger.warning(f"[Worker] PPTX export denied: {e}")
        return {"status": "failed", "error": "无权导出该 PPT 产物"}
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


async def write_audit_log_task(ctx: dict, payload: dict) -> dict:
    """审计日志落库任务（M6-C）。

    由 ``audit_service.record_async`` 入队；队列不可用时端点会回落到同步写，
    所以这里只负责把 payload 写进 audit_logs 表。
    """
    from app.db.session import create_db_session
    from app.services.audit_service import record

    detail = payload.pop("detail", None) or {}
    with create_db_session() as session:
        record(
            session,
            action=payload.get("action", "unknown"),
            actor_id=payload.get("actor_id"),
            actor_email=payload.get("actor_email"),
            resource_type=payload.get("resource_type"),
            resource_id=payload.get("resource_id"),
            result=payload.get("result", "allow"),
            ip=payload.get("ip"),
            user_agent=payload.get("user_agent"),
            detail=detail,
        )
    return {"status": "completed"}


async def purge_audit_logs_task(ctx: dict) -> dict:
    """审计保留期清理（默认 180 天），由 arq cron 每日触发。"""
    from app.db.session import create_db_session
    from app.services.audit_service import RETENTION_DAYS, purge_older_than

    with create_db_session() as session:
        deleted = purge_older_than(session, RETENTION_DAYS)
    logger.info("[Worker] Purged %d audit logs older than %d days", deleted, RETENTION_DAYS)
    return {"status": "completed", "deleted": deleted}


async def scan_knowledge_conflicts_task(ctx: dict, knowledge_base_id: int | None = None) -> dict:
    """知识库冲突巡检（cron 每周全库跑一次，也可按库手动触发）。

    编译期的冲突检测只比对「新页 vs 旧页」，两批历史导入或分次上传的页面
    之间的矛盾会永久漏掉。本任务对整个库做跨页配对扫描，把新发现写进
    复核队列（``kb_review_items``），**不改动任何正文**。
    """
    from app.db.session import create_db_session
    from app.services.knowledge.conflict_scanner import (
        scan_all_knowledge_bases,
        scan_knowledge_base,
    )

    with create_db_session() as session:
        if knowledge_base_id is None:
            stats = scan_all_knowledge_bases(session)
        else:
            stats = scan_knowledge_base(session, knowledge_base_id)
        session.commit()

    logger.info(
        "[Worker] Knowledge conflict scan done: %s", {k: v for k, v in stats.items() if k != "per_kb"}
    )
    return {"status": "completed", **stats}


async def refresh_llm_provider_cookies_task(ctx: dict) -> dict:
    """企业网关提供商的 Cookie 续期。

    只在「即将过期」时才重新登录，不无脑刷新：每次登录都要起一次无头
    浏览器，无脑刷既浪费资源，也会在上游留下大量登录记录。

    实现上有两个必须遵守的点：

    - **先取目标列表，再逐个 await**。不能在持有 session 的情况下 await
      登录（一次几十秒），那会把连接占死；
    - 登录失败只记录，不抛异常。定时任务因为单个提供商崩掉，会让其他
      提供商也失去续期机会。
    """
    from sqlalchemy import select

    from app.db.models import LlmProviderModel
    from app.db.session import create_db_session
    from app.services.llm_providers import auto_login, credentials

    # 按「账号」而不是「提供商」遍历：一个池里通常只有一个号过期，
    # 整池重登会把其它号当前有效的登录态白白作废。
    candidates = credentials.list_refresh_candidates()
    with create_db_session() as session:
        name_map = {
            row.id: row.name
            for row in session.scalars(
                select(LlmProviderModel).where(LlmProviderModel.enabled.is_(True))
            ).all()
        }

    refreshed: list[str] = []
    skipped: list[str] = []
    failed: list[dict] = []

    for provider_id, credential_id in candidates:
        name = name_map.get(provider_id)
        if not name:
            # 提供商已停用：账号还留着，但不该继续消耗登录动作
            skipped.append(f"provider#{provider_id}-account#{credential_id}")
            continue
        label = f"{name}#{credential_id}"
        try:
            result = await auto_login.login_and_store(provider_id, credential_id)
            if result.success:
                refreshed.append(label)
            else:
                failed.append({"provider": label, "error": result.message[:200]})
        except Exception as exc:  # noqa: BLE001 —— 单个账号失败不影响其余
            logger.warning("[Worker] LLM provider cookie refresh failed %s: %s", label, exc)
            failed.append({"provider": label, "error": str(exc)[:200]})

    logger.info(
        "[Worker] LLM provider cookie refresh: refreshed=%d skipped=%d failed=%d",
        len(refreshed), len(skipped), len(failed),
    )
    return {
        "status": "completed",
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
    }


async def build_website_task(
    ctx: dict,
    project_path: str,
) -> dict:
    """网站构建任务（npm install + npm run build）"""
    import asyncio
    import shutil
    from pathlib import Path

    logger.info(f"[Worker] Building website: {project_path}")

    # 前置检查：worker 镜像里没有 npm 时，返回可读原因而不是一句
    # `npm install failed: sh: npm: not found`（退出码 127）。
    if shutil.which("npm") is None:
        return {
            "status": "failed",
            "error": (
                "构建环境缺少 npm：worker 容器内未安装 Node.js/npm。"
                "请重建运行时镜像（deploy/Dockerfile.runtime 已加入 nodejs + npm）"
                "并重启 worker；这不是项目代码的问题。"
            ),
        }

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
        write_audit_log_task,
        purge_audit_logs_task,
        scan_knowledge_conflicts_task,
        refresh_llm_provider_cookies_task,
    ]

    # 定时任务
    # - 审计保留期清理：每天 03:17
    # - 知识库冲突巡检：每周一 04:23（全库扫描比单次编译贵，日频过密；
    #   选周一凌晨是因为周末通常没人上传文档，扫的是最稳定的语料）
    # - 企业网关 Cookie 续期：每小时 07/27/47 分。比过期缓冲（默认 2h）
    #   密得多，保证「快过期」能被及时发现，而不是卡在缓冲窗口边缘
    cron_jobs = [
        cron(purge_audit_logs_task, hour={3}, minute={17}),
        cron(scan_knowledge_conflicts_task, weekday={0}, hour={4}, minute={23}),
        cron(refresh_llm_provider_cookies_task, minute={7, 27, 47}),
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
    user_id: Optional[int] = None,
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
        user_id=user_id,
    )
    if job is None:
        raise RuntimeError("enqueue_job returned None (job may already exist)")
    # 记录归属：worker 侧据此校验产物归属，状态查询侧据此拒绝跨用户读取
    if user_id is not None:
        await pool.set(
            TASK_OWNER_KEY.format(task_id=job.job_id),
            str(user_id),
            ex=TASK_OWNER_TTL_SECONDS,
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


async def submit_audit_log(payload: dict) -> str:
    """提交审计日志写入任务，返回 task_id。

    ``audit_service.record_async`` 调用；队列不可用时由调用方回落到同步写。
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job("write_audit_log_task", payload)
    if job is None:
        raise RuntimeError("enqueue_job returned None (job may already exist)")
    return job.job_id


async def get_task_status(
    task_id: str,
    *,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> TaskResult:
    """查询任务状态（使用 arq Job API：status / result_info）

    传入 user_id 时校验任务归属：完成态结果里带服务器文件路径，
    不能让任意登录用户凭 task_id 读到他人工件位置。
    """
    pool = await get_arq_pool()

    if user_id is not None and not is_admin:
        owner = await pool.get(TASK_OWNER_KEY.format(task_id=task_id))
        # owner 为空说明是未记录归属的旧任务或非用户任务，保持可查；
        # 一旦有归属记录就严格比对，避免跨用户读取
        if owner is not None and int(owner) != user_id:
            raise PermissionError("无权查看该任务")

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
