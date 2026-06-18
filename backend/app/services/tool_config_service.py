from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentToolConfigModel
from app.db.session import create_db_session
from app.services.session_storage import parse_approval_sub_tools

AGENT_MODES = {
    "general": {
        "label": "通用模式",
        "description": "日常问答、资料整理和轻量工具调用。",
    },
    "ppt": {
        "label": "PPT 模式",
        "description": "使用 SVG 原生图形生成演示文稿，支持导出原生 .pptx 文件，形状可编辑。",
    },
    "website": {
        "label": "网站模式",
        "description": "用于页面方案、前端代码和交互式应用生成。",
    },
    "video": {
        "label": "视频模式",
        "description": "智能视频生成，将想法转化为动画 MP4 视频。支持 23 种专业模板，多帧 storyboard 规划，Chromium 录制 + ffmpeg 编码。",
    },
    "email": {
        "label": "邮箱模式",
        "description": "邮件管理助手，支持读取、搜索、发送邮件，统计邮件数量。",
    },
    "bigdata": {
        "label": "大数据模式",
        "description": "大数据平台运维与开发助手。支持 Dinky/Flink/Spark/Doris/ClickHouse 计算引擎、"
                       "DolphinScheduler/Airflow 工作流调度、HDFS/Kafka/MinIO 存储、YARN/K8s 资源管理、"
                       "SeaTunnel/NiFi 数据集成、OpenMetadata/DataHub 数据治理、Superset/Grafana 监控 BI。",
    },
}


# ---------------------------------------------------------------------------
# 工具自动发现：mode → registrar 函数列表
# 新增工具只需在这里注册，TOOL_CATALOG 和 DEFAULT_MODE_TOOLS 自动生成
# ---------------------------------------------------------------------------
_MODE_TOOL_REGISTRARS: dict[str, list[tuple[str, str]]] = {
    "ppt": [
        ("app.tools.icon_tools", "register_icon_tools"),
        ("app.tools.ppt_tools", "register_ppt_tools"),
        ("app.tools.chart_tools", "register_chart_tools"),
        ("app.tools.quality_checker_tools", "register_quality_checker_tools"),
        ("app.tools.pptx_reverse_tools", "register_pptx_reverse_tools"),
        ("app.tools.template_tools", "register_template_tools"),
        ("app.tools.image_tools", "register_image_tools"),
    ],
    "video": [
        ("app.tools.video_tools", "register_video_tools"),
    ],
    "email": [
        ("app.tools.email_tools", "register_email_tools"),
    ],
    "website": [
        ("app.tools.website_tools", "register_website_tools"),
        ("app.tools.website_file_tools", "register_website_file_tools"),
    ],
}


def _discover_all_mode_tools() -> dict[str, set[str]]:
    """从各 mode 的 registrar 函数中自动发现工具名。返回 {mode: {tool_name, ...}}。"""
    from wuwei.tools import ToolRegistry
    result: dict[str, set[str]] = {}
    for mode, registrars in _MODE_TOOL_REGISTRARS.items():
        tools: set[str] = set()
        for module_path, func_name in registrars:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                registrar = getattr(mod, func_name)
                reg = ToolRegistry()
                registrar(reg)
                tools.update(t.name for t in reg.list_tools())
            except Exception:
                pass
        result[mode] = tools
    return result


def _build_default_mode_tools() -> dict[str, dict[str, dict[str, bool]]]:
    """基于自动发现 + 手动覆盖，构建完整的 DEFAULT_MODE_TOOLS。"""
    # 基础模板：每个 mode 都有的通用工具
    _BASE: dict[str, dict[str, bool]] = {
        "calc": {"enabled": False, "requires_approval": False},
        "time": {"enabled": False, "requires_approval": False},
        "file": {"enabled": False, "requires_approval": True},
        "file_to_md": {"enabled": True, "requires_approval": False},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": False, "requires_approval": True},
        "skill": {"enabled": True, "requires_approval": False},
        "memory": {"enabled": False, "requires_approval": False},
        "decision": {"enabled": True, "requires_approval": False},
        "email": {"enabled": False, "requires_approval": True},
        "render_chart": {"enabled": True, "requires_approval": False},
        "analyze_data": {"enabled": True, "requires_approval": False},
    }
    # 每个 mode 的手动覆盖（需要特殊 enabled/approval 配置的工具）
    _MODE_OVERRIDES: dict[str, dict[str, dict[str, bool]]] = {
        "general": {
            "calc": {"enabled": True, "requires_approval": False},
            "time": {"enabled": True, "requires_approval": False},
            "file": {"enabled": True, "requires_approval": True},
            "memory": {"enabled": True, "requires_approval": False},
            "skill": {"enabled": False, "requires_approval": False},
        },
        "ppt": {
            "file_to_md": {"enabled": True, "requires_approval": False},
            "search_icons": {"enabled": True, "requires_approval": False},
            "list_icons": {"enabled": True, "requires_approval": False},
            "convert_pptx_to_svg": {"enabled": True, "requires_approval": True},
            "import_pptx_template": {"enabled": True, "requires_approval": True},
            "search_images": {"enabled": True, "requires_approval": False},
            "get_image_info": {"enabled": True, "requires_approval": False},
            "read_notes": {"enabled": True, "requires_approval": False},
            "batch_edit_slides": {"enabled": True, "requires_approval": False},
            "email": {"enabled": False, "requires_approval": True},
            "memory": {"enabled": False, "requires_approval": False},
        },
        "video": {
            "calc": {"enabled": False, "requires_approval": False},
            "time": {"enabled": False, "requires_approval": False},
            "file": {"enabled": False, "requires_approval": True},
            "file_to_md": {"enabled": False, "requires_approval": False},
            "skill": {"enabled": False, "requires_approval": False},
            "email": {"enabled": False, "requires_approval": True},
            "memory": {"enabled": False, "requires_approval": False},
        },
        "website": {
            "calc": {"enabled": True, "requires_approval": False},
            "time": {"enabled": True, "requires_approval": False},
            "file": {"enabled": True, "requires_approval": True},
            "npm": {"enabled": True, "requires_approval": True},
            "skill": {"enabled": False, "requires_approval": False},
            "build_website": {"enabled": True, "requires_approval": False},
            "deploy_website": {"enabled": True, "requires_approval": True},
        },
        "email": {
            "calc": {"enabled": False, "requires_approval": False},
            "time": {"enabled": False, "requires_approval": False},
            "file": {"enabled": False, "requires_approval": True},
            "skill": {"enabled": True, "requires_approval": False},
            "email": {"enabled": True, "requires_approval": True},
            "decision": {"enabled": True, "requires_approval": False},
            "memory": {"enabled": True, "requires_approval": False},
        },
        "bigdata": {
            "calc": {"enabled": True, "requires_approval": False},
            "time": {"enabled": True, "requires_approval": False},
            "file": {"enabled": False, "requires_approval": True},
            "file_to_md": {"enabled": True, "requires_approval": False},
            "memory": {"enabled": True, "requires_approval": False},
            "skill": {"enabled": False, "requires_approval": False},
        },
    }
    # 从 registrar 自动发现的工具默认 enabled=True, requires_approval=False
    discovered = _discover_all_mode_tools()
    result: dict[str, dict[str, dict[str, bool]]] = {}
    for mode in AGENT_MODES:
        tools = dict(_BASE)  # copy base
        # 自动发现的工具：默认 enabled
        for tool_name in discovered.get(mode, set()):
            if tool_name not in tools:
                tools[tool_name] = {"enabled": True, "requires_approval": False}
        # 手动覆盖
        for tool_name, cfg in _MODE_OVERRIDES.get(mode, {}).items():
            tools[tool_name] = cfg
        result[mode] = tools
    return result


TOOL_CATALOG = {
    "calc": {
        "label": "计算工具",
        "description": "执行受限的数学表达式计算，适合公式、估算和数值推导。",
        "builtin_name": "calc",
        "approval_scope": ["calculate"],
        "sub_tools": {
            "calculate": {"label": "计算", "description": "执行数学表达式计算"},
        },
    },
    "time": {
        "label": "时间工具",
        "description": "获取当前时间、时区和日期相关信息。",
        "builtin_name": "time",
        "approval_scope": ["get_now"],
        "sub_tools": {
            "get_now": {"label": "获取当前时间", "description": "获取当前时间和时区信息"},
        },
    },
    "file": {
        "label": "文件工具",
        "description": "读取、转换、写入、追加、替换、列出或删除 workspace 内文件。",
        "builtin_name": "file",
        "approval_scope": [
            "read_text_file",
            "write_text_file",
            "append_text_file",
            "replace_text_in_file",
            "delete_file",
            "list_files",
        ],
        "sub_tools": {
            "read_text_file": {"label": "读取文件", "description": "读取文本文件内容"},
            "write_text_file": {"label": "写入文件", "description": "创建或覆盖文件"},
            "append_text_file": {"label": "追加文件", "description": "向文件追加内容"},
            "replace_text_in_file": {"label": "替换内容", "description": "在文件中查找并替换文本"},
            "delete_file": {"label": "删除文件", "description": "删除 workspace 内文件"},
            "list_files": {"label": "列出文件", "description": "列出 workspace 内文件和目录"},
        },
    },
    "file_to_md": {
        "label": "文件转Markdown",
        "description": "将文档转换为 Markdown 文本，支持 .docx/.pdf/.txt/.md/.csv/.xlsx/.html 等格式。独立于文件工具组，可单独启用。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "python": {
        "label": "Python 脚本",
        "description": "运行 workspace 内 Python 脚本，适合数据处理和自动化任务。",
        "builtin_name": "python",
        "approval_scope": ["run_python_script"],
        "sub_tools": {
            "run_python_script": {"label": "运行脚本", "description": "运行 workspace 内 Python 脚本"},
        },
    },
    "git": {
        "label": "Git 工具",
        "description": "查看状态、diff、日志，也可暂存和提交代码。",
        "builtin_name": "git",
        "approval_scope": ["git_add", "git_commit", "git_diff", "git_log", "git_show", "git_status"],
        "sub_tools": {
            "git_status": {"label": "查看状态", "description": "查看工作区状态"},
            "git_diff": {"label": "查看差异", "description": "查看未暂存的差异"},
            "git_log": {"label": "查看日志", "description": "查看提交历史"},
            "git_add": {"label": "暂存文件", "description": "将文件添加到暂存区"},
            "git_commit": {"label": "提交", "description": "提交暂存的更改"},
            "git_show": {"label": "查看详情", "description": "查看某次提交的详细信息"},
        },
    },
    "npm": {
        "label": "NPM 工具",
        "description": "列出脚本、运行 npm script 或安装依赖包。",
        "builtin_name": "npm",
        "approval_scope": ["npm_list_scripts", "npm_run_script", "npm_install_package"],
        "sub_tools": {
            "npm_list_scripts": {"label": "列出脚本", "description": "获取 package.json 中的 scripts 列表"},
            "npm_run_script": {"label": "运行脚本", "description": "运行 package.json 中定义的 npm script"},
            "npm_install_package": {"label": "安装包", "description": "安装 NPM 依赖包"},
        },
    },
    "skill": {
        "label": "Skill Tool",
        "description": "Use Wuwei built-in skill capabilities for specialized workflows.",
        "builtin_name": "skill",
        "approval_scope": ["run_skill_python_script"],
        "sub_tools": {
            "run_skill_python_script": {"label": "运行技能脚本", "description": "执行 Skill 中的 Python 脚本"},
        },
    },
    "search_icons": {
        "label": "图标搜索",
        "description": "按关键词批量搜索 PPT 图标库，返回可用的图标名列表。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "list_icons": {
        "label": "列出图标库",
        "description": "列出所有可用的图标库及图标数量，用于确认图标库是否可用。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "save_slide": {
        "label": "保存幻灯片",
        "description": "将一页 SVG 幻灯片写入会话工作目录，新建或覆盖已有页。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "save_slides_batch": {
        "label": "批量保存幻灯片",
        "description": "批量保存多页幻灯片，减少 LLM 调用次数（推荐每 3 页一批）。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "read_slide": {
        "label": "读取幻灯片",
        "description": "读取已有幻灯片的 SVG 内容，用于修改前查看。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "submit_slide_plan": {
        "label": "提交幻灯片计划",
        "description": "在规划阶段提交结构化的页面计划（JSON 数组），自动弹出决策面板等待用户确认。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "submit_spec_lock": {
        "label": "提交设计参数",
        "description": "提交 spec_lock 的核心设计参数（颜色、字体、图标库），确保后续页面生成不偏离。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "calc_chart_positions": {
        "label": "图表坐标计算",
        "description": "为柱状图、饼图、折线图、雷达图和网格布局计算精确的SVG坐标。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "check_svg_quality": {
        "label": "SVG质量检查",
        "description": "检查已生成幻灯片的SVG质量，包括XML格式校验、字体安全、禁止元素检测等。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "convert_pptx_to_svg": {
        "label": "PPTX转SVG",
        "description": "将上传的PPTX文件转换为SVG，提取幻灯片中的矢量图形用于设计参考。",
        "builtin_name": None,
        "approval_scope": ["convert_pptx_to_svg"],
        "sub_tools": {
            "convert_pptx_to_svg": {"label": "转换PPTX为SVG", "description": "将上传的PPTX文件转换为SVG矢量图形"},
        },
    },
    "import_pptx_template": {
        "label": "导入PPTX模板",
        "description": "将PPTX文件作为设计模板导入，提取主题颜色、布局结构和媒体资源。",
        "builtin_name": None,
        "approval_scope": ["import_pptx_template"],
        "sub_tools": {
            "import_pptx_template": {"label": "导入PPTX模板", "description": "将PPTX文件导入为设计模板，提取主题和布局"},
        },
    },
    "copy_template": {
        "label": "复制网站模板",
        "description": "将预置的 vanilla/vue/react 基础模板复制到 data/websites/ 下，目录名自动生成（u用户ID_s会话ID_v版本号）。",
        "builtin_name": None,
        "approval_scope": ["copy_template"],
        "sub_tools": {
            "copy_template": {"label": "复制模板", "description": "复制基础项目模板到目标目录"},
        },
    },
    "check_website_project": {
        "label": "列出网站项目",
        "description": "列出 data/websites/ 下所有已创建的网站项目（含版本化目录名）。",
        "builtin_name": None,
        "approval_scope": ["check_website_project"],
        "sub_tools": {
            "check_website_project": {"label": "列出项目", "description": "列出所有已创建的网站项目"},
        },
    },
    "build_website": {
        "label": "构建网站",
        "description": "对指定项目目录执行 npm install && npm run build。",
        "builtin_name": None,
        "approval_scope": ["build_website"],
        "sub_tools": {
            "build_website": {"label": "构建项目", "description": "执行 npm install && npm run build"},
        },
    },
    "deploy_website": {
        "label": "部署网站",
        "description": "请求部署网站到 nginx 服务器，需要管理员审批。",
        "builtin_name": None,
        "approval_scope": ["deploy_website"],
        "sub_tools": {
            "deploy_website": {"label": "部署网站", "description": "提交部署请求，等待管理员审批"},
        },
    },
    "email": {
        "label": "邮件工具",
        "description": "通过 IMAP/SMTP 管理邮件，支持读取、搜索和发送。",
        "builtin_name": "email",
        "approval_scope": [
            "list_email_folders",
            "count_emails",
            "read_emails",
            "search_emails",
            "get_email",
            "send_email",
        ],
        "sub_tools": {
            "list_email_folders": {"label": "列出文件夹", "description": "列出邮箱中所有可用的文件夹/目录"},
            "count_emails": {"label": "邮件统计", "description": "按条件统计邮件数量"},
            "read_emails": {"label": "读取邮件", "description": "分页获取邮件列表"},
            "search_emails": {"label": "搜索邮件", "description": "在主题和正文中搜索关键词"},
            "get_email": {"label": "查看邮件", "description": "获取单封邮件的完整内容"},
            "send_email": {"label": "发送邮件", "description": "通过 SMTP 发送邮件，可选 CC"},
        },
    },
    "decision": {
        "label": "决策工具",
        "description": "向用户提出决策问题，提供选项让用户选择或自定义输入。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {
            "ask_user_decision": {"label": "请求决策", "description": "向用户提出决策问题，提供选项"},
        },
    },
    "memory": {
        "label": "记忆工具",
        "description": "搜索和保存用户记忆，用于个性化服务。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {
            "search_memory": {"label": "搜索记忆", "description": "搜索用户的历史记忆"},
            "save_memory": {"label": "保存记忆", "description": "保存关于用户的重要信息"},
        },
    },
    "search_images": {
        "label": "搜索图片",
        "description": "搜索免费商用图片，支持 Openverse、Wikimedia、Pexels、Pixabay 等多个来源。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "get_image_info": {
        "label": "图片信息",
        "description": "获取图片的元数据信息（尺寸、格式、是否可用）。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "read_notes": {
        "label": "读取演讲者备注",
        "description": "读取指定幻灯片的演讲者备注。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "batch_edit_slides": {
        "label": "批量编辑幻灯片",
        "description": "批量编辑已保存的幻灯片：文本替换、页码更新、删除、重排等，无需重新生成。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_search_templates": {
        "label": "搜索视频模板",
        "description": "根据意图搜索最合适的视频模板，支持 23 种专业模板。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_list_templates": {
        "label": "列出视频模板",
        "description": "列出所有可用的视频模板及其类别。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_get_template": {
        "label": "获取模板详情",
        "description": "获取指定视频模板的详细信息，包括输入参数和输出能力。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_create_project": {
        "label": "创建视频项目",
        "description": "创建一个新的视频项目，返回项目 ID 用于后续操作。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_set_template": {
        "label": "设置视频模板",
        "description": "为视频项目选择一个模板。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_set_variables": {
        "label": "设置模板变量",
        "description": "设置视频模板的变量，如标题、颜色、数据等。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_write_content_graph": {
        "label": "写入 Storyboard",
        "description": "写入多帧视频的 storyboard 结构（content-graph），用于多帧视频规划。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_write_frame_html": {
        "label": "写入帧 HTML",
        "description": "为多帧视频的指定节点写入自包含的动画 HTML。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_write_preview_html": {
        "label": "写入预览 HTML",
        "description": "写入单帧视频的预览 HTML，用于单帧视频快速路径。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_export_mp4": {
        "label": "导出 MP4",
        "description": "渲染并导出 MP4 视频文件，支持自定义分辨率和帧率。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "video_list_projects": {
        "label": "列出视频项目",
        "description": "列出所有视频项目及其状态。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "resume_ppt": {
        "label": "继续生成PPT",
        "description": "从上次中断的地方继续生成 PPT，恢复 spec_lock 和页面计划。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "check_ppt_progress": {
        "label": "查看PPT进度",
        "description": "查看当前 PPT 生成进度，包括已完成页数和剩余页面。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
    "analyze_template": {
        "label": "分析PPT模板",
        "description": "分析 PPTX 模板，提取颜色、字体、布局等设计参数。",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    },
}

# 自动生成 DEFAULT_MODE_TOOLS：base 通用工具 + registrar 自动发现 + mode 覆盖
DEFAULT_MODE_TOOLS: dict[str, dict[str, dict[str, bool]]] = _build_default_mode_tools()


def _get_catalog_entry(tool_name: str) -> dict:
    """获取工具的 catalog 条目。TOOL_CATALOG 中有的用其配置，没有的自动生成默认条目。"""
    if tool_name in TOOL_CATALOG:
        return TOOL_CATALOG[tool_name]
    return {
        "label": tool_name,
        "description": "",
        "builtin_name": None,
        "approval_scope": [],
        "sub_tools": {},
    }


# 收集所有 DEFAULT_MODE_TOOLS 中出现的工具名，用于兜底
_ALL_KNOWN_TOOLS: set[str] = set()
for _mode_tools in DEFAULT_MODE_TOOLS.values():
    _ALL_KNOWN_TOOLS.update(_mode_tools.keys())


@dataclass(frozen=True)
class RuntimeToolProfile:
    mode: str
    builtin_tools: tuple[str, ...]
    approval_tools: frozenset[str]
    signature: tuple[tuple[str, bool, bool], ...]


class ToolConfigService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    @staticmethod
    def build_display_name_map() -> dict[str, str]:
        """Build a flat {function_name: chinese_label} map from TOOL_CATALOG."""
        name_map: dict[str, str] = {}
        for tool_name, catalog_item in TOOL_CATALOG.items():
            # 从 TOOL_CATALOG 的 label 字段提取工具名
            if "label" in catalog_item:
                name_map[tool_name] = catalog_item["label"]
            # 从 sub_tools 中提取子工具名
            for name, info in catalog_item.get("sub_tools", {}).items():
                name_map[name] = info["label"]
        return name_map

    def ensure_defaults(self, db: Session) -> None:
        changed = False
        existing = {
            (row.mode, row.tool_name): row
            for row in db.scalars(select(AgentToolConfigModel)).all()
        }
        for mode, tools in DEFAULT_MODE_TOOLS.items():
            for tool_name, defaults in tools.items():
                if (mode, tool_name) in existing:
                    continue
                db.add(
                    AgentToolConfigModel(
                        mode=mode,
                        tool_name=tool_name,
                        enabled=defaults["enabled"],
                        requires_approval=defaults["requires_approval"],
                    )
                )
                changed = True
        changed = self._upgrade_website_npm_default(db) or changed
        changed = self._upgrade_ppt_skill_default(db) or changed
        if changed:
            db.commit()

    @staticmethod
    def _upgrade_website_npm_default(db: Session) -> bool:
        row = db.scalar(
            select(AgentToolConfigModel).where(
                AgentToolConfigModel.mode == "website",
                AgentToolConfigModel.tool_name == "npm",
            )
        )
        if row is None:
            return False
        if row.enabled is False and row.requires_approval is True:
            row.enabled = True
            db.add(row)
            return True
        return False

    @staticmethod
    def _upgrade_ppt_skill_default(db: Session) -> bool:
        row = db.scalar(
            select(AgentToolConfigModel).where(
                AgentToolConfigModel.mode == "ppt",
                AgentToolConfigModel.tool_name == "skill",
            )
        )
        if row is None:
            return False
        if row.enabled is False:
            row.enabled = True
            row.requires_approval = False
            db.add(row)
            return True
        return False

    @staticmethod
    def _parse_approval_sub_tools(row: AgentToolConfigModel) -> list[str]:
        import json
        try:
            parsed = json.loads(row.approval_sub_tools_json)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    @staticmethod
    def _build_sub_tools_list(catalog_item: dict) -> list[dict[str, str]]:
        return [
            {"name": name, "label": info["label"], "description": info["description"]}
            for name, info in catalog_item.get("sub_tools", {}).items()
        ]

    def list_configs(self) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            rows = db.scalars(select(AgentToolConfigModel).order_by(AgentToolConfigModel.mode.asc())).all()

        configs_by_mode: dict[str, list[dict[str, object]]] = {mode: [] for mode in AGENT_MODES}
        for row in rows:
            if row.mode not in AGENT_MODES:
                continue
            configs_by_mode[row.mode].append(
                {
                    "mode": row.mode,
                    "tool_name": row.tool_name,
                    "enabled": row.enabled,
                    "requires_approval": row.requires_approval,
                    "approval_sub_tools": parse_approval_sub_tools(row.approval_sub_tools_json),
                }
            )

        # catalog: TOOL_CATALOG 手动条目 + DEFAULT_MODE_TOOLS 中自动发现的条目
        all_tool_names = set(TOOL_CATALOG.keys()) | _ALL_KNOWN_TOOLS
        return {
            "catalog": [
                {
                    "name": name,
                    "label": _get_catalog_entry(name)["label"],
                    "description": _get_catalog_entry(name)["description"],
                    "approval_scope": _get_catalog_entry(name)["approval_scope"],
                    "sub_tools": self._build_sub_tools_list(_get_catalog_entry(name)),
                }
                for name in sorted(all_tool_names)
            ],
            "modes": [
                {
                    "mode": mode,
                    "label": meta["label"],
                    "description": meta["description"],
                    "tools": configs_by_mode[mode],
                }
                for mode, meta in AGENT_MODES.items()
            ],
        }

    def update_mode(self, mode: str, tools: list[dict[str, object]]) -> dict[str, object]:
        if mode not in AGENT_MODES:
            raise KeyError("Unknown agent mode")

        import json

        with self.session_factory() as db:
            self.ensure_defaults(db)
            existing = {
                row.tool_name: row
                for row in db.scalars(select(AgentToolConfigModel).where(AgentToolConfigModel.mode == mode)).all()
            }
            for item in tools:
                tool_name = str(item["tool_name"])
                if tool_name not in _ALL_KNOWN_TOOLS:
                    raise KeyError(f"Unknown tool: {tool_name}")
                row = existing.get(tool_name)
                if row is None:
                    row = AgentToolConfigModel(mode=mode, tool_name=tool_name)
                    db.add(row)
                row.enabled = bool(item["enabled"])
                row.requires_approval = bool(item["requires_approval"])
                sub_tools = item.get("approval_sub_tools", [])
                if isinstance(sub_tools, list):
                    row.approval_sub_tools_json = json.dumps(sub_tools, ensure_ascii=False)
            db.commit()

        return self.list_configs()

    def get_runtime_profile(self, mode: str) -> RuntimeToolProfile:
        mode = mode if mode in AGENT_MODES else "general"
        with self.session_factory() as db:
            self.ensure_defaults(db)
            rows = db.scalars(
                select(AgentToolConfigModel)
                .where(AgentToolConfigModel.mode == mode)
                .order_by(AgentToolConfigModel.tool_name.asc())
            ).all()

        builtin_tools: list[str] = []
        approval_tools: set[str] = set()
        signature: list[tuple[str, bool, bool]] = []
        for row in rows:
            catalog_item = _get_catalog_entry(row.tool_name)
            signature.append((row.tool_name, row.enabled, row.requires_approval))
            if not row.enabled:
                continue
            if catalog_item.get("builtin_name"):
                builtin_tools.append(catalog_item["builtin_name"])
            if row.requires_approval:
                configured_sub_tools = parse_approval_sub_tools(row.approval_sub_tools_json)
                all_sub_tools = list(catalog_item["sub_tools"].keys())
                if configured_sub_tools:
                    # Only the explicitly listed sub-tools require approval
                    approval_tools.update(
                        item for item in configured_sub_tools
                        if item in all_sub_tools
                    )
                else:
                    # Empty list = ALL sub-tools require approval (backward compatible)
                    approval_tools.update(str(item) for item in catalog_item["approval_scope"])

        return RuntimeToolProfile(
            mode=mode,
            builtin_tools=tuple(dict.fromkeys(builtin_tools)),
            approval_tools=frozenset(approval_tools),
            signature=tuple(signature),
        )


def seed_tool_configs() -> None:
    ToolConfigService().list_configs()
