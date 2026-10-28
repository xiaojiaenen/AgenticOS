"""企业网关的自动登录（Playwright 填表 → 提取 Cookie）。

上游（企业内网 AI 网关）没有 API Key 体系，只有浏览器登录态。这里用无头
Chromium 打开登录页、填账号密码、拿 Cookie，再把 Cookie 当作认证头去调上游。

设计取舍：

- **不在请求路径上同步登录**。登录要起浏览器、耗时数秒，塞进「构建 LLM」
  的热路径会让首字延迟不可控。登录只由管理端点或定时任务触发。
- **动作由 :class:`LoginFlow` 描述，不在代码里 if 厂商**。登录页是 SPA、
  按钮文案是「授权并登录」、会话 Cookie 由前端异步写入、证书自签 —— 这些
  差异全是从真实站点踩出来的，散在逻辑里会迅速长成一堆无法维护的分支。
- **失败要能诊断**。返回的是结构化结果（找不到输入框 / 超时 / 未拿到
  Cookie），而不是一句「登录失败」—— 排查上游改版时差别很大。
- **浏览器必须保证关闭**。旧实现几条 early-return 分支会漏掉 ``close()``，
  在容器里跑久了就是僵尸 Chromium 累积。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.timezone import app_now
from app.services.llm_providers import credentials
from app.services.llm_providers.presets import LoginFlow

logger = logging.getLogger("agenticos.llm.auto_login")

MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 2.0

# 认证相关 cookie 关键词：只有这些（或有效期足够长的未知 cookie）参与过期计算
_AUTH_COOKIE_KEYWORDS = {
    "session", "token", "auth", "sid", "jwt", "sso", "login", "user",
    "credential", "access", "refresh", "ticket", "bearer", "phpsessid",
    "jsessionid", "asp.net", "connect.sid",
}

# 跟踪/统计 cookie：有效期往往很长且与登录无关，必须排除
_TRACKING_COOKIE_KEYWORDS = {
    "_ga", "_gid", "_fbp", "_fbc", "utm_", "gclid", "fbclid",
    "_gcl", "msclkid", "tt_", "li_", "bcookie", "_np_",
}


@dataclass
class LoginResult:
    success: bool
    message: str
    cookie: str | None = None
    expire_at: datetime | None = None
    credential_id: int | None = None


class LoginUnavailable(RuntimeError):
    """自动登录能力不可用（未安装 Playwright 或浏览器）。"""


def _launch_kwargs() -> dict:
    settings = get_settings()
    kwargs: dict = {"headless": True}
    path = (settings.playwright_chromium_path or "").strip()
    if path:
        kwargs["executable_path"] = path
    return kwargs


async def login_with_credentials(
    login_url: str,
    username: str,
    password: str,
    *,
    flow: LoginFlow | None = None,
) -> LoginResult:
    """用账号密码登录，返回 Cookie 与推断出的过期时间。"""
    if not login_url:
        return LoginResult(False, "未配置登录地址")
    if not username or not password:
        return LoginResult(False, "未配置企业账号或密码")

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise LoginUnavailable(f"未安装 Playwright，无法自动登录: {exc}") from exc

    effective_flow = flow or LoginFlow()
    last_error = "登录失败"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await asyncio.wait_for(
                _do_login(login_url, username, password, effective_flow),
                timeout=get_settings().llm_provider_auto_login_timeout_seconds,
            )
            if result.success:
                return result
            last_error = result.message
            # 页面结构不对（找不到输入框）重试没有意义，上游改版了
            if "未找到" in result.message:
                return result
        except asyncio.TimeoutError:
            last_error = "登录超时，请检查网络或登录地址"
        except LoginUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = _friendly_error(exc)
            logger.warning("自动登录第 %d 次失败: %s", attempt, type(exc).__name__)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_SECONDS)

    return LoginResult(False, last_error)


async def _do_login(
    login_url: str, username: str, password: str, flow: LoginFlow
) -> LoginResult:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**_launch_kwargs())
        try:
            # ignore_https_errors 必须放在 context 上：内网自签证书会让
            # 页面根本加载不出来，报错只有一句 TLS 握手失败
            context = await browser.new_context(
                ignore_https_errors=flow.ignore_https_errors,
                extra_http_headers=flow.extra_http_headers or None,
            )
            page = await context.new_page()
            await page.goto(login_url, wait_until=flow.wait_until, timeout=60_000)

            # SPA 的 goto 返回不代表表单已渲染
            if flow.settle_ms:
                await asyncio.sleep(flow.settle_ms / 1000)

            username_input = await _find_username_input(page, flow.username_selectors)
            if username_input is None:
                return LoginResult(False, "未找到用户名输入框，请检查登录地址是否正确")
            password_input = await _find_first(page, flow.password_selectors)
            if password_input is None:
                return LoginResult(False, "未找到密码输入框，请检查登录地址是否正确")

            await username_input.fill(username)
            await password_input.fill(password)

            clicked = False
            if flow.submit_text:
                clicked = await _click_by_text(page, flow.submit_text)
            if not clicked:
                submit = await _find_first(page, flow.submit_selectors)
                if submit is not None:
                    await submit.click()
                    clicked = True
            if not clicked:
                await password_input.press("Enter")

            # URL 跳转是比「拿到任意 cookie」可靠得多的成功判据：
            # 登录失败时 SSO 页面自己也会写 cookie
            reached_success_url = True
            if flow.success_url:
                try:
                    await page.wait_for_url(flow.success_url, timeout=flow.success_timeout_ms)
                except Exception:  # noqa: BLE001 —— 不跳转不一定失败，继续看 cookie
                    reached_success_url = False
                    logger.info("自动登录未命中成功跳转 %s，继续检查 Cookie", flow.success_url)

            if flow.after_submit_ms:
                await asyncio.sleep(flow.after_submit_ms / 1000)

            cookies = await _collect_cookies(context, flow)
            if not cookies:
                return LoginResult(False, "登录后未获取到 Cookie，请确认账号密码是否正确")

            if flow.required_cookies:
                names = {str(c.get("name") or "") for c in cookies}
                missing = [name for name in flow.required_cookies if name not in names]
                if missing:
                    detail = "、".join(missing)
                    suffix = "" if reached_success_url else "，且未跳到登录成功页"
                    return LoginResult(
                        False,
                        f"登录后缺少会话 Cookie（{detail}）{suffix}，"
                        "可能是账号密码错误或登录流程已变更",
                    )

            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
            return LoginResult(
                True, "登录成功", cookie_str, _infer_expire_at(cookies)
            )
        finally:
            await browser.close()


async def _collect_cookies(context, flow: LoginFlow) -> list[dict]:
    """轮询等待会话 Cookie 就绪，并按域过滤。

    会话 Cookie 常常是登录跳转成功后由前端脚本异步写入的，取一次拿不到
    不代表失败 —— 旧实现只 ``sleep(1)`` 取一次，在 SPA 站点上基本必失手。
    """
    attempts = max(1, flow.cookie_poll_attempts)
    interval = max(200, flow.cookie_poll_interval_ms) / 1000
    cookies: list[dict] = []

    for index in range(attempts):
        cookies = await context.cookies()
        cookies = _filter_domain(cookies, flow.cookie_domain)
        if flow.required_cookies:
            names = {str(c.get("name") or "") for c in cookies}
            if all(name in names for name in flow.required_cookies):
                return cookies
        elif cookies:
            return cookies
        if index < attempts - 1:
            await asyncio.sleep(interval)

    return cookies


def _filter_domain(cookies: list[dict], domain: str) -> list[dict]:
    """只保留目标域的 cookie。

    多域 SSO（登录域、授权域、业务域）会留下一堆互不相关的 cookie，混成
    一个串发给上游既没意义，也容易被网关的安全策略当成异常请求。
    """
    target = (domain or "").strip().lstrip(".").lower()
    if not target:
        return cookies
    kept: list[dict] = []
    for cookie in cookies:
        raw = str(cookie.get("domain") or "").strip().lstrip(".").lower()
        if not raw:
            continue
        if raw == target or raw.endswith("." + target) or target.endswith("." + raw):
            kept.append(cookie)
    return kept


def _infer_expire_at(cookies: list[dict]) -> datetime:
    """从 Cookie 推断过期时间。

    上游给的 ``expires`` 常常不可信（tracking cookie 有效期长达一年、
    session cookie 为 -1），所以只取认证相关 cookie 的最早过期时间，
    并设一个下限，避免刚登录就被判定为过期。
    """
    settings = get_settings()
    now = app_now()
    floor = now + timedelta(hours=settings.llm_provider_cookie_default_ttl_hours)
    tz = now.tzinfo

    earliest: datetime | None = None
    for cookie in cookies:
        name = (cookie.get("name") or "").lower()
        expires = cookie.get("expires", -1)
        if expires is None or expires <= 0:
            continue
        if any(keyword in name for keyword in _TRACKING_COOKIE_KEYWORDS):
            continue
        try:
            expired_at = datetime.fromtimestamp(expires, tz=tz)
        except (OverflowError, OSError, ValueError):
            continue
        if expired_at <= now:
            continue
        is_auth = any(keyword in name for keyword in _AUTH_COOKIE_KEYWORDS)
        if not is_auth and expired_at - now < timedelta(hours=1):
            continue
        if earliest is None or expired_at < earliest:
            earliest = expired_at

    if earliest is None:
        return floor
    return max(earliest, floor)


async def _find_first(page, selectors: tuple[str, ...]):
    for selector in selectors:
        element = await page.query_selector(selector)
        if element is not None and await element.is_visible():
            return element
    return None


async def _find_username_input(page, selectors: tuple[str, ...]):
    element = await _find_first(page, selectors)
    if element is not None:
        return element

    # 兜底：密码框正上方第一个可见输入框
    password = await page.query_selector('input[type="password"]')
    if password is None:
        return None
    password_box = await password.bounding_box()
    candidates = await page.query_selector_all(
        'input[type="text"], input[type="email"], input[type="tel"], input:not([type])'
    )
    for candidate in candidates:
        if not await candidate.is_visible():
            continue
        box = await candidate.bounding_box()
        if box and password_box and box["y"] < password_box["y"]:
            return candidate
    return None


async def _click_by_text(page, text: str) -> bool:
    """按可见文本点击。

    企业 SSO 的提交按钮经常不是 ``<button>``（可能是 ``<div>`` 或带图标的
    链接），按标签选择器一律命不中，按文案反而稳定。
    """
    try:
        locator = page.locator(f"text={text}").first
        if await locator.count() == 0:
            return False
        await locator.click(timeout=10_000)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("按文案「%s」点击失败: %s", text, exc)
        return False


def _friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return "登录超时，请检查网络连接或登录地址是否正确"
    if "err_name_not_resolved" in text:
        return "无法解析登录地址，请检查网址是否正确"
    if "err_connection_refused" in text:
        return "连接被拒绝，请检查登录地址是否可用"
    if "err_connection_timed_out" in text:
        return "连接超时，请检查网络连接"
    if "certificate" in text or "ssl" in text:
        return "证书校验失败：该站点使用自签证书，请在预设里开启「跳过 TLS 校验」"
    if "executable" in text or ("browser" in text and "launch" in text):
        return "浏览器启动失败，请检查 Playwright 与 Chromium 安装"
    return f"登录失败: {str(exc)[:200]}"


async def login_and_store(
    provider_id: int, credential_id: int | None = None
) -> LoginResult:
    """读取凭据 → 登录 → 写回结果。管理端点与定时任务共用这一条路径。"""
    from app.services.llm_providers.presets import resolve_login_flow

    material = credentials.read_login_material(provider_id, credential_id)
    if material is None:
        return LoginResult(False, "未配置企业账号密码，无法自动登录")

    target_id = material["credential_id"]
    flow = _login_flow_for_provider(provider_id, material["login_url"] or "", resolve_login_flow)

    try:
        result = await login_with_credentials(
            material["login_url"] or "",
            material["username"],
            material["password"],
            flow=flow,
        )
    except LoginUnavailable as exc:
        credentials.apply_login_result(target_id, success=False, error=str(exc))
        return LoginResult(False, str(exc), credential_id=target_id)

    credentials.apply_login_result(
        target_id,
        success=result.success,
        cookie=result.cookie,
        expire_at=result.expire_at,
        error=None if result.success else result.message,
    )
    result.credential_id = target_id
    return result


def _login_flow_for_provider(provider_id: int, login_url: str, resolver) -> LoginFlow:
    """按提供商的 ``extra`` 组装登录动作。读不到配置时退回纯默认值。"""
    from app.db.session import create_db_session
    from app.services.llm_providers.spec import get_provider, parse_extra

    try:
        with create_db_session() as db:
            row = get_provider(db, provider_id)
            extra = parse_extra(row.extra_json) if row is not None else {}
    except Exception:  # noqa: BLE001 —— 读配置失败不该阻断登录，退回默认动作
        extra = {}
    return resolver(extra, default_entry=login_url)
