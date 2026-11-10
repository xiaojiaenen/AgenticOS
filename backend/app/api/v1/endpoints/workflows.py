"""工作流端点（P0-3 v1）：CRUD + 运行 + 人工输入恢复。

权限模型：
- 写操作（创建/修改/删除）：仅管理员 —— 工作流是平台级能力，定义即代码，
  不能让普通用户互相注入 HTTP 出口或 LLM 消耗；
- 运行：登录用户，但**只能运行 enabled 的工作流**（管理员可跑草稿调试）；
- 运行记录：触发者本人或管理员可见。

运行是**同步内联**执行（有 run_timeout_seconds 总超时兜底）；异步化（ARQ
任务队列 + SSE 推送）留给 v2，与画布一起做。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin, require_feature
from app.db.models import UserModel, WorkflowModel, WorkflowRunModel
from app.services.workflow import (
    WorkflowError,
    WorkflowValidationError,
    create_workflow,
    delete_workflow,
    launch_resume,
    launch_run,
    run_to_dict,
    update_workflow,
    workflow_to_dict,
)

router = APIRouter(prefix="/workflows", tags=["工作流"])

_logger = logging.getLogger("agenticos.workflow.api")


class WorkflowUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    graph: dict[str, Any]
    enabled: bool = False


class WorkflowRunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowEnabledRequest(BaseModel):
    enabled: bool


class WorkflowResumeRequest(BaseModel):
    value: Any = None


def _workflow_or_404(db: Session, workflow_id: int) -> WorkflowModel:
    row = db.get(WorkflowModel, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return row


def _run_or_404(db: Session, run_id: int) -> WorkflowRunModel:
    row = db.get(WorkflowRunModel, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return row


def _ensure_run_visible(run: WorkflowRunModel, user: UserModel) -> None:
    if user.role == "admin":
        return
    if run.triggered_by != user.id:
        raise HTTPException(status_code=403, detail="无权查看该运行记录")


@router.get("", summary="工作流列表（管理员全量；普通用户仅已启用）")
async def list_workflows(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(WorkflowModel)
    if current_user.role != "admin":
        query = query.filter(WorkflowModel.enabled.is_(True))
    rows = query.order_by(WorkflowModel.id.desc()).all()
    items = []
    for row in rows:
        item = workflow_to_dict(row)
        item.pop("graph", None)  # 列表不带全量图，详情页再取
        items.append(item)
    return {"items": items, "total": len(items)}


@router.post("", summary="创建工作流（管理员）")
async def create_workflow_endpoint(
    payload: WorkflowUpsertRequest,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = create_workflow(
            db,
            name=payload.name,
            description=payload.description,
            graph=payload.graph,
            enabled=payload.enabled,
            user_id=current_user.id,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return workflow_to_dict(row)


@router.get("/{workflow_id}", summary="工作流详情")
async def get_workflow_endpoint(
    workflow_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = _workflow_or_404(db, workflow_id)
    if current_user.role != "admin" and not row.enabled:
        raise HTTPException(status_code=403, detail="该工作流未启用")
    return workflow_to_dict(row)


@router.put("/{workflow_id}", summary="修改工作流（管理员）")
async def update_workflow_endpoint(
    workflow_id: int,
    payload: WorkflowUpsertRequest,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _workflow_or_404(db, workflow_id)
    try:
        row = update_workflow(
            db,
            workflow_id,
            name=payload.name,
            description=payload.description,
            graph=payload.graph,
            enabled=payload.enabled,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return workflow_to_dict(row)


@router.put("/{workflow_id}/enabled", summary="启停工作流（管理员；不校验/不改动图）")
async def set_workflow_enabled(
    workflow_id: int,
    payload: WorkflowEnabledRequest,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """轻量启停：管理端列表的开关直接打这里，不必回传全量图。

    不走 update_workflow 的 name/description/graph 分支，enabled 之外零改动。
    """
    _workflow_or_404(db, workflow_id)
    try:
        row = update_workflow(db, workflow_id, enabled=payload.enabled)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": row.id, "enabled": row.enabled}


@router.delete("/{workflow_id}", summary="删除工作流（管理员，级联删除运行记录）")
async def delete_workflow_endpoint(
    workflow_id: int,
    current_user: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        delete_workflow(db, workflow_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "id": workflow_id}


@router.post("/{workflow_id}/run", summary="运行工作流（后台执行，立即返回 run；轮询详情看进度）")
async def run_workflow_endpoint(
    workflow_id: int,
    payload: WorkflowRunRequest,
    current_user: UserModel = Depends(require_feature("read", "use_workflows")),
    db: Session = Depends(get_db),
) -> dict:
    """异步执行：创建 running 行并调度后台任务，立即返回。

    流程受节点/总超时约束最长可跑 300s+，同步等会把 HTTP 请求挂死（代理
    网关超时断连、无法轮询进度）。前端拿 run.id 轮询 GET /workflows/runs/{id}
    到终态；进程重启时 running 行由 startup_cleanup 收尸。
    智能体工具桥不走这里 —— 它需要最终结果，直接调 service.start_run 内联执行。
    """
    row = _workflow_or_404(db, workflow_id)
    if not row.enabled and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="该工作流未启用，无法运行")
    try:
        run = await launch_run(
            workflow_id,
            payload.inputs,
            user_id=current_user.id,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run_to_dict(run)


@router.get("/{workflow_id}/runs", summary="工作流的运行记录（管理员全量；普通用户本人）")
async def list_workflow_runs(
    workflow_id: int,
    current_user: UserModel = Depends(require_feature("read", "view_workflow_runs")),
    db: Session = Depends(get_db),
) -> dict:
    _workflow_or_404(db, workflow_id)
    query = db.query(WorkflowRunModel).filter(WorkflowRunModel.workflow_id == workflow_id)
    if current_user.role != "admin":
        query = query.filter(WorkflowRunModel.triggered_by == current_user.id)
    rows = query.order_by(WorkflowRunModel.id.desc()).limit(50).all()
    return {
        "items": [run_to_dict(row, include_steps=False) for row in rows],
        "total": len(rows),
    }


@router.get("/runs/{run_id}", summary="运行记录详情（触发者本人或管理员）")
async def get_run_endpoint(
    run_id: int,
    current_user: UserModel = Depends(require_feature("read", "view_workflow_runs")),
    db: Session = Depends(get_db),
) -> dict:
    run = _run_or_404(db, run_id)
    _ensure_run_visible(run, current_user)
    return run_to_dict(run)


@router.post("/runs/{run_id}/resume", summary="恢复等待人工输入的运行")
async def resume_run_endpoint(
    run_id: int,
    payload: WorkflowResumeRequest,
    current_user: UserModel = Depends(require_feature("read", "use_workflows")),
    db: Session = Depends(get_db),
) -> dict:
    run = _run_or_404(db, run_id)
    _ensure_run_visible(run, current_user)
    if run.status != "waiting_input":
        raise HTTPException(status_code=409, detail="该运行不处于等待人工输入状态")
    try:
        # 抢占成功即返回 running；继续执行的剩余节点走后台任务（与 run 一致）
        run = await launch_resume(run_id, payload.value)
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return run_to_dict(run)
