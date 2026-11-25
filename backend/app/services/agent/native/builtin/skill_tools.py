"""技能工具（自 wuwei/plugin/builtin/skill.py 移植，wuwei 退役 A5-5）。

工具语义逐条保留（list_skills / load_skill / load_skill_reference /
run_skill_python_script + load_token 安全机制）；allowed_tools 白名单的
强制（原 SkillPromptMiddleware.before_tool）由引擎在工具执行前检查
（见 langgraph_engine.engine）。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

SKILL_INSTRUCTION = """你可以使用以下技能：
{skill_text}

使用 load_skill 工具加载技能的详细内容和使用说明。"""

SKILL_SCRIPT_TIMEOUT_SECONDS = 10
SKILL_SCRIPT_OUTPUT_LIMIT = 4000
SKILL_REFERENCE_READ_LIMIT = 20_000

#: 技能管理与账本类工具不受 allowed_tools 限制
ALWAYS_ALLOWED_TOOLS = frozenset({
    "list_skills", "load_skill", "load_skill_reference", "run_skill_python_script",
})


def _truncate_text(text: str, *, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit], True


def _resolve_skill_file(skill_path: str, relative_path: str, required_dir: str) -> Path:
    root_dir = Path(skill_path).resolve()
    target_path = (root_dir / relative_path).resolve()
    if target_path == root_dir or root_dir not in target_path.parents:
        raise ValueError("文件路径必须位于 skill 目录内")
    if not target_path.is_file():
        raise ValueError(f"文件不存在: {relative_path}")
    resolved_relative = target_path.relative_to(root_dir)
    if not resolved_relative.parts or resolved_relative.parts[0] != required_dir:
        raise ValueError(f"当前仅允许访问 skill 目录下 {required_dir}/ 中的文件")
    return target_path


class SkillToolBox:
    """技能工具集合（注册进注册表；持有 SkillManager 与 load_token 账本）。"""

    def __init__(self, skill_manager) -> None:
        self.skill_manager = skill_manager
        self.loaded_skill_tokens: dict[str, str] = {}
        #: 激活技能的 allowed_tools 白名单（None = 不限制）；引擎执行前检查
        self.active_allowed_tools: list[str] | None = None

    def _assert_loaded(self, skill_name: str, load_token: str) -> None:
        if self.loaded_skill_tokens.get(load_token) != skill_name:
            raise ValueError(
                "使用 skill 附属资源前必须先调用 load_skill，并使用 load_skill 返回的 load_token。"
            )

    def register(self, registry) -> None:
        """注册 4 个技能工具到注册表。"""
        toolbox = self

        @registry.tool(
            name="list_skills",
            description="列出当前可用技能的摘要。先查看技能列表，再自行判断是否需要某个 skill。",
            display_name="列出技能",
        )
        def list_skills() -> list[dict[str, object]]:
            items: list[dict[str, object]] = []
            for skill in toolbox.skill_manager.list_skills():
                items.append(
                    {
                        "name": skill.name,
                        "description": skill.description,
                        "has_python_scripts": bool(skill.scripts),
                        "python_scripts": skill.scripts,
                        "has_references": bool(skill.references),
                        "references": skill.references,
                    }
                )
            return items

        @registry.tool(
            name="load_skill",
            description="根据技能名称加载技能正文。选中 skill 后再调用这个工具。",
            display_name="加载技能",
        )
        def load_skill(skill_name: str) -> dict[str, object]:
            skill = toolbox.skill_manager.get_skill(skill_name)
            instruction = toolbox.skill_manager.load_skill_instruction(skill_name)
            if not instruction:
                raise ValueError(f"Skill '{skill_name}' 不存在或没有正文")
            load_token = uuid.uuid4().hex
            toolbox.loaded_skill_tokens[load_token] = skill.name
            toolbox.active_allowed_tools = list(skill.allowed_tools) or None
            return {
                "name": skill.name,
                "description": skill.description,
                "instruction": instruction,
                "load_token": load_token,
                "python_scripts": skill.scripts,
                "references": skill.references,
            }

        @registry.tool(
            name="load_skill_reference",
            description=(
                "读取已加载 skill 的 references/ 目录中的单个参考文件。"
                "必须传入 load_skill 返回的 load_token；只在 skill 正文要求阅读参考资料时使用。"
            ),
            display_name="加载技能参考",
        )
        def load_skill_reference(
            skill_name: str,
            reference_path: str,
            load_token: str,
            max_chars: int = SKILL_REFERENCE_READ_LIMIT,
        ) -> dict[str, object]:
            skill = toolbox.skill_manager.get_skill(skill_name)
            if not skill.path:
                raise ValueError(f"Skill '{skill_name}' 没有关联目录")
            toolbox._assert_loaded(skill.name, load_token)
            if reference_path not in skill.references:
                raise ValueError(f"Skill '{skill_name}' 没有这个 reference: {reference_path}")
            target_path = _resolve_skill_file(skill.path, reference_path, "references")
            text = target_path.read_text(encoding="utf-8", errors="replace")
            content, truncated = _truncate_text(text, limit=max_chars)
            return {
                "ok": True,
                "skill_name": skill.name,
                "reference_path": reference_path,
                "content": content,
                "truncated": truncated,
                "size_chars": len(text),
            }

        @registry.tool(
            name="run_skill_python_script",
            description=(
                "执行 skill 目录下 scripts/ 中的 Python 脚本。"
                "只有在已经加载该 skill 且正文明确要求执行脚本时才使用。"
                "必须传入 load_skill 返回的 load_token。"
            ),
            timeout_seconds=SKILL_SCRIPT_TIMEOUT_SECONDS + 1,
            side_effect=True,
            requires_approval=True,
            display_name="运行技能脚本",
        )
        def run_skill_python_script(
            skill_name: str,
            script_path: str,
            load_token: str,
            args_json: str = "[]",
        ) -> dict[str, object]:
            skill = toolbox.skill_manager.get_skill(skill_name)
            if not skill.path:
                raise ValueError(f"Skill '{skill_name}' 没有关联目录")
            toolbox._assert_loaded(skill.name, load_token)
            if script_path not in skill.scripts:
                raise ValueError(f"Skill '{skill_name}' 没有这个 script: {script_path}")

            import json as _json

            try:
                script_args = _json.loads(args_json)
            except _json.JSONDecodeError as exc:
                raise ValueError("args_json 必须是合法 JSON 数组") from exc
            if not isinstance(script_args, list):
                raise ValueError("args_json 必须是 JSON 数组")

            target_path = _resolve_skill_file(skill.path, script_path, "scripts")
            result = subprocess.run(
                [sys.executable, str(target_path), *script_args],
                capture_output=True,
                text=True,
                timeout=SKILL_SCRIPT_TIMEOUT_SECONDS,
            )
            stdout = result.stdout or ""
            if len(stdout) > SKILL_SCRIPT_OUTPUT_LIMIT:
                stdout = stdout[:SKILL_SCRIPT_OUTPUT_LIMIT] + f"\n... [truncated {len(stdout) - SKILL_SCRIPT_OUTPUT_LIMIT} chars]"
            return {
                "ok": result.returncode == 0,
                "skill_name": skill.name,
                "script_path": script_path,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": (result.stderr or "")[:SKILL_SCRIPT_OUTPUT_LIMIT],
            }

    def instruction_text(self) -> str | None:
        """可用技能列表的提示词（无技能时返回 None）。"""
        skills = self.skill_manager.list_skills()
        if not skills:
            return None
        skill_lines = [f"- {s.name}: {s.description}" for s in skills]
        return SKILL_INSTRUCTION.format(skill_text="\n".join(skill_lines))
