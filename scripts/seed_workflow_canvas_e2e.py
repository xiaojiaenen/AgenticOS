"""Seed a workflow for the canvas e2e test (ASCII only).

Creates (idempotent) a workflow via the admin API:
  - name: "E2E 画布工作流"
  - graph: start -> template -> condition ->(true) template_t / (false) template_f -> end
    (no `position`: the canvas auto-lays out on first open)

Run from backend/:  .venv/Scripts/python.exe ../scripts/seed_workflow_canvas_e2e.py
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"
NAME = "E2E 画布工作流"

GRAPH = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "greet", "type": "template", "params": {"template": "你好 {{inputs.name}}"}},
        {
            "id": "gate",
            "type": "condition",
            "params": {"left": "{{inputs.score}}", "op": ">=", "right": "60"},
        },
        {"id": "pass", "type": "template", "params": {"template": "及格"}},
        {"id": "fail", "type": "template", "params": {"template": "不及格"}},
        {"id": "end", "type": "end", "params": {"output": "{{nodes.greet.output}}"}},
    ],
    "edges": [
        {"from": "start", "to": "greet"},
        {"from": "greet", "to": "gate"},
        {"from": "gate", "to": "pass", "label": "true"},
        {"from": "gate", "to": "fail", "label": "false"},
        {"from": "pass", "to": "end"},
        {"from": "fail", "to": "end"},
    ],
}


def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as exc:  # pragma: no cover - CLI helper
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()[:500]}")


login = call(
    "/api/v1/auth/login",
    "POST",
    {"email": "tester@agenticos.dev", "password": "test123456"},
)
token = login["access_token"]
assert login["user"]["role"] == "admin", "seed 需要管理员账号"

listing = call("/api/v1/workflows", token=token)
existing = next((w for w in listing["items"] if w["name"] == NAME), None)
payload = {"name": NAME, "description": "画布 e2e 用例数据", "graph": GRAPH, "enabled": True}
if existing:
    out = call(f"/api/v1/workflows/{existing['id']}", "PUT", payload, token)
    print("updated workflow", out["id"])
else:
    out = call("/api/v1/workflows", "POST", payload, token)
    print("created workflow", out["id"])
