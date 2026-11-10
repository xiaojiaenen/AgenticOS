"""Seed local dev environment for the artifact version-bar e2e test (ASCII only).

Creates (idempotent), all owned by tester@agenticos.dev:
- agent session `e2e-verbar-<uid>` (website mode)
- a built website project dist (so /artifacts restore works)
- two website version snapshots (v1/v2) so the version bar appears

Run from backend/:  ../.venv/Scripts/python.exe ../scripts/seed_website_version_bar_e2e.py
"""
import asyncio
import json
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

BASE = "http://127.0.0.1:8001"


def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


admin = call("/api/v1/auth/login", "POST", {
    "email": "tester@agenticos.dev", "password": "test123456",
})
admin_id = admin["user"]["id"]
token = admin["access_token"]
print("admin:", admin_id, admin["user"]["role"])

sid = f"e2e-verbar-{admin_id}"
slug = f"u{admin_id}_s{sid}_v1"

# 1) built dist（/artifacts 回源与 preview_url 签发都依赖它）
from app.core.data_path import WEBSITES_DIR  # noqa: E402

dist = WEBSITES_DIR / slug / "dist"
dist.mkdir(parents=True, exist_ok=True)
(dist / "index.html").write_text(
    "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<title>E2E Version Bar</title></head>"
    "<body><h1>E2E Version Bar</h1></body></html>",
    encoding="utf-8",
)

# 2) 两个版本快照（不足 2 个才补，保证幂等且编号稳定）
from app.services.artifact_version_service import (  # noqa: E402
    list_website_versions,
    snapshot_website_version,
)

if len(list_website_versions(sid)) < 2:
    v1 = asyncio.run(snapshot_website_version(
        sid, "<html><body><h1>version one</h1></body></html>",
        "E2E v1", slug, "vanilla",
    ))
    v2 = asyncio.run(snapshot_website_version(
        sid, "<html><body><h1>version two</h1></body></html>",
        "E2E v2", slug, "vanilla",
    ))
    print("snapshots:", v1, v2)
else:
    print("snapshots already present:", len(list_website_versions(sid)))

# 3) 会话元数据落库（owner = admin，website 模式，标题可辨）
from app.services.session_storage import DatabaseAgentStorage  # noqa: E402

meta = {
    "user_id": admin_id,
    "response_mode": "website",
    "title": "E2E 版本条会话",
}
session = SimpleNamespace(
    session_id=sid,
    system_prompt="",
    metadata=meta,
    max_steps=10,
    parallel_tool_calls=False,
    summary=None,
    last_usage={},
    last_latency_ms=0,
    last_llm_calls=0,
)
asyncio.run(DatabaseAgentStorage().save_session_meta(
    session, user_id=admin_id, agent_profile_id=None,
))

# 4) 通过 API 验证可见性
versions = call(f"/api/v1/agent/sessions/{sid}/versions", token=token)
ws = [v for v in versions.get("versions", []) if v.get("kind") == "website"]
print("versions via api:", len(ws))
assert len(ws) >= 2, "expected at least 2 website versions"
print("seed ok")
