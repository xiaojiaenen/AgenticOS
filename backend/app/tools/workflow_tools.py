"""工作流 → 智能体工具桥（P0-3 第二片）。

把**已启用**的工作流打包成智能体工具（`run_workflow_<安全名>_<id>`），
让对话里的智能体能直接执行预编排的流程 —— 路线图原文：「workflow 可整体
打包成『一个工具』喂给现有 Agent」。

设计要点：

- **动态注册**：与 MCP 工具同一模式（每个启用的工作流一个工具，按 id 后缀
  保证唯一），不进 ``TOOL_CATALOG``（管理端按组配置的工具清单不含动态工具，
  禁用工作流即等价于下线工具）。
- **身份透传**：工具在 agent 的子 task 里执行，触发者身份从
  ``_current_session_id`` contextvar 解析（与 knowledge_tools 同款）——
  工作流内部的知识检索 ACL、运行记录归属都随触发者走。
- **暂停语义**：工作流跑到 ``human_input`` 节点时工具**正常返回**等待信息
  （run_id + 提问），运行停在 ``waiting_input``；用户通过
  ``POST /workflows/runs/{id}/resume`` 回答后流程继续。工具不能替人回答。
- **取消语义**：agent run 被取消（用户断开）时，asyncio.CancelledError 会
  传进工具 —— 捕获后把 run 标记为 failed("被取消") 再原样上抛，
  不留僵尸 running 行。
- **执行安全**：side_effect=True（BoundedToolExecutor 强制串行，R-13）；
  超时由工作流自身的节点/总超时兜底；http 节点已有 SSRF 防线。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any

from app.db.models import WorkflowModel, WorkflowRunModel
from app.services.workflow.engine import WorkflowError

logger = logging.getLogger("agenticos.workflow.tools")

# 工具返回给模型的文本上限：工作流输出可能很大（检索结果聚合），
# 直接塞满上下文会把后续推理挤爆。
TOOL_OUTPUT_MAX_CHARS = 20_000

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def sanitize_tool_slug(name: str, workflow_id: int) -> str:
    """工作流名 → 工具名安全段：非字母数字字符折叠为 -，附 id 保证唯一。"""
    slug = _SAFE_NAME_RE.sub("-", (name or "").strip()).strip("-") or "wf"
    return f"{slug[:40]}-{workflow_id}"


def workflows_signature(db) -> str:
    """已启用工作流的签名（id + updated_at），作为 Agent 缓存键的一部分。

    工作流被编辑/启停后签名变化 → Agent 缓存失效 → 下次构建注册新工具集。
    """
    

    rows = (
        db.query(WorkflowModel.id, WorkflowModel.updated_at)
        .filter(WorkflowModel.enabled.is_(True))
        .order_by(WorkflowModel.id)
        .all()
    )
    raw = "|".join(f"{rid}:{updated.isoformat() if updated else ''}" for rid, updated in rows)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _may_use_workflows(user) -> bool:
    """功能级授权判定（与 ``require_feature("read", "use_workflows")`` 严格同口径）。

    **默认拒绝**：普通用户必须由管理员在「权限」页显式授予
    feature:use_workflows 才能让智能体调用工作流；管理员在
    ``enforce_for_user`` 里短路放行。

    拿不到用户身份（无会话的 API 直跑）同样拒绝 —— 工具侧不能成为绕过
    端点鉴权的后门。直跑场景走 HTTP 端点，那里有自己的门禁。
    """
    if user is None:
        return False
    from app.services.permission_service import get_permission_service

    try:
        return get_permission_service().enforce_for_user(
            user, "read", "feature", "use_workflows"
        )
    except Exception:  # noqa: BLE001 —— 权限服务异常按拒绝处理（fail-closed）
        logger.warning("workflow tool: permission check failed", exc_info=True)
        return False


def _load_user(user_id: int | None):
    """取触发者 UserModel，先 detach 再关会话，返回可安全读取的游离实例。

    踩坑：直接 `return db.get(...)` + `db.close()` 返回的是「绑定到已关闭
    会话」的实例 —— 属性眼下还在（expire_on_commit=False 掩盖了问题），
    但任何懒加载 / refresh（例如下游再次访问 user.role）都会抛
    DetachedInstanceError。手动 expunge 转成游离态才是正确语义。
    """
    if user_id is None:
        return None
    from app.db.session import SessionLocal
    from app.db.models import UserModel

    db = SessionLocal()
    try:
        user = db.get(UserModel, user_id)
        if user is not None:
            db.refresh(user)  # 确保列已加载
            db.expunge(user)  # 转为游离态，关闭会话后仍可读
        return user
    finally:
        db.close()


async def _resolve_trigger_user():
    """从会话上下文解析触发者（与 knowledge_tools 同一身份链）。"""
    try:
        from app.services.agent_service import _current_session_id
        from app.services.session_storage import DatabaseAgentStorage

        session_id = _current_session_id.get()
        if not session_id:
            return None
        owner_id = await DatabaseAgentStorage().get_owner_id(session_id)
        return _load_user(owner_id)
    except Exception:  # noqa: BLE001 —— 身份解析失败不该让工具直接炸
        logger.warning("workflow tool: 解析触发者身份失败", exc_info=True)
        return None


def _format_result(run_dict: dict[str, Any]) -> str:
    return json.dumps(run_dict, ensure_ascii=False, default=str)[:TOOL_OUTPUT_MAX_CHARS]


def register_workflow_tools(registry) -> list[str]:
    """把所有已启用工作流注册为工具。返回注册的工具名列表。"""
    
    from app.db.session import create_db_session
    from app.services.workflow import start_run
    from app.services.workflow.service import run_to_dict

    try:
        db = create_db_session()
        try:
            rows = (
                db.query(WorkflowModel)
                .filter(WorkflowModel.enabled.is_(True))
                .order_by(WorkflowModel.id)
                .all()
            )
            workflows = [
                (row.id, row.name, row.description or "") for row in rows
            ]
        finally:
            db.close()
    except Exception:  # noqa: BLE001 —— DB 未就绪时不注册（启动早期）
        logger.warning("workflow tools: 枚举工作流失败，本轮不注册", exc_info=True)
        return []

    registered: list[str] = []
    for wf_id, wf_name, wf_desc in workflows:
        tool_name = f"run_workflow_{sanitize_tool_slug(wf_name, wf_id)}"
        if registry.get(tool_name) is not None:
            continue
        desc = (
            f"执行预编排工作流「{wf_name}」"
            + (f"：{wf_desc}" if wf_desc else "")
            + "。工作流是管理员预先编排好的自动化流程（检索/判断/生成等），"
            "比逐步手动执行更可靠。inputs 是传给流程的对象；流程若需要人工"
            "输入，会自动在对话里向用户提问并等待答复，答复后自动继续执行，"
            "无需再次调用本工具。"
        )

        async def _run_workflow(inputs: dict | None = None, _wf_id: int = wf_id) -> str:
            from app.db.session import create_db_session
            from app.services.workflow import resume_run_inline

            user = await _resolve_trigger_user()
            run_db = create_db_session()
            run_id: int | None = None
            try:
                workflow = run_db.get(WorkflowModel, _wf_id)
                if workflow is None or not workflow.enabled:
                    return _format_result({
                        "status": "unavailable",
                        "message": f"工作流 {_wf_id} 不存在或已停用",
                    })
                # 功能级授权：与 POST /workflows/{id}/run 同一口径
                # （feature:use_workflows）。未授权的用户即使能被模型调用该工具，
                # 也会得到 denied，而不是悄悄花掉管理员配置的 LLM 配额。
                if not _may_use_workflows(user):
                    return _format_result({
                        "status": "denied",
                        "message": "当前账号未被授权使用工作流，请联系管理员授予「使用工作流」权限。",
                    })
                run = await start_run(run_db, workflow, dict(inputs or {}), user=user)
                run_id = run.id
                result = run_to_dict(run)
            except asyncio.CancelledError:
                # 用户断开连接取消 agent run：不留僵尸 running 行，原样上抛
                if run_id is not None:
                    try:
                        _cleanup_run_row(run_id)
                    except Exception:  # noqa: BLE001 —— 清理尽力而为
                        pass
                raise
            finally:
                run_db.close()

            # 人工输入循环：流程每个 human_input 节点都会在**对话里**向用户
            # 提问（复用外部系统的 user_input_required 契约），用户答复后就地
            # 恢复跑完剩余节点 —— 模型最终拿到完整结果，不需要二次调用。
            # 无会话上下文（API 直跑/管理面板）时回退为 waiting 提示。
            while result.get("status") == "waiting_input":
                from app.services.agent_service import _current_session_id

                session_id = _current_session_id.get()
                if not session_id:
                    return _format_result({
                        "status": "waiting_input",
                        "run_id": result.get("id"),
                        "prompt": result.get("waiting_prompt"),
                        "message": (
                            f"工作流在第 {result.get('waiting_node_id')} 步等待人工输入，"
                            f"用户答复后在运行记录上恢复（resume）。"
                        ),
                    })
                from app.services.external_systems.coordinators import UserInputBlocker

                payload = {
                    "type": "user_input_required",
                    "api_name": f"wf_run_{result.get('id')}",
                    "api_display_name": wf_name,
                    "system_name": "workflow",
                    "fields": result.get("waiting_fields") or [{
                        "key": "value", "label": "答复", "type": "text",
                        "required": True, "description": result.get("waiting_prompt") or "",
                    }],
                    "message": result.get("waiting_prompt") or f"工作流「{wf_name}」需要人工输入：",
                }
                # 阻塞等待用户在对话里答复（SSE 会推 user_input_required 表单）。
                # 此时**不持有任何 DB 会话** —— 等待可能长达数分钟，占着连接
                # 会耗尽连接池。用户断开 → agent run 取消 → CancelledError 上抛。
                values = await UserInputBlocker.request_input(session_id, payload)
                if not isinstance(values, dict):
                    values = {"value": values}

                resume_db = create_db_session()
                try:
                    run = resume_db.get(WorkflowRunModel, result.get("id"))
                    if run is None:
                        return _format_result({
                            "status": "failed",
                            "error": f"运行记录不存在: {result.get('id')}",
                        })
                    run = await resume_run_inline(resume_db, run, values)
                    result = run_to_dict(run)
                except asyncio.CancelledError:
                    raise
                except WorkflowError as exc:
                    # 抢占失败：多半是用户已从管理面板/其他入口恢复
                    return _format_result({
                        "status": "already_resolved",
                        "message": (
                            f"工作流运行未能由本会话恢复（{exc}）。"
                            "请提示用户到运行记录里查看当前状态。"
                        ),
                    })
                finally:
                    resume_db.close()

            if result.get("status") == "failed":
                return _format_result({
                    "status": "failed",
                    "error": result.get("error"),
                    "steps": result.get("steps"),
                })
            return _format_result({
                "status": "succeeded",
                "run_id": result.get("id"),
                "outputs": result.get("outputs"),
            })

        # closure 捕获 wf_id：用默认参数绑定（循环变量陷阱）
        # 刻意**不设** timeout_seconds（wuwei 对 None 不做工具级超时）：
        # 人工输入的等待时长无法预估（用户可能几分钟后再答复），而执行段
        # 已由工作流自身的节点/总超时兜底。用户断开会话 → agent run 取消 →
        # CancelledError → 清理 run 行。与外部系统的 UserInputBlocker 同款语义。
        registry.tool(
            name=tool_name,
            display_name=f"工作流：{wf_name}",
            description=desc,
            side_effect=True,
        )(_run_workflow)
        registered.append(tool_name)

    return registered


# 延迟导入兜底：CancelledError 清理路径需要 run 模型
def _cleanup_run_row(run_id: int) -> None:
    from app.db.session import create_db_session
    from app.db.models import WorkflowRunModel

    db = create_db_session()
    try:
        row = db.get(WorkflowRunModel, run_id)
        if row is not None and row.status == "running":
            row.status = "failed"
            row.error = "工作流执行被取消（agent run 中断）"
            from app.core.timezone import app_now

            row.finished_at = app_now()
            db.commit()
    finally:
        db.close()
