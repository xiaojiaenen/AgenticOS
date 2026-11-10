"""工作流端点测试（CRUD / 运行 / 人工输入恢复 / 鉴权）。

权限模型钉死：写操作仅管理员；普通用户只能运行**已启用**的工作流；
运行记录仅触发者本人或管理员可见。LLM 节点走 monkeypatch 假网关。
"""

from __future__ import annotations

import asyncio
import json

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel, WorkflowModel, WorkflowRunModel
from app.db.session import create_db_session
from app.main import app

# ---------------------------------------------------------------------------
# 测试件
# ---------------------------------------------------------------------------

TEMPLATE_GRAPH = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "t", "type": "template", "params": {"template": "你好 {{inputs.name}}"}},
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
        {"id": "end", "type": "end", "params": {"output": "{{nodes.ask.output}}"}},
    ],
    "edges": [
        {"from": "start", "to": "ask"},
        {"from": "ask", "to": "end"},
    ],
}

CYCLIC_GRAPH = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "a", "type": "template", "params": {"template": "x"}},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "a"},
        {"from": "a", "to": "end"},
        {"from": "end", "to": "a"},
    ],
}


def _wait_run(client, run_id: int, headers: dict, *, statuses: set[str], timeout_s: float = 15.0) -> dict:
    """后台执行：轮询 run 详情到目标状态（或超时报错）。

    run 端点已异步化 —— 提交立即返回 running，真实执行在后台任务里。
    """
    import time as _time

    deadline = _time.monotonic() + timeout_s
    body: dict = {}
    while _time.monotonic() < deadline:
        resp = client.get(f"/api/v1/workflows/runs/{run_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in statuses:
            return body
        _time.sleep(0.1)
    raise AssertionError(f"轮询超时：run {run_id} 未到达 {statuses}，最后状态 {body.get('status')}")


class FakeGateway:
    async def generate(self, messages, stream=False, **kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(message=SimpleNamespace(content="假回答"), model="fake")


def cleanup(*emails: str) -> None:
    with create_db_session() as db:
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def cleanup_workflows(*names: str) -> None:
    with create_db_session() as db:
        db.execute(delete(WorkflowRunModel).where(
            WorkflowRunModel.workflow_id.in_(
                db.query(WorkflowModel.id).filter(WorkflowModel.name.in_(names))
            )
        ))
        db.execute(delete(WorkflowModel).where(WorkflowModel.name.in_(names)))
        db.commit()


def _grant_user_role_workflow_features() -> None:
    """给 ``user`` 角色授权工作流功能（幂等）。

    工作流默认收紧：普通用户需显式授权才能运行。本文件测的是端点业务
    逻辑，所以在模块加载时给 ``user`` 角色授一次 —— 只影响本进程的
    enforcer，不写全局清理逻辑，避免与其他测试文件互相干扰。
    """
    from app.services.permission_service import get_permission_service

    svc = get_permission_service()
    for feature in ("use_workflows", "view_workflow_runs"):
        svc.add_policy("user", "*", f"feature:{feature}", "read")
        svc.add_policy("admin", "*", f"feature:{feature}", "read")
    svc.reload()


def _token(email: str, *, role: str = "user") -> str:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name="WF Tester",
            password_hash=hash_password("password-123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id
    # 补角色绑定（注册接口会写，测试直接建库不会）：没有 g 绑定，
    # 角色级授权（p, user, *, feature:use_workflows, read）对本人不生效
    from app.services.permission_service import get_permission_service

    svc = get_permission_service()
    _grant_user_role_workflow_features()
    svc.add_role_for_user(f"user:{uid}", role if role == "admin" else "user", "*" if role == "admin" else "global")
    svc.reload()
    settings = get_settings()
    return create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


# ---------------------------------------------------------------------------
# CRUD 与鉴权
# ---------------------------------------------------------------------------

class TestWorkflowCrud:
    def test_admin_can_create_user_cannot(self):
        wf_name = "wf-crud-创建权限"
        cleanup("wf-admin@example.com", "wf-user@example.com")
        cleanup_workflows(wf_name)
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                user = _token("wf-user@example.com")

                resp_user = client.post(
                    "/api/v1/workflows",
                    headers={"Authorization": f"Bearer {user}"},
                    json={"name": wf_name, "graph": TEMPLATE_GRAPH},
                )
                assert resp_user.status_code == 403, resp_user.text

                resp = client.post(
                    "/api/v1/workflows",
                    headers={"Authorization": f"Bearer {admin}"},
                    json={"name": wf_name, "description": "测试流", "graph": TEMPLATE_GRAPH},
                )
                assert resp.status_code == 200, resp.text
                body = resp.json()
                assert body["name"] == wf_name and body["node_count"] == 3
                assert body["enabled"] is False
        finally:
            cleanup("wf-admin@example.com", "wf-user@example.com")
            cleanup_workflows(wf_name)

    def test_invalid_graph_rejected_with_all_errors(self):
        wf_name = "wf-crud-环图"
        cleanup("wf-admin@example.com")
        cleanup_workflows(wf_name)
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                resp = client.post(
                    "/api/v1/workflows",
                    headers={"Authorization": f"Bearer {admin}"},
                    json={"name": wf_name, "graph": CYCLIC_GRAPH},
                )
                assert resp.status_code == 400
                assert "环" in resp.json()["detail"]
        finally:
            cleanup("wf-admin@example.com")
            cleanup_workflows(wf_name)

    def test_list_visibility_enabled_only_for_user(self):
        wf_on, wf_off = "wf-可见-启用", "wf-可见-停用"
        cleanup("wf-admin@example.com", "wf-user@example.com")
        cleanup_workflows(wf_on, wf_off)
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                user = _token("wf-user@example.com")
                h = {"Authorization": f"Bearer {admin}"}
                client.post("/api/v1/workflows", headers=h,
                            json={"name": wf_on, "graph": TEMPLATE_GRAPH, "enabled": True})
                client.post("/api/v1/workflows", headers=h,
                            json={"name": wf_off, "graph": TEMPLATE_GRAPH, "enabled": False})

                admin_list = client.get("/api/v1/workflows", headers=h).json()
                user_list = client.get(
                    "/api/v1/workflows", headers={"Authorization": f"Bearer {user}"}
                ).json()
                admin_names = {i["name"] for i in admin_list["items"]}
                user_names = {i["name"] for i in user_list["items"]}
                assert {wf_on, wf_off} <= admin_names
                assert wf_on in user_names and wf_off not in user_names

                # 停用工作流的详情：管理员可看，普通用户 403
                off_id = next(i["id"] for i in admin_list["items"] if i["name"] == wf_off)
                assert client.get(f"/api/v1/workflows/{off_id}", headers=h).status_code == 200
                assert client.get(
                    f"/api/v1/workflows/{off_id}", headers={"Authorization": f"Bearer {user}"}
                ).status_code == 403

                # 修改与删除仅管理员
                upd = client.put(
                    f"/api/v1/workflows/{off_id}",
                    headers={"Authorization": f"Bearer {user}"},
                    json={"name": wf_off, "graph": TEMPLATE_GRAPH},
                )
                assert upd.status_code == 403
                upd_admin = client.put(
                    f"/api/v1/workflows/{off_id}",
                    headers=h,
                    json={"name": wf_off, "graph": TEMPLATE_GRAPH, "enabled": True},
                )
                assert upd_admin.status_code == 200 and upd_admin.json()["enabled"] is True

                # 轻量启停端点：只改 enabled，不必回传全量图；普通用户 403
                toggle_user = client.put(
                    f"/api/v1/workflows/{off_id}/enabled",
                    headers={"Authorization": f"Bearer {user}"},
                    json={"enabled": False},
                )
                assert toggle_user.status_code == 403
                toggle_admin = client.put(
                    f"/api/v1/workflows/{off_id}/enabled",
                    headers=h,
                    json={"enabled": False},
                )
                assert toggle_admin.status_code == 200 and toggle_admin.json()["enabled"] is False
                assert client.get(f"/api/v1/workflows/{off_id}", headers=h).json()["enabled"] is False
                assert client.delete(f"/api/v1/workflows/{off_id}", headers=h).status_code == 200
                assert client.get(f"/api/v1/workflows/{off_id}", headers=h).status_code == 404
        finally:
            cleanup("wf-admin@example.com", "wf-user@example.com")
            cleanup_workflows(wf_on, wf_off)


# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------

class TestWorkflowRun:
    def test_run_template_flow(self):
        wf_name = "wf-run-模板流"
        cleanup("wf-admin@example.com", "wf-user@example.com")
        cleanup_workflows(wf_name)
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                user = _token("wf-user@example.com")
                h = {"Authorization": f"Bearer {admin}"}
                wf_id = client.post("/api/v1/workflows", headers=h, json={
                    "name": wf_name, "graph": TEMPLATE_GRAPH, "enabled": True,
                }).json()["id"]

                # 未登录不可运行（无 token）
                assert client.post(f"/api/v1/workflows/{wf_id}/run", json={}).status_code == 401

                resp = client.post(
                    f"/api/v1/workflows/{wf_id}/run",
                    headers={"Authorization": f"Bearer {user}"},
                    json={"inputs": {"name": "小 AG"}},
                )
                assert resp.status_code == 200, resp.text
                submitted = resp.json()
                assert submitted["status"] == "running", "提交应立即返回 running（后台执行）"
                body = _wait_run(
                    client, submitted["id"], {"Authorization": f"Bearer {user}"},
                    statuses={"succeeded", "failed"},
                )
                assert body["status"] == "succeeded", body
                assert body["outputs"] == "你好 小 AG"
                steps = {s["node_id"]: s["status"] for s in body["steps"]}
                assert steps == {"start": "done", "t": "done", "end": "done"}

                # 运行记录可见性：管理员能看到普通用户的 run
                runs = client.get(f"/api/v1/workflows/{wf_id}/runs", headers=h).json()
                assert runs["total"] >= 1
        finally:
            cleanup("wf-admin@example.com", "wf-user@example.com")
            cleanup_workflows(wf_name)

    def test_run_disabled_blocked_for_user_allowed_for_admin(self):
        wf_name = "wf-run-停用流"
        cleanup("wf-admin@example.com", "wf-user@example.com")
        cleanup_workflows(wf_name)
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                user = _token("wf-user@example.com")
                h = {"Authorization": f"Bearer {admin}"}
                wf_id = client.post("/api/v1/workflows", headers=h, json={
                    "name": wf_name, "graph": TEMPLATE_GRAPH, "enabled": False,
                }).json()["id"]
                assert client.post(
                    f"/api/v1/workflows/{wf_id}/run",
                    headers={"Authorization": f"Bearer {user}"}, json={"inputs": {}},
                ).status_code == 403
                ok = client.post(
                    f"/api/v1/workflows/{wf_id}/run", headers=h, json={"inputs": {"name": "x"}}
                )
                assert ok.status_code == 200
                done = _wait_run(client, ok.json()["id"], h, statuses={"succeeded", "failed"})
                assert done["status"] == "succeeded"
        finally:
            cleanup("wf-admin@example.com", "wf-user@example.com")
            cleanup_workflows(wf_name)

    def test_run_with_llm_node_uses_factory(self):
        """LLM 节点端到端：走 llm_factory（假网关），产出到 outputs。"""
        wf_name = "wf-run-llm流"
        cleanup("wf-admin@example.com")
        cleanup_workflows(wf_name)
        graph = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "n", "type": "llm", "params": {"prompt": "总结 {{inputs.topic}}"}},
                {"id": "end", "type": "end", "params": {"output": "{{nodes.n.output}}"}},
            ],
            "edges": [
                {"from": "start", "to": "n"},
                {"from": "n", "to": "end"},
            ],
        }
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                h = {"Authorization": f"Bearer {admin}"}
                wf_id = client.post("/api/v1/workflows", headers=h, json={
                    "name": wf_name, "graph": graph, "enabled": True,
                }).json()["id"]
                with patch("app.services.llm_factory.build_llm", return_value=FakeGateway()):
                    resp = client.post(
                        f"/api/v1/workflows/{wf_id}/run", headers=h,
                        json={"inputs": {"topic": "工作流"}},
                    )
                assert resp.status_code == 200, resp.text
                body = _wait_run(client, resp.json()["id"], h, statuses={"succeeded", "failed"})
                assert body["status"] == "succeeded", body
                assert body["outputs"] == "假回答"
        finally:
            cleanup("wf-admin@example.com")
            cleanup_workflows(wf_name)

    def test_run_unknown_variable_fails_with_node_error(self):
        wf_name = "wf-run-缺变量"
        cleanup("wf-admin@example.com")
        cleanup_workflows(wf_name)
        graph = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "t", "type": "template", "params": {"template": "{{inputs.missing}}"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "t"},
                {"from": "t", "to": "end"},
            ],
        }
        try:
            with TestClient(app) as client:
                admin = _token("wf-admin@example.com", role="admin")
                h = {"Authorization": f"Bearer {admin}"}
                wf_id = client.post("/api/v1/workflows", headers=h, json={
                    "name": wf_name, "graph": graph, "enabled": True,
                }).json()["id"]
                resp = client.post(
                    f"/api/v1/workflows/{wf_id}/run", headers=h, json={"inputs": {}}
                )
                assert resp.status_code == 200  # 运行本身被受理
                body = _wait_run(client, resp.json()["id"], h, statuses={"succeeded", "failed"})
                assert body["status"] == "failed"
                assert "t" in (body["error"] or ""), body["error"]
                failed_steps = [s for s in body["steps"] if s["status"] == "failed"]
                assert failed_steps and failed_steps[0]["node_id"] == "t"
        finally:
            cleanup("wf-admin@example.com")
            cleanup_workflows(wf_name)


# ---------------------------------------------------------------------------
# 人工输入：暂停 → 恢复 → 防护
# ---------------------------------------------------------------------------

class TestHumanInputRun:
    def test_pause_resume_and_guards(self):
        wf_name = "wf-人工输入"
        cleanup("wf-owner@example.com", "wf-other@example.com")
        cleanup_workflows(wf_name)
        try:
            with TestClient(app) as client:
                owner = _token("wf-owner@example.com")
                other = _token("wf-other@example.com")
                admin = _token("wf-admin@example.com", role="admin")
                h = {"Authorization": f"Bearer {admin}"}
                wf_id = client.post("/api/v1/workflows", headers=h, json={
                    "name": wf_name, "graph": HUMAN_GRAPH, "enabled": True,
                }).json()["id"]

                # 运行 → 暂停等待人工输入
                resp = client.post(
                    f"/api/v1/workflows/{wf_id}/run",
                    headers={"Authorization": f"Bearer {owner}"},
                    json={"inputs": {}},
                )
                assert resp.status_code == 200, resp.text
                submitted = resp.json()
                assert submitted["status"] == "running", "提交应立即返回 running"
                body = _wait_run(
                    client, submitted["id"], {"Authorization": f"Bearer {owner}"},
                    statuses={"waiting_input", "succeeded", "failed"},
                )
                assert body["status"] == "waiting_input", body
                assert body["waiting_prompt"] == "请确认发布"
                run_id = body["id"]

                # 他人不可见/不可恢复
                assert client.get(
                    f"/api/v1/workflows/runs/{run_id}",
                    headers={"Authorization": f"Bearer {other}"},
                ).status_code == 403
                assert client.post(
                    f"/api/v1/workflows/runs/{run_id}/resume",
                    headers={"Authorization": f"Bearer {other}"},
                    json={"value": "x"},
                ).status_code == 403

                # 管理员可恢复（触发者本人也可以 —— 这里用 admin 验证豁免通道）
                resume = client.post(
                    f"/api/v1/workflows/runs/{run_id}/resume",
                    headers=h,
                    json={"value": {"confirmed": True}},
                )
                assert resume.status_code == 200, resume.text
                resumed_submit = resume.json()
                assert resumed_submit["status"] == "running", "恢复提交应立即返回 running"
                resumed = _wait_run(client, resumed_submit["id"], h, statuses={"succeeded", "failed"})
                assert resumed["status"] == "succeeded", resumed
                assert resumed["outputs"] == {"confirmed": True}

                # 已结束的 run 不能再次恢复
                again = client.post(
                    f"/api/v1/workflows/runs/{run_id}/resume", headers=h, json={"value": "y"}
                )
                assert again.status_code == 409

                # 非等待状态的 run 详情：本人可见
                detail = client.get(
                    f"/api/v1/workflows/runs/{run_id}",
                    headers={"Authorization": f"Bearer {owner}"},
                )
                assert detail.status_code == 200
        finally:
            cleanup("wf-owner@example.com", "wf-other@example.com", "wf-admin@example.com")
            cleanup_workflows(wf_name)

    def test_resume_requires_waiting_status(self):
        """直接对 running/succeeded run 调 resume → 409（不进入恢复逻辑）。"""
        wf_name = "wf-恢复状态守卫"
        cleanup("wf-owner@example.com")
        cleanup_workflows(wf_name)
        try:
            with TestClient(app) as client:
                owner = _token("wf-owner@example.com")
                admin = _token("wf-admin@example.com", role="admin")
                h = {"Authorization": f"Bearer {admin}"}
                wf_id = client.post("/api/v1/workflows", headers=h, json={
                    "name": wf_name, "graph": TEMPLATE_GRAPH, "enabled": True,
                }).json()["id"]
                done_submit = client.post(
                    f"/api/v1/workflows/{wf_id}/run",
                    headers={"Authorization": f"Bearer {owner}"}, json={"inputs": {"name": "a"}},
                ).json()
                done_run = _wait_run(
                    client, done_submit["id"], h, statuses={"succeeded", "failed"}
                )
                assert done_run["status"] == "succeeded"
                resp = client.post(
                    f"/api/v1/workflows/runs/{done_run['id']}/resume",
                    headers=h, json={"value": "x"},
                )
                assert resp.status_code == 409
        finally:
            cleanup("wf-owner@example.com", "wf-admin@example.com")
            cleanup_workflows(wf_name)


class TestZombieCleanup:
    def test_running_runs_marked_failed_on_restart(self):
        """进程重启收尸：running 的 workflow run 标记为 failed("restart")；
        waiting_input 不收 —— 暂停点持久化在 DB，重启后照常可恢复。"""
        from app.services.startup_cleanup import mark_interrupted_runs

        with create_db_session() as db:
            wf_row = WorkflowModel(
                name="wf-收尸",
                graph_json=json.dumps(TEMPLATE_GRAPH, ensure_ascii=False),
                enabled=True,
            )
            db.add(wf_row)
            db.commit()
            wf_id = wf_row.id
        try:
            with create_db_session() as db:
                zombie = WorkflowRunModel(
                    workflow_id=wf_id, status="running",
                    inputs_json="{}", steps_json="[]", context_json="{}",
                )
                paused = WorkflowRunModel(
                    workflow_id=wf_id, status="waiting_input",
                    waiting_node_id="ask", waiting_prompt="确认？",
                    inputs_json="{}", steps_json="[]", context_json="{}",
                )
                db.add_all([zombie, paused])
                db.commit()
                zombie_id, paused_id = zombie.id, paused.id

            counts = asyncio.run(asyncio.to_thread(mark_interrupted_runs))
            assert counts["workflow_runs"] >= 1

            with create_db_session() as db:
                assert db.get(WorkflowRunModel, zombie_id).status == "failed"
                assert "restart" in (db.get(WorkflowRunModel, zombie_id).error or "")
                assert db.get(WorkflowRunModel, paused_id).status == "waiting_input", (
                    "人工输入暂停点必须能跨重启恢复，不能被收尸"
                )
        finally:
            cleanup_workflows("wf-收尸")


def _unused_asyncio_guard():  # pragma: no cover
    # asyncio 引用保留给未来异步用例；避免误删 import
    return asyncio
