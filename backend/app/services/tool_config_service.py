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
        "description": "优先生成结构化演示文稿，默认不启用外部工具。",
    },
    "website": {
        "label": "网站模式",
        "description": "用于页面方案、前端代码和交互式应用生成。",
    },
}

TOOL_CATALOG = {
    "calc": {
        "label": "计算工具",
        "description": "执行受限的数学表达式计算，适合公式、估算和数值推导。",
        "builtin_name": "calc",
        "approval_scope": ["calculate"],
    },
    "time": {
        "label": "时间工具",
        "description": "获取当前时间、时区和日期相关信息。",
        "builtin_name": "time",
        "approval_scope": ["time"],
    },
    "file": {
        "label": "文件工具",
        "description": "读取、转换、写入、追加、替换或删除 workspace 内文件。",
        "builtin_name": "file",
        "approval_scope": [
            "file",
            "file_to_md",
            "read_text_file",
            "write_text_file",
            "append_text_file",
            "replace_text_in_file",
            "delete_file",
        ],
    },
    "python": {
        "label": "Python 脚本",
        "description": "运行 workspace 内 Python 脚本，适合数据处理和自动化任务。",
        "builtin_name": "python",
        "approval_scope": ["python", "run_python_script"],
    },
    "git": {
        "label": "Git 工具",
        "description": "查看状态、diff、日志，也可暂存和提交代码。",
        "builtin_name": "git",
        "approval_scope": ["git", "git_add", "git_commit", "git_diff", "git_log", "git_show", "git_status"],
    },
    "npm": {
        "label": "NPM 工具",
        "description": "读取脚本、运行 npm script 或安装依赖包。",
        "builtin_name": "npm",
        "approval_scope": ["npm", "npm_run_script", "npm_install_package"],
    },
    "skill": {
        "label": "Skill Tool",
        "description": "Use Wuwei built-in skill capabilities for specialized workflows.",
        "builtin_name": "skill",
        "approval_scope": ["run_skill_python_script"],
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
        "skill": {"enabled": False, "requires_approval": True},
    },
    "ppt": {
        "calc": {"enabled": True, "requires_approval": False},
        "time": {"enabled": False, "requires_approval": False},
        "file": {"enabled": False, "requires_approval": True},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": False, "requires_approval": True},
        "skill": {"enabled": False, "requires_approval": True},
    },
    "website": {
        "calc": {"enabled": True, "requires_approval": False},
        "time": {"enabled": True, "requires_approval": False},
        "file": {"enabled": True, "requires_approval": True},
        "python": {"enabled": False, "requires_approval": True},
        "git": {"enabled": False, "requires_approval": True},
        "npm": {"enabled": True, "requires_approval": True},
        "skill": {"enabled": False, "requires_approval": True},
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
                }
            )

        return {
            "catalog": [
                {
                    "name": name,
                    "label": item["label"],
                    "description": item["description"],
                    "approval_scope": item["approval_scope"],
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
            builtin_tools.append(str(catalog_item["builtin_name"]))
            if row.requires_approval:
                approval_tools.update(str(item) for item in catalog_item["approval_scope"])

        return RuntimeToolProfile(
            mode=mode,
            builtin_tools=tuple(dict.fromkeys(builtin_tools)),
            approval_tools=frozenset(approval_tools),
            signature=tuple(signature),
        )


def seed_tool_configs() -> None:
    ToolConfigService().list_configs()
