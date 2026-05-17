from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentToolConfigModel
from app.db.session import create_db_session

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
    "email": {
        "label": "邮件模式",
        "description": "读取、搜索、发送公司邮件，支持抄送功能。",
    },
}

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
            "file_to_md",
            "read_text_file",
            "write_text_file",
            "append_text_file",
            "replace_text_in_file",
            "delete_file",
            "list_files",
        ],
        "sub_tools": {
            "file_to_md": {"label": "文件转Markdown", "description": "将文件转换为 Markdown 格式"},
            "read_text_file": {"label": "读取文件", "description": "读取文本文件内容"},
            "write_text_file": {"label": "写入文件", "description": "创建或覆盖文件"},
            "append_text_file": {"label": "追加文件", "description": "向文件追加内容"},
            "replace_text_in_file": {"label": "替换内容", "description": "在文件中查找并替换文本"},
            "delete_file": {"label": "删除文件", "description": "删除 workspace 内文件"},
            "list_files": {"label": "列出文件", "description": "列出 workspace 内文件和目录"},
        },
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
    "save_slide": {
        "label": "保存幻灯片",
        "description": "将一页 SVG 幻灯片写入会话工作目录，新建或覆盖已有页。",
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
}

DEFAULT_MODE_TOOLS: dict[str, dict[str, dict[str, bool]]] = {
    "general": {
        "calc": {"enabled": True, "requires_approval": False},
        "time": {"enabled": True, "requires_approval": False},
        "file": {"enabled": True, "requires_approval": True},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": False, "requires_approval": True},
        "skill": {"enabled": False, "requires_approval": False},
    },
    "ppt": {
        "calc": {"enabled": False, "requires_approval": False},
        "time": {"enabled": False, "requires_approval": False},
        "file": {"enabled": False, "requires_approval": True},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": False, "requires_approval": True},
        "skill": {"enabled": True, "requires_approval": False},
        "search_icons": {"enabled": True, "requires_approval": False},
        "save_slide": {"enabled": True, "requires_approval": False},
        "read_slide": {"enabled": True, "requires_approval": False},
    },
    "website": {
        "calc": {"enabled": True, "requires_approval": False},
        "time": {"enabled": True, "requires_approval": False},
        "file": {"enabled": True, "requires_approval": True},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": True, "requires_approval": True},
        "skill": {"enabled": False, "requires_approval": False},
    },
    "email": {
        "calc": {"enabled": True, "requires_approval": False},
        "time": {"enabled": True, "requires_approval": False},
        "file": {"enabled": False, "requires_approval": True},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": False, "requires_approval": True},
        "skill": {"enabled": True, "requires_approval": False},
    },
}


@dataclass(frozen=True)
class RuntimeToolProfile:
    mode: str
    builtin_tools: tuple[str, ...]
    approval_tools: frozenset[str]
    signature: tuple[tuple[str, bool, bool], ...]


class ToolConfigService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

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
            if row.mode not in AGENT_MODES or row.tool_name not in TOOL_CATALOG:
                continue
            configs_by_mode[row.mode].append(
                {
                    "mode": row.mode,
                    "tool_name": row.tool_name,
                    "enabled": row.enabled,
                    "requires_approval": row.requires_approval,
                    "approval_sub_tools": self._parse_approval_sub_tools(row),
                }
            )

        return {
            "catalog": [
                {
                    "name": name,
                    "label": item["label"],
                    "description": item["description"],
                    "approval_scope": item["approval_scope"],
                    "sub_tools": self._build_sub_tools_list(item),
                }
                for name, item in TOOL_CATALOG.items()
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
                if tool_name not in TOOL_CATALOG:
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
            catalog_item = TOOL_CATALOG.get(row.tool_name)
            if not catalog_item:
                continue
            signature.append((row.tool_name, row.enabled, row.requires_approval))
            if not row.enabled:
                continue
            if catalog_item.get("builtin_name"):
                builtin_tools.append(catalog_item["builtin_name"])
            if row.requires_approval:
                configured_sub_tools = self._parse_approval_sub_tools(row)
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
