"""
任务队列 API 端点

提供任务提交和状态查询接口。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.roles import is_admin_like, CAP_DANGEROUS
from app.api.deps import get_current_user, get_db, require_capability, require_perm
from app.core.data_path import WEBSITES_DIR, _parse_dir_name
from app.db.models import KBDocumentModel, KnowledgeBaseModel, UserModel

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed, unknown
    result: Optional[dict] = None
    error: Optional[str] = None


class PptExportRequest(BaseModel):
    artifact_id: str
    canvas_format: Optional[str] = None
    theme: Optional[str] = None
    use_native_shapes: bool = True
    use_compat_mode: bool = False
    transition: Optional[str] = None
    animation: Optional[str] = None
    enable_notes: bool = True


class DocumentCompileRequest(BaseModel):
    document_id: int
    knowledge_base_id: int


class WebsiteBuildRequest(BaseModel):
    project_path: str


class TaskSubmitResponse(BaseModel):
    task_id: str
    message: str = "Task submitted"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_redis_unavailable(exc: BaseException) -> bool:
    """无 Redis / 连接失败 → 503，而不是 500。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "connection",
        "connect",
        "refused",
        "timeout",
        "timed out",
        "no such host",
        "redis",
        "connectionerror",
        "connection refused",
        "cannot connect",
        "failed to connect",
        "max retries",
        "unreachable",
        "broken pipe",
        "oSError",
    )
    return any(m in text for m in markers)


def _raise_submit_error(exc: Exception) -> None:
    if _is_redis_unavailable(exc):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列不可用（无法连接 Redis），请启动 Redis 或配置 REDIS_URL",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to submit task: {exc}",
    ) from exc


def _require_document_access(
    db: Session,
    document_id: int,
    knowledge_base_id: int,
    current_user: UserModel,
) -> None:
    """document-compile 归属校验：文档必须属于该知识库，且用户可访问。"""
    doc = db.get(KBDocumentModel, document_id)
    if not doc or doc.knowledge_base_id != knowledge_base_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    kb = db.get(KnowledgeBaseModel, knowledge_base_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    is_admin = is_admin_like(current_user.role)
    if is_admin:
        return

    # private / personal 仅 owner
    if kb.visibility == "private" or kb.scope == "personal":
        if kb.owner_id != current_user.id and doc.uploaded_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: private knowledge base",
            )
        return

    # 其余：上传者或知识库 owner 可触发编译
    if doc.uploaded_by != current_user.id and kb.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not document owner",
        )


def _validate_website_project_path(project_path: str, current_user: UserModel) -> Path:
    """website-build：project_path 必须在 data/websites 白名单内，并校验归属。"""
    websites_root = WEBSITES_DIR.resolve()
    raw = Path(project_path)

    # 允许相对路径 data/websites/<slug> 或绝对路径，或纯 slug
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        parts = raw.parts
        if "websites" in parts:
            # 截取从 websites/ 开始的部分挂到 WEBSITES_DIR
            idx = parts.index("websites")
            slug_parts = parts[idx + 1 :]
            candidate = (websites_root / Path(*slug_parts)).resolve() if slug_parts else (websites_root / raw.name).resolve()
        else:
            # 纯 slug / 相对 WEBSITES_DIR
            candidate = (websites_root / raw).resolve()

    try:
        candidate.relative_to(websites_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="路径不合法，只能访问 data/websites/ 下的项目",
        )

    if candidate == websites_root or not candidate.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="网站项目不存在",
        )

    # 归属：目录名 u<uid>_s..._vN；非管理员只能构建自己的
    parsed = _parse_dir_name(candidate.name)
    is_admin = is_admin_like(current_user.role)
    if not is_admin:
        if parsed is None or parsed[0] != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: website project belongs to another user",
            )

    return candidate


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 运维台：任务列表 / 队列深度 / 重试（admin-only，重试叠加 CAP_DANGEROUS）
# ---------------------------------------------------------------------------


class QueueTaskItem(BaseModel):
    task_id: str
    name: str
    submitted_at: float
    user_id: Optional[int] = None
    kwargs: dict = {}
    status: str
    error: Optional[str] = None
    age_seconds: Optional[int] = None


class QueueTaskListResponse(BaseModel):
    items: list[QueueTaskItem]
    total_indexed: int


class QueueStatsResponse(BaseModel):
    broker: str
    queue_depth: Optional[int] = None
    recent: dict = {}
    recent_window: int = 0


class TaskRetryResponse(BaseModel):
    origin_task_id: str
    task_id: str
    name: str


@router.get("", response_model=QueueTaskListResponse)
async def list_queue_tasks(
    limit: int = 50,
    status_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    current_user: UserModel = Depends(require_perm("settings:edit")),
):
    """运维台任务列表（按提交时间倒序 + 当前状态）。

    ``status_filter``: pending / completed / failed / unknown；
    ``name_filter``: 任务名子串匹配。
    """
    from app.services.task_queue import list_queue_tasks as _list

    try:
        listing = await _list(
            limit=min(max(limit, 1), 200),
            status_filter=status_filter,
            name_filter=name_filter,
        )
    except Exception as e:
        if _is_redis_unavailable(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="任务队列不可用（无法连接 Redis）",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {e}",
        ) from e

    return QueueTaskListResponse(
        items=[QueueTaskItem(**item) for item in listing["items"]],
        total_indexed=listing["total_indexed"],
    )


@router.get("/stats", response_model=QueueStatsResponse)
async def queue_stats(
    current_user: UserModel = Depends(require_perm("settings:edit")),
):
    """队列深度 + 近期任务状态分布（运维台顶栏）。"""
    from app.services.task_queue import queue_stats as _stats

    try:
        data = await _stats()
    except Exception as e:
        # 与 list_queue_tasks / submit_task 同一套异常映射：
        # 无 Redis → 503 + 可读提示；其它异常 → 500。
        # 原先这里有两个连续的 except Exception，第一个 raise 后第二个永远
        # 不可达，导致任何异常（含 Redis 不可达）都直接 500。
        if _is_redis_unavailable(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="任务队列不可用（无法连接 Redis），请启动 Redis 或配置 REDIS_URL",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue stats: {e}",
        ) from e
    return QueueStatsResponse(**data)


@router.post("/{task_id}/retry", response_model=TaskRetryResponse)
async def retry_task(
    task_id: str,
    current_user: UserModel = Depends(require_capability(CAP_DANGEROUS)),
):
    """重试任务：按登记的参数重新投递同名任务（CAP_DANGEROUS）。

    仅限注册表里仍保留元数据的任务（默认 7 天内提交的非日志类任务）。
    """
    from app.services.task_queue import retry_task as _retry

    try:
        result = await _retry(task_id, user_id=current_user.id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        if _is_redis_unavailable(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="任务队列不可用（无法连接 Redis）",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry task: {e}",
        ) from e
    return TaskRetryResponse(**result)


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    """查询任务状态"""
    from app.services.task_queue import get_task_status as _get_status

    try:
        result = await _get_status(
            task_id,
            user_id=current_user.id,
            is_admin=is_admin_like(current_user.role),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except Exception as e:
        if _is_redis_unavailable(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="任务队列不可用（无法连接 Redis）",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query task: {e}",
        ) from e

    return TaskStatusResponse(
        task_id=result.task_id,
        status=result.status,
        result=result.result,
        error=result.error,
    )


@router.post("/ppt-export", response_model=TaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_ppt_export(
    request: PptExportRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """提交 PPTX 导出任务"""
    from app.services.task_queue import submit_ppt_export as _submit

    try:
        task_id = await _submit(
            artifact_id=request.artifact_id,
            canvas_format=request.canvas_format,
            theme=request.theme,
            use_native_shapes=request.use_native_shapes,
            use_compat_mode=request.use_compat_mode,
            transition=request.transition,
            animation=request.animation,
            enable_notes=request.enable_notes,
            user_id=current_user.id,
        )
        return TaskSubmitResponse(task_id=task_id)
    except HTTPException:
        raise
    except Exception as e:
        _raise_submit_error(e)


@router.post("/document-compile", response_model=TaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_document_compile(
    request: DocumentCompileRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """提交文档编译任务（含归属校验）"""
    _require_document_access(db, request.document_id, request.knowledge_base_id, current_user)

    from app.services.task_queue import submit_document_compilation as _submit

    try:
        task_id = await _submit(
            document_id=request.document_id,
            knowledge_base_id=request.knowledge_base_id,
        )
        return TaskSubmitResponse(task_id=task_id)
    except HTTPException:
        raise
    except Exception as e:
        _raise_submit_error(e)


@router.post("/website-build", response_model=TaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_website_build(
    request: WebsiteBuildRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """提交网站构建任务（project_path 白名单 + 归属校验）"""
    project_dir = _validate_website_project_path(request.project_path, current_user)

    from app.services.task_queue import submit_website_build as _submit

    try:
        task_id = await _submit(
            project_path=str(project_dir),
        )
        return TaskSubmitResponse(task_id=task_id)
    except HTTPException:
        raise
    except Exception as e:
        _raise_submit_error(e)


