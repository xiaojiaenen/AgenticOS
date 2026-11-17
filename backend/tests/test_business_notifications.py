"""业务邮件通知回归（部署通过 / 反馈回复 / 文件作品通过）。

覆盖的关键点：

- 没有配置 SMTP 凭据时**静默跳过**（不抛异常、不阻断审批）；
- 部署通过邮件**内嵌封面图**（MIME related + Content-ID，cid:cover）；
- 中文标题与正文不因编码问题炸掉；
- 反馈回复通知带上回复正文与状态。

测试不真发邮件：用 monkeypatch 替换 ``send_notification_email``，
断言调用参数（收件人 / 主题 / 正文 / 内嵌图片）。
"""
from __future__ import annotations

import pytest

from app.services import business_notifications as bn


@pytest.fixture()
def captured(monkeypatch):
    """替换底层发信函数，捕获调用参数。"""
    calls: list[dict] = []

    async def _fake_send(creds, to, subject, html, is_html=False, inline_image=None):
        calls.append({
            "to": to,
            "subject": subject,
            "html": html,
            "is_html": is_html,
            "inline_image": inline_image,
        })
        return True

    monkeypatch.setattr(bn, "_creds", lambda: object())
    monkeypatch.setattr(
        "app.tools.email_tools.send_notification_email", _fake_send
    )
    return calls


@pytest.fixture()
def no_creds(monkeypatch):
    """没有 SMTP 凭据的环境。"""
    monkeypatch.setattr(bn, "_creds", lambda: None)


@pytest.mark.anyio
async def test_deploy_approved_skips_without_credentials(no_creds):
    """没配 SMTP 时静默返回 False（不抛异常）。"""
    result = await bn.notify_deploy_approved(
        user_email="a@example.com",
        user_name="A",
        title="我的网站",
        project_slug="u1_s2_v1",
        visibility="public",
        short_url="/s/abc/",
    )
    assert result is False


@pytest.mark.anyio
async def test_deploy_approved_sends_with_cover(captured, monkeypatch, tmp_path):
    """部署通过邮件带封面（cid:cover）与访问地址。"""
    # _read_cover 从 DATA_DIR / "website-covers" 读，monkeypatch DATA_DIR 即可
    cover_dir = tmp_path / "website-covers"
    cover_dir.mkdir()
    (cover_dir / "u1_s2_v1.webp").write_bytes(b"RIFF-fake-webp")
    monkeypatch.setattr("app.core.data_path.DATA_DIR", tmp_path)

    result = await bn.notify_deploy_approved(
        user_email="a@example.com",
        user_name="A",
        title="我的网站",
        project_slug="u1_s2_v1",
        visibility="public",
        short_url="/s/abc/",
        description="一个示例网站",
    )
    assert result is True
    assert len(captured) == 1
    call = captured[0]
    assert call["to"] == "a@example.com"
    assert "我的网站" in call["subject"]
    assert "cid:cover" in call["html"]
    assert call["inline_image"] is not None
    assert call["inline_image"][0] == "cover"
    assert call["inline_image"][2] == "image/webp"


@pytest.mark.anyio
async def test_feedback_reply_includes_body(captured):
    """反馈回复通知带上回复正文与状态。"""
    result = await bn.notify_feedback_reply(
        user_email="b@example.com",
        issue_title="按钮点不动",
        reply_text="已修复，请刷新页面重试。",
        status_label="已处理",
        issue_id=42,
        actor_name="管理员",
    )
    assert result is True
    call = captured[0]
    assert call["to"] == "b@example.com"
    assert "按钮点不动" in call["subject"]
    assert "已修复，请刷新页面重试。" in call["html"]
    assert "已处理" in call["html"]


@pytest.mark.anyio
async def test_published_item_approved_sends(captured):
    """文件型作品通过后通知作者。"""
    result = await bn.notify_published_item_approved(
        user_email="c@example.com",
        title="季度汇报",
        kind_label="演示文稿",
        short_url="/s/xyz/",
        description="十二页的季度汇报",
    )
    assert result is True
    call = captured[0]
    assert "季度汇报" in call["subject"]
    assert "演示文稿" in call["html"]
    assert "十二页的季度汇报" in call["html"]
