"""
任务队列（taskiq · 原生支持 Redis Cluster）

用于处理重计算任务（PPT 导出、npm build、知识编译等），
避免阻塞 API 事件循环。

## 为什么从 arq 迁到 taskiq

arq 0.28 的 ``ArqRedis`` 是普通 ``redis.asyncio.Redis``，且消费端重度依赖
``pipeline(transaction=True)``。在 Redis Cluster 下：

- 普通客户端连集群节点 → key 不归该节点管就 ``MOVED``；
- ``RedisCluster.pipeline(transaction=True)`` 在 redis-py 里**无条件抛异常**
  （"transaction is deprecated in cluster mode"），与 key 是否同槽无关。

已在内网 6 节点集群实测：arq 的做法 30 个 key 有 15 个抛 ``MovedError``。
taskiq-redis 提供原生 cluster 类（``RedisStreamClusterBroker`` 等），
实现上完全不用事务，同集群实测全部通过。

## 启动 worker

    taskiq worker app.services.task_queue:taskiq_broker --workers 1

## 提交任务

    from app.services.task_queue import submit_ppt_export
    task_id = await submit_ppt_export(artifact_id, ...)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

from app.core.config import get_settings  # noqa: F401  (保留供外部 import)

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


async def send_annual_wrapped_task(ctx: dict, year: int | None = None) -> dict:
    """每年 1 月 1 日给全体活跃用户群发上一年度的个人 AI 报告邮件。

    cron 触发时不传 year，默认取「当前年 - 1」。也可由管理员端点指定年份/
    单个用户手动触发。系统邮箱未配置时安全跳过（见 dispatch_annual_wrapped）。
    """
    from app.core.timezone import app_now
    from app.services.notification_service import dispatch_annual_wrapped

    target_year = year if year is not None else app_now().year - 1
    result = await dispatch_annual_wrapped(target_year)
    logger.info("[Worker] Annual wrapped %s: %s", target_year, result)
    return {"status": "completed", "year": target_year, **result}


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
                # 绑定到用户的凭据续期失败：若是认证类失败（域密码已改），
                # 吊销其平台会话强制重新登录 —— 新密码在 LDAP 登录时被捕获，
                # 凭据自动更新，Cookie 随之恢复。这正是「密码轮换自愈」闭环。
                from app.services.llm_providers import gateway_link

                gateway_link.handle_credential_auth_failure(
                    credential_id, result.message, allow_revoke=True
                )
        except Exception as exc:  # noqa: BLE001 —— 单个账号失败不影响其余
            logger.warning("[Worker] LLM provider cookie refresh failed %s: %s", label, exc)
            failed.append({"provider": label, "error": str(exc)[:200]})
            from app.services.llm_providers import gateway_link

            gateway_link.handle_credential_auth_failure(
                credential_id, f"续期异常: {exc}", allow_revoke=True
            )

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


def _redis_settings_from_url():
    """**已废弃**：arq 专用的 RedisSettings，保留仅为兼容旧引用。

    队列已迁到 taskiq（见 ``task_queue_taskiq.py``），它原生支持 Redis
    Cluster。这里保留函数名避免外部脚本 import 失败，但不再使用。
    """
    from app.services.task_queue_taskiq import _queue_url

    return _queue_url()


class WorkerSettings:
    """**已废弃**：arq worker 配置。

    队列已迁到 taskiq —— arq 在 Redis Cluster 上无解（普通客户端 MOVED、
    RedisCluster 拒绝事务）。worker 启动命令改为：

        taskiq worker app.services.task_queue:taskiq_broker --workers 1

    ``WorkerSettings`` 保留仅为兼容旧的部署脚本引用，不再使用。
    """

    functions = [
        export_pptx_task,
        compile_document_task,
        build_website_task,
        write_audit_log_task,
        purge_audit_logs_task,
        scan_knowledge_conflicts_task,
        refresh_llm_provider_cookies_task,
        send_annual_wrapped_task,
    ]


# ---------------------------------------------------------------------------
# taskiq broker + 任务注册
# ---------------------------------------------------------------------------

from app.services.task_queue_taskiq import AgenticosWorkerMiddleware, build_broker_with_backend  # noqa: E402

#: 全局 broker（taskiq worker 的入口对象）
taskiq_broker = build_broker_with_backend()

#: 启动钩子（初始化 Redis manager、加载厂商预设）挂在这个 middleware 上：
#: taskiq 0.13 的 broker 没有 add_startup_hook，只有 TaskiqMiddleware.startup。
taskiq_broker.add_middlewares(AgenticosWorkerMiddleware())


# 任务注册：taskiq 用 @broker.task 装饰，任务名即注册名。
# arq 时代任务函数第一个参数是 ctx（arq 注入的上下文 dict），taskiq 没有这个
# 约定 —— 用下面的薄包装把 ctx 补成空 dict，任务体一行都不用改。
_registered = {}


def _register(task_fn, name: str):
    """把 arq 风格任务（首参 ctx）注册成 taskiq 任务。"""

    async def _runner(*args, **kwargs):
        return await task_fn({}, *args, **kwargs)

    _runner.__name__ = name
    # taskiq 0.13 的 task() 签名是 (task_name=None, **labels)。若写 name= 会被
    # 当作 label 吞掉，task_name 落回自动生成的模块限定名
    # （app.services.task_queue:xxx），而 scheduler/生产者发的是裸名，
    # worker find_task(裸名) 查不到 → 全部 "not found"、任务静默不执行。
    # 必须用 task_name= 让注册名与调度/生产侧的裸名对齐。
    _registered[name] = taskiq_broker.task(task_name=name)(_runner)
    return _registered[name]


export_pptx = _register(export_pptx_task, "export_pptx_task")
compile_document = _register(compile_document_task, "compile_document_task")
build_website = _register(build_website_task, "build_website_task")
write_audit_log = _register(write_audit_log_task, "write_audit_log_task")
purge_audit_logs = _register(purge_audit_logs_task, "purge_audit_logs_task")
scan_knowledge_conflicts = _register(scan_knowledge_conflicts_task, "scan_knowledge_conflicts_task")
refresh_llm_provider_cookies = _register(
    refresh_llm_provider_cookies_task, "refresh_llm_provider_cookies_task"
)
send_annual_wrapped = _register(send_annual_wrapped_task, "send_annual_wrapped_task")


# ---------------------------------------------------------------------------
# 定时任务（taskiq scheduler）
# ---------------------------------------------------------------------------


def build_schedule_source():
    """定时任务的 schedule source：集群用 cluster 版（scan 跨节点）。

    source 里只存「cron 定义」，任务体仍是上面注册的 taskiq task。
    """
    from app.services.task_queue_taskiq import _queue_url, is_cluster

    url = _queue_url()
    if is_cluster():
        from taskiq_redis import RedisClusterScheduleSource

        return RedisClusterScheduleSource(url=url, prefix="agenticos:schedule")

    from taskiq_redis import ListRedisScheduleSource

    return ListRedisScheduleSource(url=url, prefix="agenticos:schedule")


def build_scheduler():
    """构造 scheduler（`taskiq scheduler` 的入口对象）。

    cron 与 arq 时代保持一致：
    - 审计保留期清理：每天 03:17
    - 知识库冲突巡检：每周一 04:23（全库扫描比单次编译贵，日频过密；
      选周一凌晨是因为周末通常没人上传文档，扫的是最稳定的语料）
    - 企业网关 Cookie 续期：每小时 07/27/47 分（比过期缓冲默认 2h 密得多，
      保证「快过期」能被及时发现，而不是卡在缓冲窗口边缘）
    """
    from taskiq import TaskiqScheduler

    return TaskiqScheduler(broker=taskiq_broker, sources=[build_schedule_source()])


#: `taskiq scheduler` 的入口对象
taskiq_scheduler = build_scheduler()

#: cron 定义（由 `python -m app.services.task_queue_seed` 一次性写入 source）
CRON_SCHEDULES = (
    ("purge_audit_logs_task", "17 3 * * *"),
    ("scan_knowledge_conflicts_task", "23 4 * * 1"),
    ("refresh_llm_provider_cookies_task", "7,27,47 * * * *"),
    # 每年 1 月 1 日 08:00 群发上一年度个人 AI 报告邮件
    ("send_annual_wrapped_task", "0 8 1 1 *"),
)


# ---------------------------------------------------------------------------
# 任务提交辅助函数
# ---------------------------------------------------------------------------


async def get_broker():
    """获取 taskiq broker（单例，异步启动）。

    保留 ``get_arq_pool`` 的名字给旧调用方；返回的对象支持 ``set/get``
    （通过 ``broker.result_backend``）以满足历史代码里的归属记录读写。
    """
    from app.services import task_queue_taskiq

    return await task_queue_taskiq.get_broker()


#: 兼容别名（旧代码 / 脚本可能引用）
get_arq_pool = get_broker


async def close_arq_pool() -> None:
    """关闭队列连接（供优雅关闭时调用）。"""
    from app.services import task_queue_taskiq

    await task_queue_taskiq.close_broker()


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
    task = await export_pptx.kiq(
        artifact_id=artifact_id,
        canvas_format=canvas_format,
        theme=theme,
        use_native_shapes=use_native_shapes,
        use_compat_mode=use_compat_mode,
        transition=transition,
        animation=animation,
        enable_notes=enable_notes,
        user_id=user_id,
    )
    # 记录归属：worker 侧据此校验产物归属，状态查询侧据此拒绝跨用户读取
    if user_id is not None:
        await _set_owner(task.task_id, user_id)
    return task.task_id


async def submit_document_compilation(
    document_id: int,
    knowledge_base_id: int,
) -> str:
    """提交文档编译任务，返回 task_id"""
    task = await compile_document.kiq(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
    )
    return task.task_id


async def submit_website_build(
    project_path: str,
) -> str:
    """提交网站构建任务，返回 task_id"""
    task = await build_website.kiq(project_path=project_path)
    return task.task_id


async def submit_audit_log(payload: dict) -> str:
    """提交审计日志写入任务，返回 task_id。

    ``audit_service.record_async`` 调用；队列不可用时由调用方回落到同步写。
    """
    task = await write_audit_log.kiq(payload=payload)
    return task.task_id


# ---------------------------------------------------------------------------
# 任务归属（Redis 直存，跨 arq/taskiq 语义都成立）
# ---------------------------------------------------------------------------


async def _set_owner(task_id: str, user_id: int) -> None:
    """记录任务归属。写失败不影响投递（归属缺失时退化为「可查」）。"""
    try:
        from app.core.redis import get_redis

        await get_redis().set(
            TASK_OWNER_KEY.format(task_id=task_id),
            str(user_id),
            ex=TASK_OWNER_TTL_SECONDS,
        )
    except Exception:  # noqa: BLE001
        logger.warning("记录任务归属失败 task_id=%s", task_id, exc_info=True)


async def _get_owner(task_id: str) -> Optional[str]:
    try:
        from app.core.redis import get_redis

        return await get_redis().get(TASK_OWNER_KEY.format(task_id=task_id))
    except Exception:  # noqa: BLE001
        return None


async def get_task_status(
    task_id: str,
    *,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> TaskResult:
    """查询任务状态（taskiq result backend）

    传入 user_id 时校验任务归属：完成态结果里带服务器文件路径，
    不能让任意登录用户凭 task_id 读到他人工件位置。
    """
    from app.services import task_queue_taskiq

    if user_id is not None and not is_admin:
        owner = await _get_owner(task_id)
        # owner 为空说明是未记录归属的旧任务或非用户任务，保持可查；
        # 一旦有归属记录就严格比对，避免跨用户读取
        if owner is not None and int(owner) != user_id:
            raise PermissionError("无权查看该任务")

    # taskiq 的 result backend 只有「有结果 / 没结果」两种可见状态：
    # 排队中与执行中都表现为还没有结果。真实状态从 broker 的 stream 里能
    # 看到，但不值得为状态查询多连一次；对外语义保持 pending/running 的
    # 区分没有意义（前端只区分「还没好」和「已完成/失败」）。
    try:
        result = await task_queue_taskiq.get_result_raw(task_id)
    except Exception as exc:  # noqa: BLE001
        # 连接类错误抛给上层映射 503；其余按未知处理
        text = repr(exc).lower()
        if any(m in text for m in ("connection", "refused", "timeout", "unreachable")):
            raise
        logger.warning("查询任务结果失败 task_id=%s: %s", task_id, exc)
        return TaskResult(task_id=task_id, status="unknown")

    if result is None:
        # 没有结果：可能还在排队/执行，也可能是旧任务已被清理
        return TaskResult(task_id=task_id, status="pending")

    if result.is_err:
        return TaskResult(task_id=task_id, status="failed", error=str(result.error or result.return_value))

    value = result.return_value
    if value is not None and not isinstance(value, dict):
        value = {"value": value}
    return TaskResult(task_id=task_id, status="completed", result=value)
