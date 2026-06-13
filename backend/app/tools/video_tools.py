"""
Video 智能体工具
注册 wuwei 工具供 Agent 调用
"""

import json
from typing import Any

from wuwei import ToolRegistry

from ..services.video import (
    get_video_orchestrator,
    ContentGraph,
    validate,
)


def register_video_tools(registry: ToolRegistry):
    """注册 video 模式工具"""
    orchestrator = get_video_orchestrator()

    @registry.register(
        name="video_search_templates",
        description="搜索视频模板。根据意图搜索最合适的视频模板。",
        parameters={
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "搜索意图，如 'data visualization', 'product promo', 'title animation'",
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5,
                },
            },
            "required": ["intent"],
        },
    )
    async def video_search_templates(intent: str, top_n: int = 5) -> Any:
        results = orchestrator.templates.search(intent, top=top_n)
        return [
            {
                "id": r.template.id,
                "name": r.template.name,
                "description": r.template.description,
                "category": r.template.category,
                "tags": r.template.tags,
                "best_for": r.template.best_for,
                "score": r.score,
            }
            for r in results
        ]

    @registry.register(
        name="video_list_templates",
        description="列出所有可用的视频模板。",
        parameters={"type": "object", "properties": {}},
    )
    async def video_list_templates() -> Any:
        templates = orchestrator.templates.list_all()
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "tags": t.tags,
                "best_for": t.best_for,
            }
            for t in templates
        ]

    @registry.register(
        name="video_get_template",
        description="获取指定模板的详细信息。",
        parameters={
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "string",
                    "description": "模板 ID",
                },
            },
            "required": ["template_id"],
        },
    )
    async def video_get_template(template_id: str) -> Any:
        template = orchestrator.templates.get(template_id)
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "tags": template.tags,
            "best_for": template.best_for,
            "inputs": template.inputs,
            "output": template.output.model_dump(),
            "source_entry": template.source_entry,
        }

    @registry.register(
        name="video_create_project",
        description="创建视频项目。返回项目 ID 用于后续操作。",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "项目名称",
                },
                "intent": {
                    "type": "string",
                    "description": "项目意图，如 'explainer', 'data-viz', 'promo'",
                    "default": "",
                },
            },
            "required": ["name"],
        },
    )
    async def video_create_project(name: str, intent: str = "") -> Any:
        project = await orchestrator.create(name, intent)
        return {"project_id": project.id}

    @registry.register(
        name="video_set_template",
        description="为项目设置视频模板。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "项目 ID",
                },
                "template_id": {
                    "type": "string",
                    "description": "模板 ID",
                },
            },
            "required": ["project_id", "template_id"],
        },
    )
    async def video_set_template(project_id: str, template_id: str) -> Any:
        await orchestrator.set_template(project_id, template_id)
        return {"ok": True}

    @registry.register(
        name="video_set_variables",
        description="设置项目的模板变量。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "项目 ID",
                },
                "variables": {
                    "type": "object",
                    "description": "变量键值对",
                },
            },
            "required": ["project_id", "variables"],
        },
    )
    async def video_set_variables(project_id: str, variables: dict) -> Any:
        await orchestrator.set_variables(project_id, variables)
        return {"ok": True}

    @registry.register(
        name="video_write_content_graph",
        description="写入多帧 storyboard（content-graph）。用于多帧视频的结构规划。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "项目 ID",
                },
                "graph": {
                    "type": "object",
                    "description": "ContentGraph JSON，包含 schemaVersion, intent, nodes, edges",
                },
            },
            "required": ["project_id", "graph"],
        },
    )
    async def video_write_content_graph(project_id: str, graph: dict) -> Any:
        cg = ContentGraph(**graph)
        result = validate(cg)
        if not result.ok:
            return {"ok": False, "errors": [e.model_dump() for e in result.errors]}
        await orchestrator.write_content_graph(project_id, cg)
        return {"ok": True}

    @registry.register(
        name="video_write_frame_html",
        description="为多帧视频的指定节点写入 HTML。每个节点对应一帧。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "项目 ID",
                },
                "node_id": {
                    "type": "string",
                    "description": "ContentGraph 节点 ID",
                },
                "html": {
                    "type": "string",
                    "description": "自包含的动画 HTML（CSS keyframes + GSAP）",
                },
            },
            "required": ["project_id", "node_id", "html"],
        },
    )
    async def video_write_frame_html(
        project_id: str, node_id: str, html: str
    ) -> Any:
        await orchestrator.write_frame_html(project_id, node_id, html)
        return {"ok": True}

    @registry.register(
        name="video_write_preview_html",
        description="写入单帧预览 HTML。用于单帧视频的快速路径。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "项目 ID",
                },
                "html": {
                    "type": "string",
                    "description": "自包含的动画 HTML（CSS keyframes + GSAP）",
                },
            },
            "required": ["project_id", "html"],
        },
    )
    async def video_write_preview_html(project_id: str, html: str) -> Any:
        await orchestrator.write_preview_html(project_id, html)
        return {"ok": True}

    @registry.register(
        name="video_export_mp4",
        description="渲染导出 MP4 视频。完成所有 HTML 写入后调用此工具生成最终视频。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "项目 ID",
                },
                "resolution": {
                    "type": "string",
                    "description": "分辨率，格式 '宽x高'，默认 '1920x1080'",
                    "default": "1920x1080",
                },
                "fps": {
                    "type": "integer",
                    "description": "帧率，默认 30",
                    "default": 30,
                },
            },
            "required": ["project_id"],
        },
    )
    async def video_export_mp4(
        project_id: str, resolution: str = "1920x1080", fps: int = 30
    ) -> Any:
        w, h = resolution.split("x")
        result = await orchestrator.export_mp4(
            project_id,
            resolution={"width": int(w), "height": int(h)},
            fps=fps,
        )
        return {
            "output_path": result["output_path"],
            "duration_sec": result["duration_sec"],
        }

    @registry.register(
        name="video_list_projects",
        description="列出所有视频项目。",
        parameters={"type": "object", "properties": {}},
    )
    async def video_list_projects() -> Any:
        projects = await orchestrator.list_all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "status": p.status.value,
                "template_id": p.template_id,
                "created_at": p.created_at,
            }
            for p in projects
        ]
