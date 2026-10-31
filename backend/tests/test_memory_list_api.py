"""记忆列表分页 / total / 关键词过滤回归。

背景：管理后台「记忆管理」面板此前一次性拉全量（默认 200 条），
没有分页也没有服务端搜索 —— 记忆多了之后既慢又没法定位某一条
（用户要找"ORION"那条幻觉记忆，只能肉眼翻）。本次给 GET /memory
补齐 q 过滤 + total，前端才能做真分页。
"""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.models import MemoryModel, UserModel
from app.db.session import create_db_session
from app.main import app

client = TestClient(app)


def _register_and_login() -> tuple[int, str, dict[str, str]]:
    email = f"mem-{uuid4().hex[:10]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Mem Tester", "password": "password-123"},
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    return payload["user"]["id"], email, {"Authorization": f"Bearer {payload['access_token']}"}


def _create_memory(headers: dict[str, str], content: str) -> None:
    resp = client.post(
        "/api/v1/memory",
        json={"content": content, "memory_type": "fact", "importance": 0.6},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


def _cleanup(emails: list[str]) -> None:
    with create_db_session() as db:
        user_ids = db.scalars(select(UserModel.id).where(UserModel.email.in_(emails))).all()
        if user_ids:
            db.execute(delete(MemoryModel).where(MemoryModel.user_id.in_(user_ids)))
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def test_list_memories_pagination_total_and_search() -> None:
    """分页窗口、total 全量计数、q 关键词过滤都要在服务端生效。"""
    user_id, email, headers = _register_and_login()
    try:
        for i in range(5):
            _create_memory(headers, f"用户喜欢用 Python 写脚本 {i}")
        _create_memory(headers, "项目代号为 ORION 的任务分布")

        # 全量：total = 6
        full = client.get("/api/v1/memory?limit=20", headers=headers).json()
        assert full["total"] == 6
        assert full["count"] == 6
        assert len(full["items"]) == 6

        # 分页：limit=2, offset=0/2，两页不重叠，total 保持全量
        page1 = client.get("/api/v1/memory?limit=2&offset=0", headers=headers).json()
        page2 = client.get("/api/v1/memory?limit=2&offset=2", headers=headers).json()
        assert page1["total"] == 6 and len(page1["items"]) == 2
        assert page2["total"] == 6 and len(page2["items"]) == 2
        assert {m["id"] for m in page1["items"]}.isdisjoint({m["id"] for m in page2["items"]})

        # 关键词过滤：q=ORION 只剩 1 条，total 也要跟着缩小
        hit = client.get("/api/v1/memory?q=ORION", headers=headers).json()
        assert hit["total"] == 1
        assert len(hit["items"]) == 1
        assert "ORION" in hit["items"][0]["content"]

        # 过滤 + 分页叠加：q=Python 共 5 条，第二页只剩 1 条
        py2 = client.get("/api/v1/memory?q=Python&limit=4&offset=4", headers=headers).json()
        assert py2["total"] == 5
        assert len(py2["items"]) == 1

        # 普通用户看不到别人的记忆
        _, other_email, other_headers = _register_and_login()
        other_view = client.get("/api/v1/memory", headers=other_headers).json()
        assert other_view["total"] == 0
        _cleanup([other_email])
    finally:
        _cleanup([email])


def test_admin_sees_all_users_and_can_filter_by_user() -> None:
    """管理员：total 覆盖所有用户；user_id 参数把范围缩到单个用户。"""
    user_a, email_a, headers_a = _register_and_login()
    user_b, email_b, headers_b = _register_and_login()
    try:
        _create_memory(headers_a, "甲的记忆条目")
        _create_memory(headers_a, "甲的 ORION 项目记忆")
        _create_memory(headers_b, "乙的记忆条目")

        # user_a 升级为 admin（token 只含 user id，角色查库，无需重登）
        with create_db_session() as db:
            db.get(UserModel, user_a).role = "admin"
            db.commit()

        admin_all = client.get("/api/v1/memory?limit=50", headers=headers_a).json()
        assert admin_all["total"] == 3

        admin_b = client.get(f"/api/v1/memory?user_id={user_b}", headers=headers_a).json()
        assert admin_b["total"] == 1
        assert admin_b["items"][0]["content"] == "乙的记忆条目"
        assert admin_b["items"][0]["user_id"] == user_b

        admin_hit = client.get("/api/v1/memory?q=ORION", headers=headers_a).json()
        assert admin_hit["total"] == 1
        assert "ORION" in admin_hit["items"][0]["content"]
    finally:
        _cleanup([email_a, email_b])


def test_batch_delete_memories() -> None:
    """批量删除：全部成功返回 deleted 数；越界/他人 id 进 missing 而不是整批 404。"""
    user_id, email, headers = _register_and_login()
    try:
        for i in range(3):
            _create_memory(headers, f"待清理记忆 {i}")

        ids = [
            m["id"]
            for m in client.get("/api/v1/memory?limit=10", headers=headers).json()["items"]
        ]
        assert len(ids) == 3

        # 混入一个不存在的 id
        resp = client.post(
            "/api/v1/memory/batch-delete",
            json={"ids": ids + [999999]},
            headers=headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["deleted"] == 3
        assert payload["missing"] == [999999]

        remaining = client.get("/api/v1/memory", headers=headers).json()
        assert remaining["total"] == 0
    finally:
        _cleanup([email])


def test_batch_delete_rejects_other_users_memories() -> None:
    """普通用户不能批量删别人的记忆。"""
    _, owner_email, owner_headers = _register_and_login()
    user_x, email_x, headers_x = _register_and_login()
    try:
        _create_memory(owner_headers, "属于甲的记忆")
        target_id = client.get("/api/v1/memory", headers=owner_headers).json()["items"][0]["id"]

        resp = client.post("/api/v1/memory/batch-delete", json={"ids": [target_id]}, headers=headers_x)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0
        assert resp.json()["missing"] == [target_id]

        still_there = client.get("/api/v1/memory", headers=owner_headers).json()
        assert still_there["total"] == 1
    finally:
        _cleanup([owner_email, email_x])
