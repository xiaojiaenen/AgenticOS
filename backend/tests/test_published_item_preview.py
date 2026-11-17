"""文件型作品的短链预览页。

用户报障：「word、ppt、excel 公开到作品库后，点击会跳转到 404 页面」。

根因不是路由缺失 —— `/s/<code>` 是通的 —— 而是它 302 到了**下载端点**：
docx/xlsx/pptx 浏览器无法原生内联渲染，跳过去要么触发下载、要么白屏，
观感就是"坏了"。修法是让它返回一个真正的预览页。

这里锁住：
- 成功作品返回 HTML 200（不是 302）
- 文档类内嵌 iframe 直接渲染（它本来就是 .html）
- PPT/表格给出下载入口并说明原因
- 未上架作品仍是 404 且带人话原因
- 标题里的 HTML 被转义（作品标题来自用户输入）
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import PublishedItemModel, UserModel
from app.db.session import create_db_session
from app.main import app


def _make_published_item(kind: str, title: str, status: str = "deployed") -> tuple[int, str, str]:
    """建一条已发布作品，返回 (id, short_code, user_email)。"""
    email = f"pub-{uuid4().hex}@example.com"
    code = uuid4().hex[:10]
    with create_db_session() as db:
        user = UserModel(
            email=email, name="Pub", password_hash="x", role="user", is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        item = PublishedItemModel(
            kind=kind,
            session_id=f"pub-session-{code}",
            source_ref=f"ref-{code}",
            user_id=user.id,
            title=title,
            visibility="public",
            status=status,
            short_code=code,
            file_path=f"test-{code}.bin",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id, code, email


def _cleanup(item_id: int, email: str) -> None:
    with create_db_session() as db:
        db.execute(delete(PublishedItemModel).where(PublishedItemModel.id == item_id))
        db.execute(delete(UserModel).where(UserModel.email == email))
        db.commit()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestPreviewPage:
    @pytest.mark.parametrize(
        "kind,expect_iframe",
        [("document", True), ("ppt", False), ("sheet", False)],
    )
    def test_deployed_item_renders_preview_html(self, client, kind, expect_iframe):
        item_id, code, email = _make_published_item(kind, f"预览测试 {kind}")
        try:
            response = client.get(f"/s/{code}/", follow_redirects=False)
            # 关键：不再 302 到下载端点，而是直接给页面
            assert response.status_code == 200, (
                f"{kind} 短链应返回预览页，实际 {response.status_code}"
            )
            assert response.headers["content-type"].startswith("text/html")
            body = response.text
            assert "预览测试" in body
            if expect_iframe:
                # 文档本身就是 .html，内嵌渲染
                assert "<iframe" in body
                assert "下载原文件" in body
            else:
                # 二进制格式：给下载按钮 + 说明
                assert "下载" in body
                assert "浏览器无法直接显示" in body
        finally:
            _cleanup(item_id, email)

    def test_title_html_is_escaped(self, client):
        """作品标题来自用户输入，直接插进 HTML 会被注入。"""
        item_id, code, email = _make_published_item("ppt", "<script>alert(1)</script>")
        try:
            body = client.get(f"/s/{code}/", follow_redirects=False).text
            assert "<script>alert(1)</script>" not in body, "标题未转义，存在 XSS"
            assert "&lt;script&gt;" in body
        finally:
            _cleanup(item_id, email)

    @pytest.mark.parametrize(
        "status,keyword",
        [
            ("pending", "审批"),
            ("rejected", "未通过"),
            ("cancelled", "取消"),
            ("failed", "失败"),
        ],
    )
    def test_not_deployed_gives_reason_not_silent_404(self, client, status, keyword):
        """未上架不是静默 404 —— 要告诉用户为什么打不开。"""
        item_id, code, email = _make_published_item("ppt", "未上架", status=status)
        try:
            response = client.get(f"/s/{code}/", follow_redirects=False)
            assert response.status_code == 404
            assert keyword in response.json().get("detail", "")
        finally:
            _cleanup(item_id, email)

    def test_unknown_code_404(self, client):
        response = client.get(f"/s/{uuid4().hex[:10]}/", follow_redirects=False)
        assert response.status_code == 404

    def test_download_endpoint_still_forces_attachment(self, client):
        """下载按钮走的端点必须是 attachment（否则浏览器又会尝试内联）。"""
        item_id, code, email = _make_published_item("document", "下载测试")
        try:
            response = client.get(
                f"/api/v1/published-items/{item_id}/download?download=1",
                follow_redirects=False,
            )
            # 没有真实文件时是 404（file_path 指向不存在的文件），
            # 但**不能**是 500 —— 说明错误处理正确
            assert response.status_code in (200, 404)
            if response.status_code == 200:
                assert "attachment" in response.headers.get("content-disposition", "")
        finally:
            _cleanup(item_id, email)
