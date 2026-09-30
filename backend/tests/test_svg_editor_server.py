"""svg_editor FastAPI server 冒烟测试。

server.py 原为独立 Flask 旁路工具，现已迁为 FastAPI（无 Flask 依赖）。
此处仅验证核心 GET/POST 端点可用与响应形状，不覆盖 websocket 预览服务。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.ppt.svg_editor.server import create_app

_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect id="rect-1" x="0" y="0" width="100" height="100" fill="#fff"/>
</svg>"""


def _make_client(tmp_path):
    project = tmp_path / "proj"
    (project / "svg_output").mkdir(parents=True)
    (project / "svg_output" / "slide-01.svg").write_text(_SVG, encoding="utf-8")
    # idle_timeout=0 关闭 watchdog 线程，避免测试进程被 os._exit
    app = create_app(str(project), idle_timeout=0)
    return TestClient(app)


def test_svg_editor_config_and_slides(tmp_path) -> None:
    client = _make_client(tmp_path)

    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"live": False}

    resp = client.get("/api/slides")
    assert resp.status_code == 200
    slides = resp.json()["slides"]
    assert len(slides) == 1
    assert slides[0]["name"] == "slide-01.svg"
    assert slides[0]["annotated"] is False


def test_svg_editor_slide_and_annotate_roundtrip(tmp_path) -> None:
    client = _make_client(tmp_path)

    resp = client.get("/api/slide/slide-01.svg")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["name"] == "slide-01.svg"
    assert "<svg" in payload["content"]
    assert payload["annotations"] == []

    resp = client.post(
        "/api/slide/slide-01.svg/annotate",
        json={"element_id": "rect-1", "annotation": "这是一个矩形"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "annotations_count": 1}

    resp = client.get("/api/slide/slide-01.svg")
    assert resp.status_code == 200
    assert resp.json()["annotations"] == [
        {"element_id": "rect-1", "tag": "rect", "annotation": "这是一个矩形"}
    ]

    # 非法 slide 名被拒绝（Starlette 路由层 404 或 _safe_svg_path 校验 400，
    # 均不允许路径穿越；错误响应保持原 Flask 格式 {"error": ...} 或 {"detail": ...}）
    resp = client.get("/api/slide/..%2Fescape.svg")
    assert resp.status_code in (400, 404)
