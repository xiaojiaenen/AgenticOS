"""上游自动登录 — 与 sesame `auto_login_service.py` 保持一致。

唯一上游: https://agents.gree.com
登录页由 UPSTREAM_LOGIN_URL 配置（应与 sesame AI_ASSISTANT_LOGIN_URL 相同）。

Returns:
    (success, message, cookie_string, earliest_expire)
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger("agenticos.upstream.auto_login")

MAX_RETRIES = 2
GOTO_TIMEOUT = 60000
IDLE_TIMEOUT = 30000

# 认证相关 cookie 名称关键词（大小写不敏感匹配）
_AUTH_COOKIE_KEYWORDS = {
    "session", "token", "auth", "sid", "jwt", "sso", "login", "user",
    "credential", "access", "refresh", "ticket", "bearer", "cookie",
    "phpsessid", "jsessionid", "asp.net", "connect.sid",
}

# 应该排除的短命 cookie 关键词（通常是跟踪/分析 cookie）
_TRACKING_COOKIE_KEYWORDS = {
    "_ga", "_gid", "_fbp", "_fbc", "utm_", "gclid", "fbclid",
    "_gcl", "msclkid", "tt_", "li_", "bcookie",
}

# 最小 cookie 有效期（小时），低于此值的过期时间会被忽略
MIN_COOKIE_EXPIRE_HOURS = 24


async def login_with_credentials(
    login_url: str,
    username: str,
    password: str,
) -> tuple[bool, str, Optional[str], Optional[datetime]]:
    """
    使用 Playwright 打开浏览器，自动填写账号密码登录，提取 Cookie。

    Returns:
        (success, message, cookie_string, earliest_expire)
    """
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            success, msg, cookie, expire = await _do_login(login_url, username, password)
            if success:
                return True, msg, cookie, expire
            last_error = msg
            # 表单识别失败不需要重试
            if "未找到" in msg:
                return False, msg, None, None
            if attempt < MAX_RETRIES:
                logger.info(f"Auto login attempt {attempt} failed: {msg}, retrying...")
                await asyncio.sleep(2)
        except Exception as e:
            last_error = _friendly_error(e)
            logger.warning(f"Auto login attempt {attempt} error: {type(e).__name__}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2)

    return False, last_error, None, None


async def _do_login(
    login_url: str,
    username: str,
    password: str,
) -> tuple[bool, str, Optional[str], Optional[datetime]]:
    """单次登录尝试"""
    async with async_playwright() as p:
        chrome_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
        launch_opts = {"headless": True}
        if chrome_path and os.path.exists(chrome_path):
            launch_opts["executable_path"] = chrome_path
        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(login_url, wait_until="networkidle", timeout=GOTO_TIMEOUT)

        # 自动识别用户名输入框
        username_input = await _find_username_input(page)
        if not username_input:
            await browser.close()
            return False, "未找到用户名输入框，请检查登录地址是否正确", None, None

        # 自动识别密码输入框
        password_input = await page.query_selector('input[type="password"]')
        if not password_input:
            await browser.close()
            return False, "未找到密码输入框，请检查登录地址是否正确", None, None

        # 填写表单
        await username_input.fill(username)
        await password_input.fill(password)

        # 提交：优先找提交按钮，否则回车
        submit_btn = await _find_submit_button(page)
        if submit_btn:
            await submit_btn.click()
        else:
            await password_input.press("Enter")

        # 等待导航完成
        await page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT)
        await asyncio.sleep(1)  # 等待 JS 设置 cookie

        # 提取所有 cookie
        cookies = await context.cookies()
        await browser.close()

        if not cookies:
            return False, "登录成功但未获取到 Cookie，请检查账号密码是否正确", None, None

        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        # 智能计算 cookie 有效期：只看认证相关 cookie，排除短命 tracking cookie
        from app.core.timezone import app_now

        now = app_now()
        earliest = None

        for c in cookies:
            name_lower = c["name"].lower()
            exp = c.get("expires", -1)

            # 跳过 session cookie（expires=-1 或 0 表示会话结束即过期）
            if exp <= 0:
                continue

            # 跳过已过期的 cookie
            dt = datetime.fromtimestamp(exp, tz=now.tzinfo).replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None) if now.tzinfo else now
            if dt <= now_naive:
                continue

            # 跳过明确的 tracking/分析 cookie
            if any(kw in name_lower for kw in _TRACKING_COOKIE_KEYWORDS):
                continue

            # 只考虑认证相关 cookie，或有效期 > 1 小时的未知 cookie
            is_auth = any(kw in name_lower for kw in _AUTH_COOKIE_KEYWORDS)
            hours_left = (dt - now_naive).total_seconds() / 3600

            if is_auth or hours_left > 1:
                if earliest is None or dt < earliest:
                    earliest = dt

        # 兜底：如果没找到有意义的过期时间，使用最小有效期
        if earliest is None:
            earliest = now_naive + timedelta(hours=MIN_COOKIE_EXPIRE_HOURS)
            logger.info(f"Cookie 过期时间过短或未找到，使用最小有效期: {MIN_COOKIE_EXPIRE_HOURS}h")
        elif (earliest - now_naive).total_seconds() < MIN_COOKIE_EXPIRE_HOURS * 3600:
            earliest = now_naive + timedelta(hours=MIN_COOKIE_EXPIRE_HOURS)
            logger.info(f"Cookie 过期时间过短或未找到，使用最小有效期: {MIN_COOKIE_EXPIRE_HOURS}h")

        return True, "登录成功", cookie_str, earliest


def _friendly_error(e: Exception) -> str:
    """将 Playwright 异常转换为用户友好的错误信息"""
    err_str = str(e).lower()
    if "timeout" in err_str or "timed out" in err_str:
        return "登录超时，请检查网络连接或登录地址是否正确"
    if "net::err_name_not_resolved" in err_str:
        return "无法访问登录地址，请检查网址是否正确"
    if "net::err_connection_refused" in err_str:
        return "连接被拒绝，请检查登录地址是否可用"
    if "net::err_connection_timed_out" in err_str:
        return "连接超时，请检查网络连接"
    if "navigation failed" in err_str:
        return "页面加载失败，请检查登录地址是否正确"
    if "browser" in err_str and "launch" in err_str:
        return "浏览器启动失败，请联系管理员"
    return "登录失败，请稍后重试"


async def _find_username_input(page):
    """智能识别用户名输入框"""
    # 优先级从高到低
    selectors = [
        '#UserIDShort',
        'input[name="username"]',
        'input[name="account"]',
        'input[name="user"]',
        'input[name="email"]',
        'input[name="loginId"]',
        'input[name="userId"]',
        'input[type="email"]',
        'input[type="text"][autocomplete="username"]',
        'input[type="tel"]',
    ]
    for sel in selectors:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            return el

    # 兜底：密码框前面的第一个可见 text/email/tel input
    password = await page.query_selector('input[type="password"]')
    if password:
        all_inputs = await page.query_selector_all(
            'input[type="text"], input[type="email"], input[type="tel"], input:not([type])'
        )
        for inp in all_inputs:
            if await inp.is_visible():
                bbox = await inp.bounding_box()
                pwd_box = await password.bounding_box()
                if bbox and pwd_box and bbox["y"] < pwd_box["y"]:
                    return inp

    return None


async def _find_submit_button(page):
    """智能识别登录按钮"""
    selectors = [
        '#modalButton',
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("登录")',
        'button:has-text("Login")',
        'button:has-text("Sign in")',
        'button:has-text("提交")',
    ]
    for sel in selectors:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            return el
    return None
