"""
任务队列 API 端点

提供任务提交和状态查询接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_current_user
from app.db.models import UserModel

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
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    """查询任务状态"""
    from app.services.task_queue import get_task_status as _get_status
    
    result = await _get_status(task_id)
    
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
        )
        return TaskSubmitResponse(task_id=task_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit task: {e}",
        )


@router.post("/document-compile", response_model=TaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_document_compile(
    request: DocumentCompileRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """提交文档编译任务"""
    from app.services.task_queue import submit_document_compilation as _submit
    
    try:
        task_id = await _submit(
            document_id=request.document_id,
            knowledge_base_id=request.knowledge_base_id,
        )
        return TaskSubmitResponse(task_id=task_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit task: {e}",
        )


@router.post("/website-build", response_model=TaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_website_build(
    request: WebsiteBuildRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """提交网站构建任务"""
    from app.services.task_queue import submit_website_build as _submit
    
    try:
        task_id = await _submit(
            project_path=request.project_path,
        )
        return TaskSubmitResponse(task_id=task_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit task: {e}",
        )
