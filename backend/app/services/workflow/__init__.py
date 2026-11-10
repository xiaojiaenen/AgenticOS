"""工作流服务包（P0-3 v1：引擎 + 内置节点 + DB 编排）。

分层见 engine.py 模块 docstring：engine（纯计算）→ nodes（副作用边界）
→ service（DB 编排）。对外入口：

- ``validate_workflow_graph`` / ``WorkflowExecutor`` —— 引擎直用（测试/未来画布预览）
- ``create_workflow / update_workflow / delete_workflow / start_run / resume_run`` —— 端点层
"""

from app.services.workflow.engine import (
    CONDITION_OPS,
    NODE_TYPES,
    WorkflowError,
    WorkflowNodeError,
    WorkflowValidationError,
    WorkflowExecutor,
    resolve_value,
    validate_workflow_graph,
)
from app.services.workflow.service import (
    create_workflow,
    delete_workflow,
    execute_run_background,
    launch_resume,
    launch_run,
    resume_run_inline,
    run_to_dict,
    start_run,
    update_workflow,
    workflow_to_dict,
)

__all__ = [
    "CONDITION_OPS",
    "NODE_TYPES",
    "WorkflowError",
    "WorkflowNodeError",
    "WorkflowValidationError",
    "WorkflowExecutor",
    "resolve_value",
    "validate_workflow_graph",
    "create_workflow",
    "update_workflow",
    "delete_workflow",
    "start_run",
    "launch_run",
    "launch_resume",
    "resume_run_inline",
    "execute_run_background",
    "run_to_dict",
    "workflow_to_dict",
]
