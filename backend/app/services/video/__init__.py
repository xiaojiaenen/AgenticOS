"""
Video 智能体服务
将 html-video 核心功能用 Python 重写，作为 AgenticOS 的 video 智能体模式
"""

from .bridge import get_video_orchestrator, init_video_templates
from .types import (
    ContentGraph,
    Project,
    ProjectStatus,
    TemplateMetadata,
    RenderConfig,
    RenderOutput,
)
from .content_graph import validate, topo_sort, total_duration_sec
from .errors import HtmlVideoError, ErrorCode

__all__ = [
    "get_video_orchestrator",
    "init_video_templates",
    "ContentGraph",
    "Project",
    "ProjectStatus",
    "TemplateMetadata",
    "RenderConfig",
    "RenderOutput",
    "validate",
    "topo_sort",
    "total_duration_sec",
    "HtmlVideoError",
    "ErrorCode",
]
