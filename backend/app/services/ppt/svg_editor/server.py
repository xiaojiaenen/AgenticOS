#!/usr/bin/env python3
"""
PPT Master - SVG Editor Server (FastAPI)

FastAPI backend for the SVG annotation editor.
Serves the web UI and provides API endpoints for reading/writing SVG annotations.

Usage:
    uv run python -m app.services.ppt.svg_editor.server <project_dir>

Examples:
    uv run python -m app.services.ppt.svg_editor.server projects/my-project
    uv run python -m app.services.ppt.svg_editor.server projects/my-project --port 8080
    uv run python -m app.services.ppt.svg_editor.server projects/my-project --live

Dependencies:
    fastapi, uvicorn
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import threading
import time
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.services.ppt.svg_editor.annotations import (
    assign_temp_ids,
    parse_annotations,
    set_annotation,
)
from app.services.ppt.svg_finalize.embed_icons import (
    extract_paths_from_icon,
    generate_icon_group,
    parse_use_element,
    resolve_icon_path,
)

_logger = logging.getLogger(__name__)

# 包内导入（FastAPI 工程结构），不再需要 sys.path 注入
_STATIC_DIR = Path(__file__).resolve().parent
_ICONS_DIR = _STATIC_DIR.parents[1] / 'templates' / 'icons'
_USE_ICON_PATTERN = re.compile(r'<use\s+[^>]*data-icon="[^"]*"[^>]*/>')


def _inline_icons(content: str) -> str:
    """Replace <use data-icon="..."/> with rendered <g> for browser preview.

    Preserves the original <use>'s id on the produced <g> so editor element
    targeting (and AI-side annotation lookups against svg_output) stays consistent.
    """
    matches = list(_USE_ICON_PATTERN.finditer(content))
    if not matches:
        return content
    new_content = content
    for match in reversed(matches):
        use_str = match.group(0)
        try:
            attrs = parse_use_element(use_str)
            icon_name = attrs.get('icon')
            if not icon_name:
                continue
            icon_path, _ = resolve_icon_path(str(icon_name), _ICONS_DIR)
            color = str(attrs.get('fill', '#000000'))
            elements, style, base_size = extract_paths_from_icon(icon_path, color)
        except Exception:
            continue
        if not elements:
            continue
        replacement = generate_icon_group(attrs, elements, style, base_size)
        id_match = re.search(r'\bid="([^"]+)"', use_str)
        if id_match:
            replacement = replacement.replace(
                '<g ', f'<g id="{id_match.group(1)}" data-icon="{icon_name}" ', 1,
            )
        new_content = new_content[:match.start()] + replacement + new_content[match.end():]
    return new_content


class _EditorState:
    """Per-project editor state (replaces Flask app.config)."""

    def __init__(self, project_dir: str, live: bool = False) -> None:
        self.project_path = Path(project_dir).resolve()
        self.svg_dir = self.project_path / 'svg_output'
        self.images_dir = self.project_path / 'images'
        self.assets_dir = self.project_path / 'assets'
        self.live = live

        # In-memory annotation store: {filename: {element_id: annotation_text}}
        self.annotations: dict[str, dict[str, str]] = {}

        # Idle timeout: auto-shutdown if no one connects within idle_timeout seconds
        self.last_request_time = time.time()


def create_router(project_dir: str, live: bool = False, state: Optional[_EditorState] = None) -> APIRouter:
    """Create the SVG editor APIRouter for a given project directory.

    URL paths and JSON response shapes are identical to the legacy Flask app.
    """
    state = state or _EditorState(project_dir, live=live)
    svg_dir = state.svg_dir

    async def _touch() -> None:
        state.last_request_time = time.time()

    router = APIRouter(dependencies=[Depends(_touch)])

    @router.post('/api/shutdown')
    async def shutdown(request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        reason = (data or {}).get('reason') or 'shutdown'

        def _stop():
            time.sleep(0.5)  # Let HTTP response flush before killing the process
            print(f"SVG Editor shutting down ({reason}).")
            # os._exit: save-all already wrote to disk; 0.5s delay ensures response is sent.
            os._exit(0)
        threading.Thread(target=_stop, daemon=True).start()
        return {'status': 'ok'}

    @router.get('/')
    async def index():
        index_path = _STATIC_DIR / 'static' / 'index.html'
        if not index_path.is_file():
            return JSONResponse({'error': 'index.html not found'}, status_code=404)
        return FileResponse(str(index_path))

    @router.get('/api/config')
    async def get_config():
        return {'live': state.live}

    @router.get('/images/{filename:path}')
    async def serve_image(filename: str):
        """Serve images referenced by SVGs as `../images/*.png`.

        Resolution against an absolute images_dir + relative_to() check is the
        authoritative path-traversal guard.
        """
        images_dir = state.images_dir
        if not images_dir.exists():
            return JSONResponse({'error': 'images directory not found'}, status_code=404)
        target = (images_dir / filename).resolve()
        try:
            target.relative_to(images_dir.resolve())
        except ValueError:
            return JSONResponse({'error': 'invalid path'}, status_code=400)
        if not target.exists() or not target.is_file():
            return JSONResponse({'error': 'not found'}, status_code=404)
        return FileResponse(str(target))

    @router.get('/assets/{filename:path}')
    async def serve_asset(filename: str):
        """Serve media extracted by pptx_to_svg.py as `../assets/*`."""
        assets_dir = state.assets_dir
        if not assets_dir.exists():
            return JSONResponse({'error': 'assets directory not found'}, status_code=404)
        target = (assets_dir / filename).resolve()
        try:
            target.relative_to(assets_dir.resolve())
        except ValueError:
            return JSONResponse({'error': 'invalid path'}, status_code=400)
        if not target.exists() or not target.is_file():
            return JSONResponse({'error': 'not found'}, status_code=404)
        return FileResponse(str(target))

    @router.get('/api/slides')
    async def get_slides():
        annotations = state.annotations
        slides = []
        if svg_dir.exists():
            for svg_file in sorted(svg_dir.glob('*.svg')):
                disk_annotations = []
                try:
                    tree = ET.parse(str(svg_file))
                    disk_annotations = parse_annotations(tree.getroot())
                except ET.ParseError:
                    pass

                mem_count = len(annotations.get(svg_file.name, {}))
                annotation_count = max(len(disk_annotations), mem_count)

                slides.append({
                    'name': svg_file.name,
                    'annotated': annotation_count > 0,
                    'annotation_count': annotation_count,
                })

        return {'slides': slides}

    def _safe_svg_path(name: str) -> Optional[Path]:
        """Validate slide name and return safe path. Returns None if invalid.

        The early string checks reject obvious bad inputs; the resolve()+startswith()
        check is the authoritative path traversal guard.
        """
        if '/' in name or '\\' in name or '..' in name:
            return None
        svg_file = (svg_dir / name).resolve()
        if not str(svg_file).startswith(str(svg_dir.resolve())):
            return None
        return svg_file

    @router.get('/api/slide/{name}')
    async def get_slide(name: str):
        svg_file = _safe_svg_path(name)
        if svg_file is None:
            return JSONResponse({'error': 'Invalid slide name'}, status_code=400)
        if not svg_file.exists():
            return JSONResponse({'error': 'Slide not found'}, status_code=404)

        try:
            tree = ET.parse(str(svg_file))
            root = tree.getroot()
        except ET.ParseError as e:
            return JSONResponse({'error': f'Failed to parse SVG: {e}'}, status_code=500)

        assign_temp_ids(root)

        disk_annotations = parse_annotations(root)

        mem_annotations = state.annotations.get(name, {})
        merged = {}
        for ann in disk_annotations:
            merged[ann['element_id']] = ann['annotation']
        merged.update(mem_annotations)

        annotations_list = []
        for elem in root.iter():
            eid = elem.get('id')
            if eid and eid in merged:
                tag = elem.tag
                if '}' in tag:
                    tag = tag.split('}', 1)[1]
                annotations_list.append({
                    'element_id': eid,
                    'tag': tag,
                    'annotation': merged[eid],
                })

        content = ET.tostring(root, encoding='unicode', xml_declaration=False)
        # Inline <use data-icon> placeholders so the browser can render icons.
        content = _inline_icons(content)

        return {
            'name': name,
            'content': content,
            'annotations': annotations_list,
        }

    @router.post('/api/slide/{name}/annotate')
    async def post_annotate(name: str, request: Request):
        try:
            data = await request.json()
        except Exception:
            data = None
        if not data or 'element_id' not in data or 'annotation' not in data:
            return JSONResponse({'error': 'Missing element_id or annotation'}, status_code=400)

        element_id = data['element_id']
        annotation = data['annotation']

        if not isinstance(element_id, str) or not isinstance(annotation, str):
            return JSONResponse({'error': 'element_id and annotation must be strings'}, status_code=400)

        if len(element_id) > 200:
            return JSONResponse({'error': 'element_id too long (max 200 chars)'}, status_code=400)

        if len(annotation) > 10000:
            return JSONResponse({'error': 'Annotation too long (max 10000 chars)'}, status_code=400)

        state.annotations.setdefault(name, {})[element_id] = annotation

        return {
            'status': 'ok',
            'annotations_count': len(state.annotations[name]),
        }

    @router.delete('/api/slide/{name}/annotate/{element_id}')
    async def delete_annotate(name: str, element_id: str):
        annotations = state.annotations
        # Ensure the file key exists so save-all knows to rewrite this file
        # even if no new annotations were added (pure delete path).
        annotations.setdefault(name, {})
        annotations[name].pop(element_id, None)

        return {
            'status': 'ok',
            'annotations_count': len(annotations.get(name, {})),
        }

    @router.post('/api/save-all')
    async def save_all():
        annotations = state.annotations
        modified = []

        for filename, anns in annotations.items():
            # anns may be empty when the user deleted all annotations — still
            # need to write so the on-disk data-edit-* attributes are cleared.

            svg_file = _safe_svg_path(filename)
            if svg_file is None or not svg_file.exists():
                continue

            try:
                tree = ET.parse(str(svg_file))
                root = tree.getroot()
            except ET.ParseError:
                continue

            assign_temp_ids(root)

            # Clear all existing annotations from the file before writing current state
            for elem in root.iter():
                elem.attrib.pop('data-edit-target', None)
                elem.attrib.pop('data-edit-annotation', None)

            for element_id, annotation_text in anns.items():
                set_annotation(root, element_id, annotation_text)

            # Strip transient _edit_N ids from elements that are NOT user-annotated.
            # Only annotated elements need to keep their id so the AI can locate them
            # via check_annotations.py; the rest are pollution.
            annotated_ids = set(anns.keys())
            for elem in root.iter():
                eid = elem.get('id', '')
                if eid.startswith('_edit_') and eid not in annotated_ids:
                    elem.attrib.pop('id', None)

            tree.write(str(svg_file), encoding='UTF-8', xml_declaration=True)
            modified.append(filename)

        annotations.clear()

        return {'status': 'ok', 'files_modified': modified}

    return router


def create_app(project_dir: str, idle_timeout: int = 900, live: bool = False) -> FastAPI:
    """Create and configure the FastAPI app for a given project directory."""
    state = _EditorState(project_dir, live=live)

    app = FastAPI(title='SVG Editor', docs_url=None, redoc_url=None)
    app.include_router(create_router(str(state.project_path), live=live, state=state))

    if (_STATIC_DIR / 'static').is_dir():
        app.mount('/static', StaticFiles(directory=str(_STATIC_DIR / 'static')), name='static')

    def _idle_watchdog():
        if idle_timeout <= 0:
            return
        while True:
            time.sleep(10)
            elapsed = time.time() - state.last_request_time
            if elapsed > idle_timeout:
                print(f"SVG Editor idle for {idle_timeout}s, shutting down.")
                # os._exit: uvicorn has no cross-thread clean shutdown;
                # data is safe because idle timeout only fires when no requests are in flight.
                os._exit(0)

    watchdog = threading.Thread(target=_idle_watchdog, daemon=True)
    watchdog.start()

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='PPT Master SVG Editor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('project_dir', help='Path to project directory (contains svg_output/)')
    parser.add_argument('--port', type=int, default=5050, help='Port to listen on (default: 5050)')
    parser.add_argument('--no-browser', action='store_true', help='Do not auto-open browser')
    parser.add_argument(
        '--live',
        action='store_true',
        help='Run as Executor live preview: allow empty svg_output/ and keep serving after annotation submit',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=None,
        help='Idle timeout in seconds (default: 900; live mode default: 0 = disabled)',
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_path = Path(args.project_dir).resolve()
    svg_output = project_path / 'svg_output'
    if not svg_output.exists():
        if args.live:
            svg_output.mkdir(parents=True, exist_ok=True)
        else:
            print(f"Error: {svg_output} does not exist", file=sys.stderr)
            return 1
    elif not svg_output.is_dir():
        print(f"Error: {svg_output} is not a directory", file=sys.stderr)
        return 1

    idle_timeout = args.timeout
    if idle_timeout is None:
        idle_timeout = 0 if args.live else 900

    app = create_app(str(project_path), idle_timeout=idle_timeout, live=args.live)

    url = f'http://localhost:{args.port}'
    if not args.no_browser:
        webbrowser.open(url)

    mode = "live preview (auto-startup)" if args.live else "live preview"
    print(f"SVG Editor running at {url} ({mode})")
    print(f"Project: {project_path}")
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='info')
    return 0


# ============================================================================
# AgenticOS Integration - WebSocket-based real-time preview
# ============================================================================


class AgenticOSEditorServer:
    """AgenticOS SVG 实时编辑器服务"""

    def __init__(self):
        self.connections: dict[str, WebSocket] = {}
        self.svg_cache: dict[str, list[str]] = {}
        self.app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""

        @self.app.websocket("/ws/{artifact_id}")
        async def websocket_endpoint(websocket: WebSocket, artifact_id: str):
            await self._handle_websocket(websocket, artifact_id)

        @self.app.get("/editor/{artifact_id}")
        async def editor_page(artifact_id: str):
            return HTMLResponse(self._get_editor_html(artifact_id))

    async def _handle_websocket(self, websocket: WebSocket, artifact_id: str):
        """处理 WebSocket 连接"""
        await websocket.accept()
        self.connections[artifact_id] = websocket

        try:
            # 发送当前 SVG
            svgs = self.svg_cache.get(artifact_id, [])
            await websocket.send_json({
                "type": "init",
                "svgs": svgs,
                "total": len(svgs),
            })

            # 监听修改
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "update":
                    slide_num = data.get("slide_num")
                    svg = data.get("svg")

                    if slide_num is not None and svg:
                        # 更新缓存
                        if artifact_id not in self.svg_cache:
                            self.svg_cache[artifact_id] = []

                        # 确保列表足够长
                        while len(self.svg_cache[artifact_id]) <= slide_num:
                            self.svg_cache[artifact_id].append("")

                        self.svg_cache[artifact_id][slide_num] = svg

                        # 广播给其他客户端
                        await self._broadcast(artifact_id, {
                            "type": "update",
                            "slide_num": slide_num,
                            "svg": svg,
                        })

                elif data.get("type") == "select":
                    # 广播选中的幻灯片
                    await self._broadcast(artifact_id, {
                        "type": "select",
                        "slide_num": data.get("slide_num"),
                    })

        except WebSocketDisconnect:
            _logger.info("WebSocket disconnected: %s", artifact_id)
        except Exception as e:
            _logger.error("WebSocket error: %s", e)
        finally:
            if artifact_id in self.connections:
                del self.connections[artifact_id]

    async def _broadcast(self, artifact_id: str, message: dict):
        """广播消息给其他客户端"""
        if artifact_id in self.connections:
            try:
                await self.connections[artifact_id].send_json(message)
            except Exception:
                pass

    def _get_editor_html(self, artifact_id: str) -> str:
        """生成编辑器 HTML"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SVG Editor - {artifact_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; }}
        .container {{ display: flex; height: 100vh; }}
        .sidebar {{ width: 200px; background: white; border-right: 1px solid #e0e0e0; overflow-y: auto; padding: 16px; }}
        .sidebar h3 {{ font-size: 12px; color: #666; margin-bottom: 12px; text-transform: uppercase; }}
        .slide-thumb {{ cursor: pointer; margin-bottom: 12px; border: 2px solid transparent; border-radius: 8px; overflow: hidden; }}
        .slide-thumb.active {{ border-color: #2196F3; }}
        .slide-thumb:hover {{ border-color: #90CAF9; }}
        .slide-thumb svg {{ width: 100%; height: auto; display: block; }}
        .main {{ flex: 1; display: flex; flex-direction: column; }}
        .toolbar {{ height: 48px; background: white; border-bottom: 1px solid #e0e0e0; display: flex; align-items: center; padding: 0 16px; gap: 8px; }}
        .toolbar button {{ padding: 6px 12px; border: 1px solid #ddd; background: white; border-radius: 6px; cursor: pointer; font-size: 13px; }}
        .toolbar button:hover {{ background: #f5f5f5; }}
        .editor {{ flex: 1; overflow: auto; padding: 24px; background: #fafafa; }}
        .slide-preview {{ max-width: 960px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); overflow: hidden; }}
        .slide-preview svg {{ width: 100%; height: auto; display: block; }}
        .status {{ padding: 8px 16px; background: white; border-top: 1px solid #e0e0e0; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <h3>幻灯片</h3>
            <div id="slide-list"></div>
        </div>
        <div class="main">
            <div class="toolbar">
                <button onclick="prevSlide()">◀ 上一页</button>
                <button onclick="nextSlide()">下一页 ▶</button>
                <span id="page-info" style="margin: 0 12px; color: #666;">-</span>
                <button onclick="zoomIn()">放大</button>
                <button onclick="zoomOut()">缩小</button>
                <button onclick="resetZoom()">重置</button>
            </div>
            <div class="editor">
                <div class="slide-preview" id="slide-preview"></div>
            </div>
            <div class="status" id="status">连接中...</div>
        </div>
    </div>

    <script>
        const artifactId = "{artifact_id}";
        let ws = null;
        let svgs = [];
        let currentSlide = 0;
        let zoom = 1;

        function connect() {{
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${{protocol}}://${{window.location.host}}/ws/${{artifactId}}`);

            ws.onopen = () => {{
                document.getElementById('status').textContent = '已连接';
            }};

            ws.onmessage = (event) => {{
                const data = JSON.parse(event.data);

                if (data.type === 'init') {{
                    svgs = data.svgs;
                    renderSlideList();
                    showSlide(0);
                }} else if (data.type === 'update') {{
                    svgs[data.slide_num] = data.svg;
                    renderSlideList();
                    if (data.slide_num === currentSlide) {{
                        showSlide(currentSlide);
                    }}
                }} else if (data.type === 'select') {{
                    showSlide(data.slide_num);
                }}
            }};

            ws.onclose = () => {{
                document.getElementById('status').textContent = '已断开，正在重连...';
                setTimeout(connect, 2000);
            }};
        }}

        function renderSlideList() {{
            const list = document.getElementById('slide-list');
            list.innerHTML = svgs.map((svg, i) => `
                <div class="slide-thumb ${{i === currentSlide ? 'active' : ''}}" onclick="showSlide(${{i}})">
                    ${{svg}}
                </div>
            `).join('');
        }}

        function showSlide(index) {{
            if (index < 0 || index >= svgs.length) return;
            currentSlide = index;
            const preview = document.getElementById('slide-preview');
            preview.innerHTML = svgs[index];
            preview.style.transform = `scale(${{zoom}})`;
            preview.style.transformOrigin = 'top left';
            document.getElementById('page-info').textContent = `${{index + 1}} / ${{svgs.length}}`;
            renderSlideList();
        }}

        function prevSlide() {{ showSlide(currentSlide - 1); }}
        function nextSlide() {{ showSlide(currentSlide + 1); }}
        function zoomIn() {{ zoom = Math.min(zoom + 0.1, 2); updateZoom(); }}
        function zoomOut() {{ zoom = Math.max(zoom - 0.1, 0.5); updateZoom(); }}
        function resetZoom() {{ zoom = 1; updateZoom(); }}
        function updateZoom() {{
            const preview = document.getElementById('slide-preview');
            preview.style.transform = `scale(${{zoom}})`;
        }}

        connect();
    </script>
</body>
</html>"""


# 全局单例
_agenticos_editor: Optional[AgenticOSEditorServer] = None


def get_agenticos_editor() -> AgenticOSEditorServer:
    """获取 AgenticOS 编辑器服务器单例"""
    global _agenticos_editor
    if _agenticos_editor is None:
        _agenticos_editor = AgenticOSEditorServer()
    return _agenticos_editor


def load_svgs_into_editor(artifact_id: str, svgs: list[str]):
    """将 SVG 加载到编辑器

    参数:
        artifact_id: 制品 ID
        svgs: SVG 列表
    """
    editor = get_agenticos_editor()
    editor.svg_cache[artifact_id] = svgs


def get_editor_url(artifact_id: str, port: int = 8080) -> str:
    """获取编辑器 URL

    参数:
        artifact_id: 制品 ID
        port: 端口号

    返回:
        编辑器 URL
    """
    return f"http://localhost:{port}/editor/{artifact_id}"


if __name__ == '__main__':
    raise SystemExit(main())
