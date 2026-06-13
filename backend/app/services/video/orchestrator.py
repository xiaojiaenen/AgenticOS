"""
项目编排器
完整对标 html-video 原版 ProjectOrchestrator
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .types import (
    Project,
    ProjectStatus,
    ContentGraph,
    FrameRecord,
    RenderConfig,
    RenderOutput,
    TemplateMetadata,
)
from .content_graph import validate, topo_sort, get_node
from .template_registry import TemplateRegistry
from .project_store import ProjectStore
from .asset_store import AssetStore
from .engine import HyperframesEngine
from .errors import HtmlVideoError, ErrorCode


class ProjectOrchestrator:
    """项目生命周期编排"""

    def __init__(
        self,
        project_root: str,
        templates: TemplateRegistry,
        projects: ProjectStore,
        assets: AssetStore,
        engine: HyperframesEngine,
    ):
        self._project_root = project_root
        self._templates = templates
        self._projects = projects
        self._assets = assets
        self._engine = engine

    @property
    def templates(self) -> TemplateRegistry:
        return self._templates

    # --- CRUD ---

    async def create(self, name: str, intent: str = "") -> Project:
        """创建项目，ID = proj_{uuid[:12]}，status=draft"""
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        project = Project(
            id=project_id,
            name=name,
            intent=intent,
            status=ProjectStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )

        await self._projects.save(project)
        return project

    async def list_all(self) -> list[Project]:
        """列出所有项目"""
        return await self._projects.list_all()

    async def load(self, project_id: str) -> Project:
        """加载项目"""
        return await self._projects.load(project_id)

    async def remove(self, project_id: str) -> None:
        """删除项目"""
        await self._projects.remove(project_id)

    # --- 资源操作 ---

    async def add_inline_asset(
        self, project_id: str, content: str, type: str
    ) -> Project:
        """添加内联资源"""
        project = await self.load(project_id)
        asset = await self._assets.add_inline_asset(project_id, content, type)
        project.assets.append(asset)
        project.status = ProjectStatus.DRAFT
        await self._projects.save(project)
        return project

    async def add_buffer_asset(
        self, project_id: str, data: bytes, ext: str
    ) -> dict:
        """添加字节资源"""
        asset = await self._assets.add_buffer_asset(project_id, data, ext)
        return {"asset_id": asset.id, "path": asset.path}

    async def remove_asset(self, project_id: str, asset_id: str) -> Project:
        """移除资源"""
        project = await self.load(project_id)
        project.assets = [a for a in project.assets if a.id != asset_id]
        project.status = ProjectStatus.DRAFT
        await self._projects.save(project)
        return project

    # --- 模板/变量 ---

    async def set_template(self, project_id: str, template_id: str) -> Project:
        """设置模板，重置 variables，降级 status 为 draft"""
        project = await self.load(project_id)
        template = self._templates.get(template_id)

        project.template_id = template_id
        project.variables = {}
        project.status = ProjectStatus.DRAFT
        await self._projects.save(project)
        return project

    async def set_variables(self, project_id: str, variables: dict) -> Project:
        """设置变量"""
        project = await self.load(project_id)
        project.variables.update(variables)
        await self._projects.save(project)
        return project

    async def set_variable(self, project_id: str, key: str, value: Any) -> Project:
        """设置单个变量"""
        project = await self.load(project_id)
        project.variables[key] = value
        await self._projects.save(project)
        return project

    # --- 内容写入 ---

    async def write_preview_html(self, project_id: str, html: str) -> dict:
        """
        单帧快速路径：
        1. 写入 preview.html
        2. 如果没有 frames[]，清除 contentGraphPath
        3. status → previewed
        """
        project = await self.load(project_id)
        project_dir = await self._projects.ensure_dir(project_id)

        # 写入 preview.html
        preview_path = os.path.join(project_dir, "preview.html")
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)

        project.last_preview_html_path = preview_path

        # 如果没有 frames[]，清除 contentGraphPath
        if not project.frames:
            project.content_graph_path = None

        project.status = ProjectStatus.PREVIEWED
        await self._projects.save(project)

        return {"preview_path": preview_path}

    async def write_content_graph(
        self,
        project_id: str,
        graph: ContentGraph,
        preserve_frames: bool = False,
    ) -> dict:
        """
        写入多帧 storyboard：
        1. validate(graph) 校验
        2. 写入 content-graph.json
        3. 创建 frames/ 目录
        4. preserve_frames=True: 保留已有帧，只更新 durationSec
        5. preserve_frames=False: 清空 frames[]
        """
        import json

        # 校验
        result = validate(graph)
        if not result.ok:
            return {
                "ok": False,
                "errors": [e.model_dump() for e in result.errors],
            }

        project = await self.load(project_id)
        project_dir = await self._projects.ensure_dir(project_id)

        # 写入 content-graph.json
        cg_path = os.path.join(project_dir, "content-graph.json")
        with open(cg_path, "w", encoding="utf-8") as f:
            json.dump(graph.model_dump(by_alias=True), f, indent=2, ensure_ascii=False)

        project.content_graph_path = cg_path

        # 创建 frames/ 目录
        frames_dir = os.path.join(project_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        if preserve_frames:
            # 保留已有帧，只更新 durationSec
            node_map = {node.id: node for node in graph.nodes}
            for frame in project.frames:
                node = node_map.get(frame.graph_node_id)
                if node:
                    frame.duration_sec = node.duration_sec
        else:
            # 清空 frames[]
            project.frames = []

        await self._projects.save(project)
        return {"ok": True, "content_graph_path": cg_path}

    async def write_frame_html(
        self, project_id: str, graph_node_id: str, html: str
    ) -> dict:
        """
        写入单帧 HTML：
        1. 读取 content-graph，topo_sort
        2. 文件名: {order:02d}-{safe_id}.html
        3. 更新 frames[]（按 order 排序）
        4. 第一帧成为 project preview
        5. status → previewed
        """
        project = await self.load(project_id)

        if not project.content_graph_path:
            raise HtmlVideoError(
                code=ErrorCode.INVALID_INPUT,
                message="No content graph found. Call write_content_graph first.",
            )

        # 读取 content-graph
        import json

        with open(project.content_graph_path, "r", encoding="utf-8") as f:
            cg_data = json.load(f)
        graph = ContentGraph(**cg_data)

        # topo_sort
        order_list = topo_sort(graph)
        if graph_node_id not in order_list:
            raise HtmlVideoError(
                code=ErrorCode.INVALID_INPUT,
                message=f"Node {graph_node_id} not found in content graph",
            )

        order = order_list.index(graph_node_id)
        safe_id = "".join(c if c.isalnum() or c == "-" else "_" for c in graph_node_id)

        project_dir = await self._projects.ensure_dir(project_id)
        frames_dir = os.path.join(project_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        # 文件名
        filename = f"{order:02d}-{safe_id}.html"
        html_path = os.path.join(frames_dir, filename)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # 获取节点信息
        node = get_node(graph, graph_node_id)
        duration_sec = node.duration_sec if node else 3.0

        # 更新 frames[]
        # 移除同节点的旧帧
        project.frames = [
            f for f in project.frames if f.graph_node_id != graph_node_id
        ]
        project.frames.append(
            FrameRecord(
                graph_node_id=graph_node_id,
                html_path=html_path,
                duration_sec=duration_sec,
                order=order,
            )
        )
        # 按 order 排序
        project.frames.sort(key=lambda f: f.order)

        # 第一帧成为 project preview
        if order == 0 or not project.last_preview_html_path:
            project.last_preview_html_path = html_path

        project.status = ProjectStatus.PREVIEWED
        await self._projects.save(project)

        return {"html_path": html_path, "order": order}

    # --- 渲染导出 ---

    async def export_mp4(
        self,
        project_id: str,
        output_path: Optional[str] = None,
        resolution: Optional[dict] = None,
        fps: int = 60,
        on_progress: Optional[Callable] = None,
        signal: Optional[asyncio.Event] = None,
    ) -> dict:
        """
        核心渲染流程（与原版完全一致）：

        多帧路径（frames[] 非空）：
        1. 按 order 排序帧
        2. 检测是否混合引擎（reencode 标志）
        3. 遍历每帧:
           - resolve_frame_template_ref() 解析引擎+模板
           - engine.render(frame_html, config) → 帧 MP4
        4. concat_frames_ffmpeg() 合并所有帧
        5. apply_soundtrack() 混音（如有）
        6. status → rendered

        单帧快速路径：
        1. 读取 template
        2. engine.render(template_html, config) → MP4
        3. apply_soundtrack()
        4. status → rendered
        """
        project = await self.load(project_id)
        project_dir = await self._projects.ensure_dir(project_id)

        # 默认输出路径
        if not output_path:
            output_path = os.path.join(project_dir, "output.mp4")

        # 默认分辨率
        if not resolution:
            resolution = {"width": 1920, "height": 1080}

        # 多帧路径
        if project.frames:
            result = await self._export_multi_frame(
                project, output_path, resolution, fps, on_progress, signal
            )
        else:
            # 单帧快速路径
            result = await self._export_single_frame(
                project, output_path, resolution, fps, on_progress, signal
            )

        # 应用配乐
        if project.soundtrack and (
            project.soundtrack.music_asset_id or project.soundtrack.narration_asset_id
        ):
            await self._apply_soundtrack(project, output_path, result.duration_sec)

        # 更新项目状态
        project.last_output_mp4_path = output_path
        project.status = ProjectStatus.RENDERED
        project.exports.append(
            {
                "path": output_path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_sec": result.duration_sec,
                "resolution": resolution,
            }
        )
        # 保留最近 20 条导出记录
        if len(project.exports) > 20:
            project.exports = project.exports[-20:]

        await self._projects.save(project)

        return result.model_dump()

    async def _export_single_frame(
        self,
        project: Project,
        output_path: str,
        resolution: dict,
        fps: int,
        on_progress: Optional[Callable],
        signal: Optional[asyncio.Event],
    ) -> RenderOutput:
        """单帧快速路径"""
        # 获取 HTML 路径
        html_path = project.last_preview_html_path
        if not html_path or not os.path.exists(html_path):
            raise HtmlVideoError(
                code=ErrorCode.INVALID_INPUT,
                message="No preview HTML found. Call write_preview_html first.",
            )

        # 获取模板时长
        duration = "auto"
        if project.template_id:
            template = self._templates.get(project.template_id)
            if template:
                # 从模板输出能力获取默认时长
                duration_config = template.output.duration
                if "default" in duration_config:
                    duration = duration_config["default"]

        config = RenderConfig(
            format="mp4",
            resolution=resolution,
            fps=fps,
            duration=duration,
            duration_mode="auto",
            output_path=output_path,
        )

        return await self._engine.render(
            html_path, config, os.path.dirname(output_path), on_progress, signal
        )

    async def _export_multi_frame(
        self,
        project: Project,
        output_path: str,
        resolution: dict,
        fps: int,
        on_progress: Optional[Callable],
        signal: Optional[asyncio.Event],
    ) -> RenderOutput:
        """多帧路径"""
        frames = sorted(project.frames, key=lambda f: f.order)
        frame_mp4s: list[str] = []
        project_dir = await self._projects.ensure_dir(project.id)

        # 检测是否混合引擎（简化版：只支持 hyperframes）
        reencode = False
        engines_used = set()

        for i, frame in enumerate(frames):
            if signal and signal.is_set():
                raise HtmlVideoError(code=ErrorCode.CANCELLED, message="Aborted")

            # 获取帧 HTML 路径
            html_path = frame.html_path
            if not os.path.exists(html_path):
                raise HtmlVideoError(
                    code=ErrorCode.INVALID_INPUT,
                    message=f"Frame HTML not found: {html_path}",
                )

            # 渲染帧
            frame_output = os.path.join(project_dir, f"frame_{i:03d}.mp4")
            config = RenderConfig(
                format="mp4",
                resolution=resolution,
                fps=fps,
                duration=frame.duration_sec,
                duration_mode="explicit",
                output_path=frame_output,
            )

            def frame_progress(pct, stage):
                if on_progress:
                    # 将帧进度映射到总进度
                    overall = int((i / len(frames)) * 80 + (pct / len(frames)))
                    on_progress(overall, f"frame {i+1}/{len(frames)}: {stage}")

            await self._engine.render(
                html_path, config, project_dir, frame_progress, signal
            )
            frame_mp4s.append(frame_output)

        # 合并帧
        if on_progress:
            on_progress(85, "concatenating frames")

        await self._engine.concat_frames_ffmpeg(
            frame_mp4s, output_path, project_dir, reencode=reencode, fps=fps
        )

        # 计算总时长
        total_duration = sum(f.duration_sec for f in frames)
        file_size = os.path.getsize(output_path)

        return RenderOutput(
            output_path=output_path,
            duration_sec=total_duration,
            file_size_bytes=file_size,
            resolution=resolution,
            fps=fps,
            rendered_frames=int(total_duration * fps),
            render_wall_clock_sec=0,  # 将在调用方计算
            engine_version="hyperframes-playwright@0.2.0",
        )

    async def _apply_soundtrack(
        self, project: Project, output_path: str, video_duration_sec: float
    ) -> None:
        """配乐混音"""
        if not project.soundtrack:
            return

        # 查找音频文件路径
        music_path = None
        narration_path = None

        if project.soundtrack.music_asset_id:
            music_path = self._assets.get_asset_path(
                project.id, project.soundtrack.music_asset_id
            )

        if project.soundtrack.narration_asset_id:
            narration_path = self._assets.get_asset_path(
                project.id, project.soundtrack.narration_asset_id
            )

        if not music_path and not narration_path:
            return

        # 默认 fade_out
        fade_out = min(1.5, video_duration_sec / 3)
        fade_in = project.soundtrack.fade_in_sec or 0

        # 临时输出文件
        temp_output = output_path + ".tmp.mp4"

        await self._engine.mux_audio_ffmpeg(
            video_path=output_path,
            output_path=temp_output,
            music_path=music_path,
            narration_path=narration_path,
            music_volume_db=project.soundtrack.music_volume_db,
            narration_volume_db=project.soundtrack.narration_volume_db,
            fade_in_sec=fade_in,
            fade_out_sec=fade_out,
            video_duration_sec=video_duration_sec,
        )

        # 替换原文件
        os.replace(temp_output, output_path)
