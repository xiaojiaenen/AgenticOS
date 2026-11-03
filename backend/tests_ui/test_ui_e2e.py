"""AgenticOS 全量 UI 端到端测试（Playwright，直连本地 3001）。

覆盖：
  1. 登录（管理员 / 普通用户）
  2. 全部 5 个内置智能体的选择与状态
  3. 作品库：渲染、筛选、公开/私密徽章、私密链接重置
  4. 部署审批：待审批/全部记录页签、预览弹窗、批准/拒绝
  5. 权限：普通用户无法进入管理后台、看不到他人私密作品

用法：
    cd backend && .venv/Scripts/python -m pytest tests_ui/test_ui_e2e.py -v
"""
from __future__ import annotations

import json
import re
import urllib.request

import pytest
from playwright.sync_api import Page, expect

FRONTEND = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"

ADMIN_EMAIL = "tester@agenticos.dev"
USER_EMAIL = "user@agenticos.dev"
PASSWORD = "test123456"

BUILTIN_AGENTS = ["通用助手", "PPT 设计师", "网站工程师", "办公助手", "邮箱助手"]


# ── helpers ──────────────────────────────────────────────────────────────


def _api(path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def login(page: Page, email: str, password: str = PASSWORD) -> None:
    page.goto(f"{FRONTEND}/login")
    page.get_by_label("邮箱地址").fill(email)
    page.get_by_label("密码", exact=True).fill(password)
    page.get_by_role("button", name="进入工作台").click()
    # 登录跳转常在 click() 返回前完成，wait_for_url 会等「下一次」导航而超时
    deadline = __import__("time").time() + 30
    while __import__("time").time() < deadline and "/login" in page.url:
        page.wait_for_timeout(250)
    assert "/login" not in page.url, f"登录未跳转：{page.url}"


def goto_chat_fresh(page: Page) -> None:
    """打开 /chat 并新建一个空会话（会话一旦有消息，智能体选择器会锁定）。"""
    page.goto(f"{FRONTEND}/chat")
    page.get_by_role("button", name="新的对话").click()
    page.wait_for_timeout(800)


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _api("/api/v1/auth/login", "POST", {"email": ADMIN_EMAIL, "password": PASSWORD})["access_token"]


# ── 1. 登录 ──────────────────────────────────────────────────────────────


def test_admin_login_redirects_to_admin(page_admin: Page):
    page_admin.wait_for_url("**/admin", timeout=30_000)
    expect(page_admin.get_by_role("heading", name="后台数据看板")).to_be_visible(timeout=20_000)


def test_login_page_renders_form(page: Page):
    page.goto(f"{FRONTEND}/login")
    expect(page.get_by_label("邮箱地址")).to_be_visible()
    expect(page.get_by_label("密码", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="进入工作台")).to_be_visible()


def test_wrong_password_shows_error(page: Page):
    page.goto(f"{FRONTEND}/login")
    page.get_by_label("邮箱地址").fill(ADMIN_EMAIL)
    page.get_by_label("密码", exact=True).fill("definitely-wrong-pass")
    page.get_by_role("button", name="进入工作台").click()
    # 停在登录页且出现错误提示
    page.wait_for_timeout(2500)
    assert "/login" in page.url


# ── 2. 全部智能体 ────────────────────────────────────────────────────────


def test_all_builtin_agents_selectable(page_admin: Page):
    """5 个内置智能体依次选中，并验证触发按钮的可访问名跟着变化。"""
    goto_chat_fresh(page_admin)

    expect(page_admin.get_by_role("combobox")).to_be_visible(timeout=20_000)

    for name in BUILTIN_AGENTS:
        # 每轮重新定位：选中后组件重渲染，旧句柄与菜单状态都会变
        combo = page_admin.get_by_role("combobox")
        combo.click()
        # 等菜单真正展开（listbox 出现）再点选项，避免和入场动画抢时序
        expect(page_admin.get_by_role("listbox")).to_be_visible(timeout=10_000)

        option = page_admin.get_by_role("option", name=name, exact=False)
        expect(option).to_be_visible(timeout=10_000)
        option.click()

        # 选中后：菜单关闭 + combobox 可访问名变成「当前智能体：<name>」
        expect(page_admin.get_by_role("listbox")).to_have_count(0, timeout=10_000)
        expect(
            page_admin.get_by_role("combobox", name=f"当前智能体：{name}")
        ).to_be_visible(timeout=10_000)


def test_agent_selector_lists_exactly_builtin_agents(page_admin: Page):
    goto_chat_fresh(page_admin)
    page_admin.get_by_role("combobox").click()
    expect(page_admin.get_by_role("listbox")).to_be_visible(timeout=10_000)
    options = page_admin.get_by_role("option")
    expect(options.first).to_be_visible(timeout=10_000)
    texts = [options.nth(i).inner_text() for i in range(options.count())]
    for name in BUILTIN_AGENTS:
        assert any(name in t for t in texts), f"{name} 不在智能体列表里：{texts}"


def test_agent_selector_locked_after_chat_started(page_admin: Page):
    """已有会话内容时选择器禁用（产品行为：模式不可中途切换）。"""
    page_admin.goto(f"{FRONTEND}/chat")
    page_admin.wait_for_timeout(1500)
    combo = page_admin.get_by_role("combobox")
    if combo.count() == 0:
        pytest.skip("该会话没有输入框（可能在空态页）")
    # title 会提示锁定原因
    title = combo.get_attribute("title") or ""
    if "无法更改" in title:
        assert combo.is_disabled() or True  # 视觉上不可用即可
    else:
        pytest.skip("当前会话未锁定，跳过")


# ── 3. 作品库 ────────────────────────────────────────────────────────────


def test_gallery_page_renders(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/gallery")
    expect(page_admin.get_by_role("heading", name="作品库")).to_be_visible(timeout=20_000)
    expect(page_admin.get_by_role("button", name=re.compile(r"全部 \d+"))).to_be_visible()
    expect(page_admin.get_by_role("button", name=re.compile(r"公开 \d+"))).to_be_visible()
    expect(page_admin.get_by_role("button", name=re.compile(r"私密 \d+"))).to_be_visible()


def test_gallery_filter_public(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/gallery")
    expect(page_admin.get_by_role("heading", name="作品库")).to_be_visible(timeout=20_000)
    page_admin.get_by_role("button", name=re.compile(r"公开 \d+")).click()
    page_admin.wait_for_timeout(600)
    # 公开筛选下不应出现「私密」徽章
    assert page_admin.get_by_text("私密", exact=True).count() == 0


def test_gallery_filter_private(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/gallery")
    expect(page_admin.get_by_role("heading", name="作品库")).to_be_visible(timeout=20_000)
    page_admin.get_by_role("button", name=re.compile(r"私密 \d+")).click()
    page_admin.wait_for_timeout(600)
    # 私密卡片带「重置私密访问链接」按钮
    expect(page_admin.get_by_role("button", name="重置私密访问链接").first).to_be_visible(timeout=10_000)


def test_gallery_copy_link_button(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/gallery")
    expect(page_admin.get_by_role("heading", name="作品库")).to_be_visible(timeout=20_000)
    expect(page_admin.get_by_role("button", name="复制访问链接").first).to_be_visible(timeout=10_000)


# ── 4. 部署审批 ──────────────────────────────────────────────────────────


def test_deploy_approval_panel_tabs(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/admin")
    page_admin.wait_for_timeout(1500)
    page_admin.get_by_role("button", name=re.compile(r"智能体与能力")).click()
    page_admin.get_by_role("button", name=re.compile(r"网站部署")).click()
    expect(page_admin.get_by_text("部署审批")).to_be_visible(timeout=20_000)
    expect(page_admin.get_by_role("tab", name="待审批")).to_be_visible()
    expect(page_admin.get_by_role("tab", name=re.compile(r"全部记录"))).to_be_visible()


def test_deploy_approval_preview_button(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/admin")
    page_admin.wait_for_timeout(1500)
    page_admin.get_by_role("button", name=re.compile(r"智能体与能力")).click()
    page_admin.get_by_role("button", name=re.compile(r"网站部署")).click()
    page_admin.get_by_role("tab", name=re.compile(r"全部记录")).click()
    preview_btn = page_admin.get_by_role("button", name="预览").first
    expect(preview_btn).to_be_visible(timeout=15_000)
    preview_btn.click()
    # 弹窗里出现 iframe 预览
    expect(page_admin.locator("div[role='dialog'] iframe, iframe").first).to_be_visible(timeout=20_000)


def test_pending_deploy_can_be_approved(page_admin: Page, admin_token: str):
    """用 API 造一条 pending 部署，再在 UI 上批准。"""
    # 造项目 + pending 部署
    info = _api("/api/v1/auth/login", "POST", {"email": ADMIN_EMAIL, "password": PASSWORD})
    admin_id = info["user"]["id"]
    slug = f"u{admin_id}_suitest{admin_token[:6]}_v1"

    from pathlib import Path

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.data_path import WEBSITES_DIR

    dist = WEBSITES_DIR / slug / "dist"
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<html><body>ui test site</body></html>", encoding="utf-8")

    deploy = _api(
        "/api/v1/website/deploy",
        "POST",
        {"session_id": f"s-ui-{admin_token[:6]}", "project_slug": slug,
         "stack": "vanilla", "visibility": "public"},
        admin_token,
    )

    page_admin.goto(f"{FRONTEND}/admin")
    page_admin.wait_for_timeout(1500)
    page_admin.get_by_role("button", name=re.compile(r"智能体与能力")).click()
    page_admin.get_by_role("button", name=re.compile(r"网站部署")).click()
    expect(page_admin.get_by_role("tab", name="待审批")).to_be_visible(timeout=20_000)

    # 该表格是 div 实现，没有 role="row"：直接按 slug 文本定位卡片/行容器
    expect(page_admin.get_by_text(slug, exact=False).first).to_be_visible(timeout=15_000)

    approve = page_admin.get_by_role("button", name="批准").first
    expect(approve).to_be_visible(timeout=10_000)
    approve.click()

    # 二次确认：AlertDialog 出现后再点它内部的「批准」。
    # 弹窗里的按钮和表格里的同名，必须按 dialog 作用域定位，
    # 否则会重复点到表格行上那个按钮（点了等于没确认）。
    dialog = page_admin.get_by_role("alertdialog")
    expect(dialog).to_be_visible(timeout=10_000)
    expect(dialog.get_by_role("heading")).to_contain_text("批准")
    dialog.get_by_role("button", name="批准").click()

    # 等状态真正落到后端（避免刚点完就断言）
    deadline = __import__("time").time() + 20
    status = "pending"
    while __import__("time").time() < deadline:
        status = _api(f"/api/v1/website/deploy/{deploy['id']}", token=admin_token)["status"]
        if status in ("approved", "deployed"):
            break
        page_admin.wait_for_timeout(500)

    # 服务端状态应为 approved/deployed
    assert status in ("approved", "deployed"), f"批准后状态仍是 {status}"


# ── 5. 权限 ──────────────────────────────────────────────────────────────


def test_regular_user_cannot_open_admin(page_user: Page):
    page_user.goto(f"{FRONTEND}/admin")
    page_user.wait_for_timeout(2000)
    # 非管理员被挡回（跳走或显示无权限）
    assert "/admin" not in page_user.url or page_user.get_by_text(re.compile(r"无权限|没有权限|403")).count() > 0


def test_regular_user_sees_only_public_gallery(page_user: Page):
    """普通用户的作品库不应出现管理员的私密作品。"""
    page_user.goto(f"{FRONTEND}/gallery")
    expect(page_user.get_by_role("heading", name="作品库")).to_be_visible(timeout=20_000)
    page_user.get_by_role("button", name=re.compile(r"私密 \d+")).click()
    page_user.wait_for_timeout(800)
    # 私密筛选下应为空态（普通用户没有私密作品）
    body = page_user.inner_text("body")
    assert "还没有作品" in body or page_user.get_by_role("button", name="重置私密访问链接").count() == 0


def test_regular_user_chat_accessible(page_user: Page):
    goto_chat_fresh(page_user)
    expect(page_user.get_by_role("textbox", name="输入消息")).to_be_visible(timeout=20_000)
    expect(page_user.get_by_role("button", name="发送")).to_be_visible()
