"""
Video 服务桥接层
对外统一接口（单例管理）
"""

import os
from pathlib import Path
from typing import Optional

from .template_registry import TemplateRegistry
from .project_store import ProjectStore
from .asset_store import AssetStore
from .engine import HyperframesEngine
from .orchestrator import ProjectOrchestrator


# 全局单例
_orchestrator: Optional[ProjectOrchestrator] = None


def get_video_orchestrator(
    project_root: Optional[str] = None,
    templates_dir: Optional[str] = None,
) -> ProjectOrchestrator:
    """
    获取 Video 编排器单例
    首次调用时创建，后续调用返回缓存实例
    """
    global _orchestrator

    if _orchestrator is not None:
        return _orchestrator

    # 默认路径 - 使用 data/video-projects 目录
    if project_root is None:
        from app.core.data_path import VIDEO_PROJECTS_DIR
        VIDEO_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        project_root = str(VIDEO_PROJECTS_DIR)

    if templates_dir is None:
        # 尝试多个可能的模板目录
        candidates = [
            os.path.join(os.getcwd(), "backend", "templates", "video"),
            os.path.join(os.getcwd(), "templates", "video"),
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "templates", "video"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                templates_dir = candidate
                break

        if templates_dir is None:
            templates_dir = os.path.join(os.getcwd(), "backend", "templates", "video")

    # 创建组件
    templates = TemplateRegistry()
    projects = ProjectStore(project_root)
    assets = AssetStore(project_root)
    engine = HyperframesEngine()

    orchestrator = ProjectOrchestrator(
        project_root=project_root,
        templates=templates,
        projects=projects,
        assets=assets,
        engine=engine,
    )

    # 扫描模板（同步方式，因为初始化时调用）
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环已运行，创建任务
            asyncio.ensure_future(templates.scan(templates_dir))
        else:
            loop.run_until_complete(templates.scan(templates_dir))
    except RuntimeError:
        # 没有事件循环，创建新的
        asyncio.run(templates.scan(templates_dir))

    _orchestrator = orchestrator
    return orchestrator


async def init_video_templates(templates_dir: str) -> None:
    """异步初始化模板扫描"""
    global _orchestrator
    if _orchestrator is not None:
        await _orchestrator.templates.scan(templates_dir)
