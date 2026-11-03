"""智能体商店批量安装 UI 测试：逐个安装 → 验证 → 复原。

单独一个用例，覆盖「商店里所有未安装的智能体都能装上」这条路径，
避免只测一个智能体而漏掉某个 profile 的安装失败（例如工具绑定冲突）。
"""
from __future__ import annotations

import json
import re
import urllib.request

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
    raw = urllib.request.urlopen(req, timeout=60).read()
    return json.loads(raw) if raw else {}


def _items(body: dict) -> list[dict]:
    return body.get("items") or body.get("profiles") or []


def test_store_install_every_available_agent(page_admin: Page):
    """把商店里所有「可安装」的智能体逐个装上，再卸掉自己装的那些。

    关键约束：**不卸载任何原本已安装的智能体**。早先的版本为了制造
    「可安装」项会先卸几个，结果污染了智能体选择器用例（有状态测试互相
    干扰）。现在只做加法，并在 finally 里精确回滚新增项。
    """
    tok = _api("/api/v1/auth/login", "POST", {"email": ADMIN_EMAIL, "password": PASSWORD})[
        "access_token"
    ]

    store = _items(_api("/api/v1/agent-store", token=tok))
    snapshot = {a.get("name") for a in _items(_api("/api/v1/my/agents", token=tok))}

    # 可安装 = 未安装 + 非自己创建的 + 非通用助手（内置不可卸载）
    targets = [
        p for p in store
        if p.get("name") not in snapshot
        and not p.get("is_owner")
        and p.get("slug") != "general"
        and p.get("name") != "通用助手"
    ]

    page_admin.goto(f"{FRONTEND}/agents")
    expect(page_admin.get_by_text("智能体商店")).to_be_visible(timeout=30_000)
    search = page_admin.get_by_role("searchbox", name="搜索智能体")

    if not targets:
        # 已全部安装：退化为「UI 上安装/对话按钮互斥」的校验，不卸载任何东西
        search.fill("通用助手")
        page_admin.wait_for_timeout(500)
        expect(
            page_admin.get_by_role("button", name=re.compile(r"^\s*对话\s*$")).first
        ).to_be_visible(timeout=15_000)
        return

    newly: list[dict] = []
    try:
        for target in targets:
            search.fill(target["name"])
            page_admin.wait_for_timeout(500)

            install_btn = page_admin.get_by_role("button", name=re.compile(r"^\s*安装\s*$")).first
            expect(install_btn).to_be_visible(timeout=15_000)
            install_btn.click()
            newly.append(target)

            # 卡片翻转为「对话」= 安装成功
            expect(
                page_admin.get_by_role("button", name=re.compile(r"^\s*对话\s*$")).first
            ).to_be_visible(timeout=20_000)

        # 全部安装成功后再核对服务端
        names = {a.get("name") for a in _items(_api("/api/v1/my/agents", token=tok))}
        for target in newly:
            assert target["name"] in names, f"{target['name']} 安装后未生效"

    finally:
        # 只回滚本用例新增的，绝不碰原快照里的智能体
        now = {a.get("name") for a in _items(_api("/api/v1/my/agents", token=tok))}
        by_name = {p.get("name"): p for p in _items(_api("/api/v1/agent-store", token=tok))}
        for name in sorted(now - snapshot):
            prof = by_name.get(name)
            if prof and prof.get("slug") != "general":
                _api(f"/api/v1/agent-store/{prof['id']}/install", "DELETE", None, tok)
