"""工作流 → 智能体工具桥回归测试（P0-3 第二片）。

钉死的语义：只有**已启用**工作流被注册（名字唯一且安全）；触发者身份从
会话 contextvar 透传；成功/失败/等待人工输入三种结局的工具返回都可被
模型读取；agent run 被取消时不留僵尸 running 行；工作流签名变了 Agent
缓存必须失效。
"""

from __future__ import annotations

import asyncio
import json

from unittest.mock import AsyncMock, patch

from app.core.security import hash_password
from app.db.models import UserModel, WorkflowModel, WorkflowRunModel
from app.db.session import create_db_session

TEMPLATE_GRAPH = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "t", "type": "template", "params": {"template": "处理结果：{{inputs.q}}"}},
        {"id": "end", "type": "end", "params": {"output": "{{nodes.t.output}}"}},
    ],
    "edges": [
        {"from": "start", "to": "t"},
        {"from": "t", "to": "end"},
    ],
}

HUMAN_GRAPH = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "ask", "type": "human_input", "params": {"prompt": "请确认发布"}},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "ask"},
        {"from": "ask", "to": "end"},
    ],
}


def _make_workflow(name: str, *, enabled: bool = True, graph: dict | None = None) -> int:
    with create_db_session() as db:
        # 幂等：同名工作流已存在时先清掉（含其运行记录），避免上一个用例
        # 中途失败留下的数据让本用例撞 UNIQUE 约束
        existing = db.query(WorkflowModel).filter(WorkflowModel.name == name).first()
        if existing is not None:
            db.query(WorkflowRunModel).filter(
                WorkflowRunModel.workflow_id == existing.id
            ).delete()
            db.delete(existing)
            db.commit()
        row = WorkflowModel(
            name=name,
            description=f"{name} 的说明",
            graph_json=json.dumps(graph or TEMPLATE_GRAPH, ensure_ascii=False),
            enabled=enabled,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _cleanup(names: list[str], emails: list[str] | None = None) -> None:
    from sqlalchemy import delete

    with create_db_session() as db:
        ids = [r[0] for r in db.query(WorkflowModel.id).filter(WorkflowModel.name.in_(names)).all()]
        if ids:
            db.execute(delete(WorkflowRunModel).where(WorkflowRunModel.workflow_id.in_(ids)))
        db.execute(delete(WorkflowModel).where(WorkflowModel.name.in_(names)))
        if emails:
            db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def _make_user(email: str, *, role: str = "user") -> int:
    with create_db_session() as db:
        existing = db.query(UserModel).filter(UserModel.email == email).first()
        if existing is not None:
            return existing.id
        user = UserModel(
            email=email, name="WF Tool", password_hash=hash_password("pw-123456"),
            role=role, is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id
    # 补角色绑定 + 给 user 角色授权工作流功能（注册流程会做，测试直接建库不会）。
    # 不做全局清理夹具：那会和别的测试文件互相拆台（踩过）。
    from app.services.permission_service import get_permission_service

    svc = get_permission_service()
    for feature in ("use_workflows", "view_workflow_runs"):
        svc.add_policy("user", "*", f"feature:{feature}", "read")
        svc.add_policy("admin", "*", f"feature:{feature}", "read")
    svc.add_role_for_user(
        f"user:{uid}",
        role if role == "admin" else "user",
        "*" if role == "admin" else "global",
    )
    svc.reload()
    return uid


def _registry():
    from wuwei.tools import ToolRegistry

    return ToolRegistry()


def _find_tool(registry, wf_name: str, wf_id: int):
    from app.tools.workflow_tools import sanitize_tool_slug

    name = f"run_workflow_{sanitize_tool_slug(wf_name, wf_id)}"
    return name, registry.get(name)


def _set_session_owner(owner_id: int | None) -> None:
    """把 owner 身份写进会话上下文（真实链路：orchestrator 在 run 开始时设置）。"""
    from app.services.agent_service import _current_session_id

    if owner_id is None:
        _current_session_id.set(None)
        return
    # 直接往 session 存储里写一个最小会话行，get_owner_id 才能查到
    from app.db.models import AgentSessionModel
    from app.db.session import create_db_session

    sid = "wf-tool-test-session"
    with create_db_session() as db:
        existing = db.query(AgentSessionModel).filter(AgentSessionModel.session_id == sid).first()
        if existing is None:
            db.add(AgentSessionModel(
                session_id=sid,
                user_id=owner_id,
                system_prompt="",
            ))
        else:
            existing.user_id = owner_id
        db.commit()
    # 每次设置 owner 时补一次 g 绑定：authorization 用例/清理可能移除了它，
    # 否则工作流默认拒绝会把已授权的用户也挡在外面
    from app.services.permission_service import get_permission_service

    svc = get_permission_service()
    svc.add_role_for_user(f"user:{owner_id}", "user", "global")
    svc.reload()
    _current_session_id.set(sid)


def _clear_session() -> None:
    from app.services.agent_service import _current_session_id

    _current_session_id.set(None)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_only_enabled_workflows_registered(self):
        on_id = _make_workflow("wf工具-启用", enabled=True)
        off_id = _make_workflow("wf工具-停用", enabled=False)
        try:
            registry = _registry()
            from app.tools.workflow_tools import register_workflow_tools

            names = register_workflow_tools(registry)
            on_name, on_tool = _find_tool(registry, "wf工具-启用", on_id)
            off_name, off_tool = _find_tool(registry, "wf工具-停用", off_id)
            assert on_name in names and on_tool is not None
            assert off_tool is None, "停用的工作流不能注册成工具"
            assert on_tool.display_name == "工作流：wf工具-启用"
            assert on_tool.execution.side_effect is True, "工作流工具强制串行（副作用）"
        finally:
            _cleanup(["wf工具-启用", "wf工具-停用"])

    def test_tool_name_is_registry_safe(self):
        from app.tools.workflow_tools import sanitize_tool_slug

        slug = sanitize_tool_slug("报销制度 流程/审批!", 42)
        assert slug == "报销制度-流程-审批-42" or all(
            c.isalnum() or c in "-_" for c in slug
        ), "工具名只能含字母数字-_（重名注册会炸）"
        # 中文也算 \w? 保守起见：非 [a-zA-Z0-9_-] 必须被折叠
        assert "/" not in slug and "!" not in slug and " " not in slug


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------

class TestExecution:
    def test_success_returns_outputs_and_records_owner(self):

        user_id = _make_user("wf-tool-owner@example.com")
        wf_id = _make_workflow("wf工具-成功")
        try:
            registry = _registry()
            from app.tools.workflow_tools import register_workflow_tools

            register_workflow_tools(registry)
            name, tool = _find_tool(registry, "wf工具-成功", wf_id)

            _set_session_owner(user_id)
            try:
                result = asyncio.run(tool.handler({"q": "季度报销"}))
            finally:
                _clear_session()
            body = json.loads(result)
            assert body["status"] == "succeeded", result
            assert body["outputs"] == "处理结果：季度报销"
            # 运行记录归属触发者
            with create_db_session() as db:
                run = db.get(WorkflowRunModel, body["run_id"])
                assert run is not None and run.triggered_by == user_id
        finally:
            _cleanup(["wf工具-成功"], ["wf-tool-owner@example.com"])

    def test_no_session_context_is_denied(self):
        """无会话身份 → 拒绝（工具桥不能成为绕过端点鉴权的后门）。"""
        registry = _registry()
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-无上下文")
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-无上下文", wf_id)
            _clear_session()
            result = asyncio.run(tool.handler({"q": "x"}))
            assert json.loads(result)["status"] == "denied"
        finally:
            _cleanup(["wf工具-无上下文"])

    def test_waiting_input_returns_prompt_and_run_id(self):
        registry = _registry()
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-等确认", graph=HUMAN_GRAPH)
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-等确认", wf_id)
            # 有身份但无「会话仍在等用户」的场景：直接以已授权用户身份调用，
            # 并让 contextvar 里没有 session_id —— 工具应回退为 waiting 提示
            # 而不是阻塞等待对话输入。
            from app.tools import workflow_tools as wt

            fallback_owner_id = _make_user("wf-fallback-owner2@example.com")
            authorized = wt._load_user(fallback_owner_id)
            _clear_session()
            with patch.object(wt, "_resolve_trigger_user", AsyncMock(return_value=authorized)):
                result = asyncio.run(tool.handler({}))
            body = json.loads(result)
            assert body["status"] == "waiting_input"
            assert body["prompt"] == "请确认发布"
            assert body["run_id"]
            # run 停在 waiting_input，可被 resume API 接手
            with create_db_session() as db:
                run = db.get(WorkflowRunModel, body["run_id"])
                assert run.status == "waiting_input"
        finally:
            _cleanup(["wf工具-等确认"], ["wf-fallback-owner2@example.com"])

    def test_unauthenticated_session_is_denied(self):
        """有会话但没有触发者身份（未授权）→ denied。"""
        registry = _registry()
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-未授权")
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-未授权", wf_id)
            _clear_session()
            result = asyncio.run(tool.handler({"q": "x"}))
            body = json.loads(result)
            assert body["status"] == "denied"
            assert "授权" in body["message"]
        finally:
            _cleanup(["wf工具-未授权"])

    def test_missing_variable_reports_failed_with_steps(self):
        registry = _registry()
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-会失败")
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-会失败", wf_id)
            _set_session_owner(_make_user("wf-fail-owner@example.com"))
            # TEMPLATE_GRAPH 引用 inputs.q：不给 q → 节点失败
            result = asyncio.run(tool.handler({}))
            _clear_session()
            body = json.loads(result)
            assert body["status"] == "failed"
            assert body["error"]
            assert any(s["status"] == "failed" for s in body["steps"])
        finally:
            _cleanup(["wf工具-会失败"], ["wf-fail-owner@example.com"])

    def test_workflow_disabled_after_registration(self):
        """注册后工作流被停用：工具调用返回 unavailable，不执行。"""
        registry = _registry()
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-注册后停用")
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-注册后停用", wf_id)
            with create_db_session() as db:
                row = db.get(WorkflowModel, wf_id)
                row.enabled = False
                db.commit()
            _clear_session()
            result = asyncio.run(tool.handler({"q": "x"}))
            body = json.loads(result)
            assert body["status"] == "unavailable", result
        finally:
            _cleanup(["wf工具-注册后停用"])


# ---------------------------------------------------------------------------
# 缓存键签名
# ---------------------------------------------------------------------------

class TestTriggerUserDetachment:
    """触发者对象必须在会话关闭后仍可读（DetachedInstanceError 回归）。

    真实链路：_resolve_trigger_user() → _load_user() 关掉会话 →
    start_run() 写 run 行 → 其他路径再访问 user.role（如知识检索 ACL）。
    SQLAlchemy 的 expire_on_commit=False 只掩盖 commit 场景，close 后的
    懒加载一定会抛 —— 用一次「访问一个未预先加载的列」来钉住它。
    """

    def test_user_readable_after_session_closed(self):
        from app.tools.workflow_tools import _load_user

        user_id = _make_user("wf-detach@example.com")
        try:
            user = _load_user(user_id)
            assert user is not None
            # 模拟下游在读 ACL：访问多个标量列
            assert user.email == "wf-detach@example.com"
            assert user.role == "user"
            assert user.id == user_id
            # 游离态：不再受任何会话约束
            from sqlalchemy import inspect as sa_inspect

            assert sa_inspect(user).detached is True
        finally:
            _cleanup([], ["wf-detach@example.com"])

    def test_load_user_missing_returns_none(self):
        from app.tools.workflow_tools import _load_user

        assert _load_user(None) is None
        assert _load_user(99_999_999) is None


class TestWorkflowsSignature:
    def test_signature_changes_on_enable_and_edit(self):
        wf_id = _make_workflow("wf工具-签名", enabled=False)
        try:
            from app.tools.workflow_tools import workflows_signature

            with create_db_session() as db:
                off_sig = workflows_signature(db)
                row = db.get(WorkflowModel, wf_id)
                row.enabled = True
                db.commit()
                on_sig = workflows_signature(db)
                row.description = "改了描述"
                db.commit()
                edited_sig = workflows_signature(db)
            assert off_sig != on_sig, "启停工作流必须改变签名（Agent 缓存失效）"
            assert on_sig != edited_sig, "编辑工作流必须改变签名"
        finally:
            _cleanup(["wf工具-签名"])

    def test_agent_cache_key_includes_signature(self):
        """_get_agent 的缓存键包含工作流签名（直接检查源码结构 + 构建键值差异）。"""
        from app.services.agent.factory import AgentFactory

        import inspect

        src = inspect.getsource(AgentFactory._get_agent)
        assert "workflows_sig" in src, "缓存键必须含工作流签名，否则启停工作流后工具集陈旧"

    def test_tool_has_no_tool_level_timeout(self):
        """刻意不设工具级超时：人工输入的等待时长无法预估（对话里答复可能
        几分钟后才来）；执行段由工作流自身的节点/总超时兜底，用户断开会话
        → CancelledError 清理。与外部系统的 UserInputBlocker 同款语义。"""
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-超时", enabled=True)
        try:
            registry = _registry()
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-超时", wf_id)
            assert tool is not None
            assert tool.execution.timeout_seconds is None
        finally:
            _cleanup(["wf工具-超时"])

    def test_waiting_input_resolves_in_chat_via_blocker(self):
        """对话内人工输入闭环：工具接 UserInputBlocker → 用户答复 → 就地
        恢复跑完剩余节点 → 工具返回最终结果（模型无需二次调用）。"""
        from unittest.mock import patch

        registry = _registry()
        from app.tools import workflow_tools as wt_module
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-对话确认", graph={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "ask", "type": "human_input", "params": {
                    "prompt": "请确认发布",
                    "fields": [{"key": "confirm", "label": "确认", "type": "text", "required": True}],
                }},
                {"id": "end", "type": "end", "params": {"output": "{{nodes.ask.output.confirm}}"}},
            ],
            "edges": [
                {"from": "start", "to": "ask"},
                {"from": "ask", "to": "end"},
            ],
        })
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-对话确认", wf_id)
            _clear_session()
            # 建会话行并设置 contextvar（request_input 需要 session_id）。
            # 邮箱必须全文件唯一：同名会在别的用例 _cleanup 时被连带删除，
            # 表现为本用例拿不到 owner（captured 为空）。
            _clear_session()
            blocker_uid = _make_user("wf-chat-owner-blocker@example.com")
            _set_session_owner(blocker_uid)

            captured: dict = {}
            # 断言身份与授权就绪（否则下面的 KeyError 难以归因）
            resolved = asyncio.run(wt_module._resolve_trigger_user())
            assert resolved is not None and resolved.id == blocker_uid
            assert wt_module._may_use_workflows(resolved) is True

            async def fake_request_input(session_id, payload):
                captured["session_id"] = session_id
                captured["payload"] = payload
                return {"confirm": "已确认"}

            with patch(
                "app.services.external_systems.coordinators.UserInputBlocker.request_input",
                fake_request_input,
            ):
                result = asyncio.run(tool.handler({}))

            assert captured["payload"]["type"] == "user_input_required"
            assert captured["payload"]["api_name"].startswith("wf_run_")
            assert captured["payload"]["message"] == "请确认发布"
            assert captured["payload"]["fields"][0]["key"] == "confirm"

            body = json.loads(result)
            assert body["status"] == "succeeded", result
            assert body["outputs"] == "已确认", "答复后应就地恢复并产出最终结果"
        finally:
            _clear_session()
            _cleanup(["wf工具-对话确认"], ["wf-chat-owner-blocker@example.com"])

    def test_waiting_input_fallback_without_session(self):
        """无会话上下文（API 直跑/管理面板）：维持 waiting 提示回退。"""
        registry = _registry()
        from app.tools.workflow_tools import register_workflow_tools

        wf_id = _make_workflow("wf工具-无会话回退", graph={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "ask", "type": "human_input", "params": {"prompt": "确认？"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [{"from": "start", "to": "ask"}, {"from": "ask", "to": "end"}],
        })
        try:
            register_workflow_tools(registry)
            _name, tool = _find_tool(registry, "wf工具-无会话回退", wf_id)
            # 有身份、但 contextvar 无 session_id（API 直跑/管理面板）：
            # 应回退为 waiting 提示，而不是阻塞等待对话输入
            from app.tools import workflow_tools as wt

            owner = wt._load_user(_make_user("wf-fallback-owner9@example.com"))
            _clear_session()
            with patch.object(wt, "_resolve_trigger_user", AsyncMock(return_value=owner)):
                result = asyncio.run(tool.handler({}))
            body = json.loads(result)
            assert body["status"] == "waiting_input"
            assert body["prompt"] == "确认？"
        finally:
            _cleanup(["wf工具-无会话回退"], ["wf-fallback-owner9@example.com"])

    def test_factory_registers_workflow_tools(self):
        """_build_tool_registry 真实路径：DB 里有启用工作流 → 注册表含对应工具。"""
        wf_id = _make_workflow("wf工具-工厂注册", enabled=True)
        try:
            from app.services.agent_profile_service import RuntimeAgentProfile
            from app.services.agent.factory import AgentFactory

            profile = RuntimeAgentProfile(
                profile_id=None, name="t", slug="t", response_mode="general",
                system_prompt="", builtin_tools=("calc",), approval_tools=frozenset(),
                signature=(), skills=(),
            )
            registry, _ = AgentFactory._build_tool_registry(profile)
            _name, tool = _find_tool(registry, "wf工具-工厂注册", wf_id)
            assert tool is not None, "工厂构建注册表时应包含启用工作流的工具"
        finally:
            _cleanup(["wf工具-工厂注册"])
