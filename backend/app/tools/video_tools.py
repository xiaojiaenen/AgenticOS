"""
Video 智能体工具
注册 wuwei 工具供 Agent 调用
"""

import json
import os
from typing import Any

from wuwei.tools import ToolRegistry

from ..services.video import (
    get_video_orchestrator,
    ContentGraph,
    validate,
)


def register_video_tools(registry: ToolRegistry):
    """注册 video 模式工具"""
    orchestrator = get_video_orchestrator()

    @registry.tool(display_name="搜索视频模板")
    async def video_search_templates(intent: str, top_n: int = 5) -> Any:
        """根据意图搜索最合适的视频模板。

        参数:
          intent: 搜索意图，如 'data visualization', 'product promo', 'title animation'
          top_n: 返回结果数量，默认 5
        """
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

    @registry.tool(display_name="列出视频模板")
    async def video_list_templates() -> Any:
        """列出所有可用的视频模板。"""
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

    @registry.tool(display_name="获取模板详情")
    async def video_get_template(template_id: str) -> Any:
        """获取指定模板的详细信息。

        参数:
          template_id: 模板 ID
        """
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

    @registry.tool(display_name="创建视频项目")
    async def video_create_project(name: str, intent: str = "") -> Any:
        """创建视频项目。返回项目 ID 用于后续操作。

        参数:
          name: 项目名称
          intent: 项目意图，如 'explainer', 'data-viz', 'promo'
        """
        project = await orchestrator.create(name, intent)
        return {"project_id": project.id}

    @registry.tool(display_name="设置视频模板")
    async def video_set_template(project_id: str, template_id: str) -> Any:
        """为项目设置视频模板。会自动返回模板的设计规范（SKILL.md）。

        参数:
          project_id: 项目 ID
          template_id: 模板 ID
        """
        await orchestrator.set_template(project_id, template_id)

        # 读取模板的 SKILL.md（如果存在）
        skill_content = None
        try:
            template = orchestrator.templates.get(template_id)
            if template and template.template_dir:
                skill_path = os.path.join(template.template_dir, "SKILL.md")
                if os.path.exists(skill_path):
                    with open(skill_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # 去掉 YAML frontmatter，只保留正文
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                skill_content = parts[2].strip()
                            else:
                                skill_content = content
                        else:
                            skill_content = content
        except Exception:
            # SKILL.md 读取失败不影响主流程
            pass

        result = {"ok": True, "template_id": template_id}
        if skill_content:
            result["template_design_guide"] = skill_content
        return result

    @registry.tool(display_name="设置模板变量")
    async def video_set_variables(project_id: str, variables: dict) -> Any:
        """设置项目的模板变量。

        参数:
          project_id: 项目 ID
          variables: 变量键值对
        """
        await orchestrator.set_variables(project_id, variables)
        return {"ok": True}

    @registry.tool(display_name="写入 Storyboard")
    async def video_write_content_graph(project_id: str, graph: dict) -> Any:
        """写入多帧视频的 storyboard 结构（content-graph），用于多帧视频规划。

        参数:
          project_id: 项目 ID
          graph: ContentGraph JSON，包含 schemaVersion, intent, nodes, edges
        """
        cg = ContentGraph(**graph)
        result = validate(cg)
        if not result.ok:
            return {"ok": False, "errors": [e.model_dump() for e in result.errors]}
        await orchestrator.write_content_graph(project_id, cg)
        return {"ok": True}

    @registry.tool(display_name="写入帧 HTML")
    async def video_write_frame_html(project_id: str, node_id: str, html: str) -> Any:
        """为多帧视频的指定节点写入自包含的动画 HTML。

        参数:
          project_id: 项目 ID
          node_id: ContentGraph 节点 ID
          html: 自包含的动画 HTML（CSS keyframes + GSAP）
        """
        await orchestrator.write_frame_html(project_id, node_id, html)
        return {"ok": True}

    @registry.tool(display_name="写入预览 HTML")
    async def video_write_preview_html(project_id: str, html: str) -> Any:
        """写入单帧视频的预览 HTML，用于单帧视频快速路径。

        参数:
          project_id: 项目 ID
          html: 自包含的动画 HTML（CSS keyframes + GSAP）
        """
        await orchestrator.write_preview_html(project_id, html)
        return {"ok": True}

    @registry.tool(display_name="导出 MP4")
    async def video_export_mp4(project_id: str, resolution: str = "1920x1080", fps: int = 30) -> Any:
        """渲染并导出 MP4 视频文件，支持自定义分辨率和帧率。

        参数:
          project_id: 项目 ID
          resolution: 分辨率，格式 '宽x高'，默认 '1920x1080'
          fps: 帧率，默认 30
        """
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

    @registry.tool(display_name="列出视频项目")
    async def video_list_projects() -> Any:
        """列出所有视频项目。"""
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
