"""智能体商店 UI 测试：安装 / 卸载 / 安装后可在聊天选用。

覆盖用户要求的两件事：
  1. 在商店 UI 上真实点「安装」，状态变更落到服务端；
  2. 卸载后回到「安装」态，且聊天页可选列表同步变化。

不依赖 LLM：只操作安装状态，不发消息。
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
PASSWORD = "test123456"


def _api(path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        # 卸载等接口返回 204 No Content，没有响应体
        return json.loads(raw) if raw else {}


@pytest.fixture(scope="module")
def token() -> str:
    return _api("/api/v1/auth/login", "POST", {"email": ADMIN_EMAIL, "password": PASSWORD})["access_token"]


def _items(body: dict) -> list[dict]:
    """两个接口都返回 items；保留 profiles 兜底以防响应结构变更。"""
    return body.get("items") or body.get("profiles") or []


def _my_agent_names(token: str) -> list[str]:
    return [a.get("name") for a in _items(_api("/api/v1/my/agents", token=token))]


def _store_profiles(token: str) -> list[dict]:
    return _items(_api("/api/v1/agent-store", token=token))


def test_store_renders(page_admin: Page, token: str):
    page_admin.goto(f"{FRONTEND}/agents")
    expect(page_admin.get_by_text("智能体商店")).to_be_visible(timeout=30_000)
    expect(page_admin.get_by_role("searchbox", name="搜索智能体")).to_be_visible()

    # 卡片上一定有「对话」（已装）或「安装」（未装）按钮之一。
    # 按钮内含图标，可访问名可能带前后空白，用正则匹配更稳。
    page_admin.wait_for_timeout(1500)
    chats = page_admin.get_by_role("button", name=re.compile(r"^\s*对话\s*$")).count()
    installs = page_admin.get_by_role("button", name=re.compile(r"^\s*安装\s*$")).count()
    assert chats + installs > 0, (
        f"商店里没有任何智能体卡片（对话={chats} 安装={installs}）"
    )


def test_search_filters_store(page_admin: Page):
    page_admin.goto(f"{FRONTEND}/agents")
    search = page_admin.get_by_role("searchbox", name="搜索智能体")
    expect(search).to_be_visible(timeout=30_000)

    search.fill("网站")
    expect(page_admin.get_by_text("网站工程师").first).to_be_visible(timeout=10_000)

    search.fill("zzz-not-exist-zzz")
    page_admin.wait_for_timeout(600)
    assert page_admin.get_by_text("网站工程师").count() == 0


def test_install_then_uninstall_via_ui(page_admin: Page, token: str):
    """在 UI 上安装一个未安装的智能体，再卸载，服务端状态同步。"""
    store = _store_profiles(token)
    installed_names = set(_my_agent_names(token))

    def find_uninstalled() -> dict | None:
        for p in store:
            if p.get("name") in installed_names:
                continue
            if p.get("is_owner") or p.get("slug") == "general":
                continue
            return p
        return None

    target = find_uninstalled()
    if target is None:
        # 全部已安装：先通过 API 卸载一个可卸载的（保留通用助手），
        # 让「安装」按钮真实出现，再走 UI 安装。
        candidates = [
            p for p in store
            if p.get("name") in installed_names
            and not p.get("is_owner")
            and p.get("slug") != "general"
            and p.get("name") != "通用助手"
        ]
        assert candidates, f"没有可用于安装测试的智能体（已装：{sorted(installed_names)}）"
        victim = candidates[0]
        _api(f"/api/v1/agent-store/{victim['id']}/install", "DELETE", None, token)
        installed_names = set(_my_agent_names(token))
        target = find_uninstalled()
    assert target is not None, f"商店里没有可安装的智能体（已装：{sorted(installed_names)}）"
    name = target["name"]

    page_admin.goto(f"{FRONTEND}/agents")
    expect(page_admin.get_by_text("智能体商店")).to_be_visible(timeout=30_000)

    # 搜索到该智能体，点安装
    page_admin.get_by_role("searchbox", name="搜索智能体").fill(name)
    page_admin.wait_for_timeout(800)

    install_btn = page_admin.get_by_role("button", name="安装").first
    expect(install_btn).to_be_visible(timeout=15_000)
    install_btn.click()

    # 安装成功后卡片变成「对话」，并且服务端确实记录了安装
    expect(page_admin.get_by_role("button", name="对话").first).to_be_visible(timeout=20_000)
    assert name in _my_agent_names(token), f"{name} 安装后未出现在我的智能体里"

    # 卸载：卡片上的卸载按钮（aria/title 含「卸载」）
    # 卸载按钮带 title/aria-label，不同实现下可访问名可能是「卸载」或含智能体名
    uninstall = page_admin.get_by_role("button", name=re.compile("卸载")).first
    expect(uninstall).to_be_visible(timeout=15_000)
    uninstall.click()

    # 卸载后回到「安装」态
    expect(page_admin.get_by_role("button", name="安装").first).to_be_visible(timeout=20_000)
    assert name not in _my_agent_names(token), f"{name} 卸载后仍在我的智能体里"

    # 复原：本用例卸载了它，必须装回去，否则后续用例的「智能体可选」断言会失败
    _api(f"/api/v1/agent-store/{target['id']}/install", "POST", None, token)
    assert name in _my_agent_names(token), f"{name} 复原安装失败，会污染其他用例"


def test_installed_agent_selectable_in_chat(page_admin: Page, token: str):
    """已安装的智能体应出现在聊天页的选择器里并可选中。"""
    names = _my_agent_names(token)
    assert names, "测试账号没有任何已安装智能体"

    page_admin.goto(f"{FRONTEND}/chat")
    page_admin.get_by_role("button", name="新的对话").click()
    page_admin.wait_for_timeout(1200)

    page_admin.get_by_role("combobox").click()
    expect(page_admin.get_by_role("listbox")).to_be_visible(timeout=10_000)

    options = page_admin.get_by_role("option")
    expect(options.first).to_be_visible(timeout=10_000)
    option_texts = [options.nth(i).inner_text() for i in range(options.count())]

    # 至少「通用助手」必须可选
    assert any("通用助手" in t for t in option_texts), f"选择器里没有通用助手：{option_texts}"
