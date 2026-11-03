"""UI e2e 测试的 fixture：真实浏览器 + 登录会话。"""
from __future__ import annotations

import re as _re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

FRONTEND = "http://127.0.0.1:3001"
ADMIN_EMAIL = "tester@agenticos.dev"
USER_EMAIL = "user@agenticos.dev"
PASSWORD = "test123456"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        yield b
        b.close()


def _login_page(browser: Browser, email: str) -> Page:
    ctx: BrowserContext = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"{FRONTEND}/login")
    page.get_by_label("邮箱地址").fill(email)
    page.get_by_label("密码", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="进入工作台").click()
    _wait_left_login(page)
    return page


def _wait_left_login(page: Page, timeout_ms: int = 45_000) -> None:
    """等登录跳转完成。

    不能用 wait_for_url：登录成功时导航往往在 click() 返回前就完成了，
    wait_for_url 再挂上去只会等「下一次」导航，必然超时。这里显式轮询 URL。
    """
    import time

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if "/login" not in page.url:
            return
        page.wait_for_timeout(250)
    raise AssertionError(f"登录未跳转，仍停留在 {page.url}")


@pytest.fixture()
def page(browser: Browser):
    """未登录的空白页。"""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    p = ctx.new_page()
    yield p
    ctx.close()


@pytest.fixture()
def page_admin(browser: Browser):
    p = _login_page(browser, ADMIN_EMAIL)
    yield p
    p.context.close()


@pytest.fixture()
def page_user(browser: Browser):
    p = _login_page(browser, USER_EMAIL)
    yield p
    p.context.close()
