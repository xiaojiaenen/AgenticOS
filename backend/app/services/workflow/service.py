"""工作流 DB 编排：run 记录、每步落库、人工输入暂停/恢复。

与 engine 的分工：engine 是纯计算（可独立单测），本文件把每一步的轨迹与
上下文快照写进 ``workflow_runs``（进度可查、崩溃可续）。恢复语义：

- 暂停时：``context_json``（各节点全量输出）+ ``steps_json``（执行顺序）
  已经落库，``waiting_node_id`` 记录暂停点；
- 恢复时：steps_json（各节点终态）+ context_json（各节点输出）天然构成
  快照，连同人工输入答复交回引擎重建（与并行完成顺序无关）。**不依赖任何内存态** —— 进程
  重启后照常可续（与 approvals 的 Redis Future 不同，这里没有并发语义，
  DB 是唯一事实源）；
- 双重恢复防护：``UPDATE ... WHERE status='waiting_input'`` 抢占式改状态，
  只有一个请求能把 run 带回 running，其余得到 409。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.timezone import app_now
from app.db.models import UserModel, WorkflowModel, WorkflowRunModel
from app.services.workflow.engine import (
    TRACE_PREVIEW_CHARS,
    WorkflowError,
    WorkflowValidationError,
    WorkflowExecutor,
    stringify_output,
    validate_workflow_graph,
)
from app.services.workflow.nodes import build_default_handlers

logger = logging.getLogger("agenticos.workflow")


# ---------------------------------------------------------------------------
# CRUD（图校验在保存时一次说清）
# ---------------------------------------------------------------------------

def validate_or_raise(graph: dict[str, Any]) -> None:
    errors = validate_workflow_graph(graph)
    if errors:
        raise WorkflowValidationError("；".join(errors))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def create_workflow(
    db: Session,
    *,
    name: str,
    description: str,
    graph: dict[str, Any],
    enabled: bool,
    user_id: int | None,
) -> WorkflowModel:
    validate_or_raise(graph)
    row = WorkflowModel(
        name=name,
        description=description or "",
        graph_json=_dump(graph),
        enabled=bool(enabled),
        created_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_workflow(
    db: Session,
    workflow_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    graph: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> WorkflowModel:
    row = db.get(WorkflowModel, workflow_id)
    if row is None:
        raise WorkflowError(f"工作流不存在: {workflow_id}")
    if graph is not None:
        validate_or_raise(graph)
        row.graph_json = _dump(graph)
    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    if enabled is not None:
        row.enabled = enabled
    row.updated_at = app_now()
    db.commit()
    db.refresh(row)
    return row


def delete_workflow(db: Session, workflow_id: int) -> None:
    row = db.get(WorkflowModel, workflow_id)
    if row is None:
        raise WorkflowError(f"工作流不存在: {workflow_id}")
    db.query(WorkflowRunModel).filter(WorkflowRunModel.workflow_id == workflow_id).delete()
    db.delete(row)
    db.commit()


def _graph_of(row: WorkflowModel) -> dict[str, Any]:
    try:
        graph = json.loads(row.graph_json or "{}")
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"工作流 {row.id} 的 graph_json 损坏: {exc}") from exc
    return graph if isinstance(graph, dict) else {}


def _end_node_id(graph: dict[str, Any]) -> str | None:
    for node in graph.get("nodes") or []:
        if node.get("type") == "end":
            return node.get("id")
    return None


# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------

class _RunDriver:
    """单次运行的落库器：on_step 里同步写 run 行（短事务，与全仓风格一致）。"""

    def __init__(
        self,
        db: Session,
        run: WorkflowRunModel,
        graph: dict[str, Any],
        *,
        node_timeout_seconds: int,
    ) -> None:
        self.db = db
        self.run = run
        self.graph = graph
        self.steps: list[dict[str, Any]] = []
        self.context: dict[str, Any] = {}
        self.paused: dict[str, Any] | None = None

        handlers = build_default_handlers(
            user_id=run.triggered_by,
            # 触发者可能已被删除 —— ACL 按最严格处理（非管理员）
            is_admin=self._triggered_by_role() == "admin",
        )
        self.executor = WorkflowExecutor(
            graph,
            handlers=handlers,
            node_timeout_seconds=node_timeout_seconds,
            on_step=self._on_step,
            on_pause=self._on_pause,
        )

    def _triggered_by_role(self) -> str | None:
        if not self.run.triggered_by:
            return None
        user = self.db.get(UserModel, self.run.triggered_by)
        return user.role if user is not None else None

    def _node_type(self, node_id: str) -> str:
        node = self.executor._nodes.get(node_id)
        return node.get("type", "?") if node else "?"

    def _on_step(self, node_id: str, status: str, duration_ms: int, output: Any, error: str | None) -> None:
        self.steps.append({
            "node_id": node_id,
            "type": self._node_type(node_id),
            "status": status,
            "duration_ms": duration_ms,
            "output_preview": stringify_output(output)[:TRACE_PREVIEW_CHARS] if output is not None else None,
            "error": error,
        })
        if status == "done":
            self.context.setdefault("nodes", {})[node_id] = {"output": output}
        self._flush()

    def _on_pause(self, node_id: str, prompt: str, fields: list[dict[str, Any]] | None = None) -> None:
        self.paused = {"node_id": node_id, "prompt": prompt, "fields": fields}

    def _flush(self) -> None:
        self.run.steps_json = _dump(self.steps)
        self.run.context_json = _dump(self.context)
        self.db.commit()

    def _fail(self, message: str) -> None:
        self.run.status = "failed"
        self.run.error = message[:4000]
        self.run.finished_at = app_now()
        self._flush()

    def _finish(self, outputs: dict[str, Any]) -> None:
        end_id = _end_node_id(self.graph)
        end_out = outputs.get(end_id) if end_id else None
        self.run.status = "succeeded"
        self.run.outputs_json = _dump(end_out if end_out is not None else outputs)
        self.run.finished_at = app_now()
        self._flush()

    def _pause(self, paused: dict[str, Any]) -> None:
        self.run.status = "waiting_input"
        self.run.waiting_node_id = paused["node_id"]
        self.run.waiting_prompt = paused["prompt"]
        fields = paused.get("fields")
        self.run.waiting_fields_json = _dump(fields) if fields else None
        self._flush()


async def _execute_run(
    db: Session,
    run: WorkflowRunModel,
    workflow: WorkflowModel,
    inputs: dict[str, Any],
    *,
    resume_state: dict[str, Any] | None = None,
) -> WorkflowRunModel:
    """执行 run 的共享路径：工具桥内联与后台任务都走这里。

    结束时 run.status 必为终态（succeeded/failed）或 waiting_input ——
    任何路径都不允许把 run 永远留在 running。
    """
    settings = _settings()
    graph = _graph_of(workflow)
    driver = _RunDriver(db, run, graph, node_timeout_seconds=settings.workflow_node_timeout_seconds)
    driver.context = {"inputs": inputs, "nodes": {}}
    try:
        result = await driver.executor.execute(
            inputs,
            resume_state=resume_state,
            run_timeout_seconds=settings.workflow_run_timeout_seconds,
        )
    except WorkflowError as exc:
        driver._fail(str(exc))
        return run
    except Exception as exc:  # noqa: BLE001 —— 引擎外的意外异常也要落成 failed
        logger.exception("workflow run %s crashed", run.id)
        driver._fail(f"内部错误: {exc}")
        return run

    if result.get("paused"):
        driver._pause(result["paused"])
    else:
        driver._finish(result.get("outputs") or {})
    return run


async def start_run(
    db: Session,
    workflow: WorkflowModel,
    inputs: dict[str, Any],
    *,
    user: UserModel | None,
) -> WorkflowRunModel:
    """内联执行：调用方的会话上直接跑完（智能体工具桥用 —— 模型要等最终结果）。"""
    run = WorkflowRunModel(
        workflow_id=workflow.id,
        status="running",
        inputs_json=_dump(inputs),
        triggered_by=user.id if user is not None else None,
        started_at=app_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return await _execute_run(db, run, workflow, inputs)


# 后台任务强引用表：create_task 的返回值若无人持有，可能在执行前被 GC
_BG_TASKS: set[asyncio.Task] = set()


def _schedule_background(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


def _reload_run(run_id: int) -> WorkflowRunModel:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(WorkflowRunModel, run_id)
        if run is None:
            raise WorkflowError(f"运行记录不存在: {run_id}")
        db.refresh(run)
        return run
    finally:
        db.close()


async def launch_run(
    workflow_id: int,
    inputs: dict[str, Any],
    *,
    user_id: int | None,
) -> WorkflowRunModel:
    """创建 run 并调度后台执行，立即返回（running 状态）。

    API 端点走这条路径：流程受节点/总超时约束最长可跑 300s+，同步等会把
    HTTP 请求挂住（代理网关超时直接断连，且无法轮询进度）。进程重启时
    running 行由 startup_cleanup 收尸为 failed("restart")。
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        workflow = db.get(WorkflowModel, workflow_id)
        if workflow is None:
            raise WorkflowError(f"工作流不存在: {workflow_id}")
        run = WorkflowRunModel(
            workflow_id=workflow_id,
            status="running",
            inputs_json=_dump(inputs),
            triggered_by=user_id,
            started_at=app_now(),
        )
        db.add(run)
        db.commit()
        run_id = run.id
    finally:
        db.close()

    _schedule_background(execute_run_background(run_id))
    return _reload_run(run_id)


def _build_resume_state(db: Session, run: WorkflowRunModel, value: Any) -> dict[str, Any]:
    """从 run 记录构建恢复快照。记录损坏时把 run 标记为 failed 并抛 WorkflowError。

    steps_json（每节点终态）+ context_json（各节点全量输出）天然构成引擎
    需要的快照 —— 与执行顺序无关，并行完成顺序不稳定也能正确重建。
    """
    try:
        context = json.loads(run.context_json or "{}")
        steps = json.loads(run.steps_json or "[]")
    except json.JSONDecodeError as exc:
        run.status = "failed"
        run.error = f"运行记录损坏: {exc}"
        run.finished_at = app_now()
        db.commit()
        raise WorkflowError(f"运行记录损坏: {exc}") from exc

    waiting_node = run.waiting_node_id
    if not waiting_node:
        run.status = "failed"
        run.error = "运行记录缺少暂停点"
        run.finished_at = app_now()
        db.commit()
        raise WorkflowError("运行记录缺少暂停点")

    node_status = {
        s["node_id"]: s["status"]
        for s in steps
        if isinstance(s, dict) and s.get("node_id") and s.get("status") in ("done", "skipped")
    }
    outputs = {
        nid: payload.get("output")
        for nid, payload in (context.get("nodes") or {}).items()
        if isinstance(payload, dict)
    }
    return {
        "node_status": node_status,
        "outputs": outputs,
        "answer_node": waiting_node,
        "answer_value": value,
    }


async def launch_resume(run_id: int, value: Any) -> WorkflowRunModel:
    """抢占式恢复 waiting_input 的 run 并调度后台执行。

    抢占失败（已恢复/非等待态）同步抛 WorkflowError —— 端点据此回 409。
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(WorkflowRunModel, run_id)
        if run is None:
            raise WorkflowError(f"运行记录不存在: {run_id}")
        claimed = db.execute(
            update(WorkflowRunModel)
            .where(WorkflowRunModel.id == run_id, WorkflowRunModel.status == "waiting_input")
            .values(status="running")
        )
        if claimed.rowcount != 1:
            raise WorkflowError("该运行不处于等待人工输入状态（可能已被恢复）")
        db.commit()
        db.refresh(run)
        resume_state = _build_resume_state(db, run, value)
    finally:
        db.close()

    _schedule_background(execute_run_background(run_id, resume_state=resume_state))
    return _reload_run(run_id)


async def execute_run_background(run_id: int, *, resume_state: dict[str, Any] | None = None) -> None:
    """后台执行入口：自带 DB 会话，独立于 HTTP 请求生命周期。"""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(WorkflowRunModel, run_id)
        if run is None or run.status != "running":
            return
        workflow = db.get(WorkflowModel, run.workflow_id)
        if workflow is None:
            run.status = "failed"
            run.error = "工作流定义已被删除"
            run.finished_at = app_now()
            db.commit()
            return
        try:
            inputs = json.loads(run.inputs_json or "{}")
        except json.JSONDecodeError:
            inputs = {}
        await _execute_run(
            db,
            run,
            workflow,
            inputs if isinstance(inputs, dict) else {},
            resume_state=resume_state,
        )
    finally:
        db.close()


async def resume_run_inline(db: Session, run: WorkflowRunModel, value: Any) -> WorkflowRunModel:
    """内联恢复 waiting_input 的 run（智能体工具桥用：用户在对话里答复后，
    工具 handler 就地把流程跑完，模型拿到最终结果）。

    抢占失败（已恢复/非等待态）抛 WorkflowError。"""
    claimed = db.execute(
        update(WorkflowRunModel)
        .where(WorkflowRunModel.id == run.id, WorkflowRunModel.status == "waiting_input")
        .values(status="running")
    )
    if claimed.rowcount != 1:
        raise WorkflowError("该运行不处于等待人工输入状态（可能已被恢复）")
    db.commit()
    db.refresh(run)

    workflow = db.get(WorkflowModel, run.workflow_id)
    if workflow is None:
        run.status = "failed"
        run.error = "工作流定义已被删除"
        run.finished_at = app_now()
        db.commit()
        return run

    resume_state = _build_resume_state(db, run, value)
    try:
        inputs = json.loads(run.inputs_json or "{}")
    except json.JSONDecodeError:
        inputs = {}
    return await _execute_run(
        db, run, workflow, inputs if isinstance(inputs, dict) else {}, resume_state=resume_state
    )


def _settings():
    from app.core.config import get_settings

    return get_settings()


def _loads_or_empty(raw: str | None) -> list[dict[str, Any]] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


def run_to_dict(run: WorkflowRunModel, *, include_steps: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "error": run.error,
        "waiting_node_id": run.waiting_node_id,
        "waiting_prompt": run.waiting_prompt,
        "waiting_fields": _loads_or_empty(run.waiting_fields_json),
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat() if isinstance(run.started_at, datetime) else None,
        "finished_at": run.finished_at.isoformat() if isinstance(run.finished_at, datetime) else None,
    }
    if include_steps:
        try:
            data["steps"] = json.loads(run.steps_json or "[]")
        except json.JSONDecodeError:
            data["steps"] = []
        try:
            data["outputs"] = json.loads(run.outputs_json) if run.outputs_json else None
        except json.JSONDecodeError:
            data["outputs"] = None
        try:
            data["inputs"] = json.loads(run.inputs_json or "{}")
        except json.JSONDecodeError:
            data["inputs"] = {}
    return data


def workflow_to_dict(row: WorkflowModel) -> dict[str, Any]:
    try:
        graph = json.loads(row.graph_json or "{}")
    except json.JSONDecodeError:
        graph = {}
    nodes = graph.get("nodes") or []
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "enabled": row.enabled,
        "node_count": len(nodes),
        "graph": graph,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else None,
        "updated_at": row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else None,
    }
