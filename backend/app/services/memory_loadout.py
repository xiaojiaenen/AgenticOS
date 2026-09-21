"""Agent 记忆装配层：按 Agent 模式决定记忆注入策略。

不同模式注入不同体量、不同优先级的记忆：
- general: 完整装配（画像 + 场景 + atom + 技能提示）
- ppt: 仅画像（PPT 是一次性任务，不需要历史上下文）
- website: 画像 + 少量场景（聚焦当前开发任务）
- email: 画像 + 少量 atom（需要用户身份但不需要项目上下文）

对应 TencentDB Agent Memory 的 "Memory Loadout" 理念：
- 不是所有记忆都注入，按 Agent 角色装配
- 字符预算严格控制，避免挤占主对话上下文
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.memory_retriever import get_retriever

_logger = logging.getLogger("memory_loadout")


@dataclass(frozen=True)
class MemoryLoadout:
    """Agent 记忆装配配置"""
    persona_enabled: bool       # 是否注入 L3 画像
    scenario_limit: int         # 注入 L2 场景数
    atom_limit: int             # 注入 L1 atom 数
    char_budget: int            # 总字符预算
    include_skills: bool        # 是否提示技能（Skill 索引由工具调用，不直接注入）


# 按 Agent 模式预设装配策略
DEFAULT_LOADOUTS: dict[str, MemoryLoadout] = {
    "general": MemoryLoadout(
        persona_enabled=True,
        scenario_limit=2,
        atom_limit=3,
        char_budget=2000,
        include_skills=True,
    ),
    "ppt": MemoryLoadout(
        persona_enabled=True,
        scenario_limit=0,
        atom_limit=0,
        char_budget=300,
        include_skills=False,
    ),
    "website": MemoryLoadout(
        persona_enabled=True,
        scenario_limit=1,
        atom_limit=2,
        char_budget=1500,
        include_skills=True,
    ),
    "email": MemoryLoadout(
        persona_enabled=True,
        scenario_limit=1,
        atom_limit=1,
        char_budget=800,
        include_skills=False,
    ),
}


async def assemble_memory_context(
    user_id: int,
    query: str,
    mode: str,
) -> str:
    """装配记忆上下文，返回格式化的提示词块（空字符串表示无需注入）

    被 agent_service.stream_chat 在 LLM 调用前调用。
    """
    loadout = DEFAULT_LOADOUTS.get(mode, DEFAULT_LOADOUTS["general"])

    # PPT/纯任务模式：几乎不需要历史记忆
    if loadout.scenario_limit == 0 and loadout.atom_limit == 0:
        if not loadout.persona_enabled:
            return ""
        # 仅注入 L3 画像（retriever 内部会处理 persona）
        retriever = get_retriever()
        hits = await retriever.retrieve(
            user_id, query,
            layers=("L1",),  # 占位，主要为了拿 persona
            char_budget=loadout.char_budget,
            limit=1,
        )
        persona_hits = [h for h in hits if h.get("layer") == "L3"]
        return _format_memory_block(persona_hits)

    # 通用装配
    retriever = get_retriever()
    total_limit = loadout.scenario_limit + loadout.atom_limit
    hits = await retriever.retrieve(
        user_id, query,
        layers=("L1", "L2"),
        char_budget=loadout.char_budget,
        limit=total_limit,
    )

    if not hits:
        return ""

    return _format_memory_block(hits)


def _format_memory_block(hits: list[dict]) -> str:
    """格式化为 LLM 提示词块"""
    if not hits:
        return ""

    lines = ["## 用户记忆（来自历史对话，自动蒸馏）"]

    persona_lines: list[str] = []
    scenario_lines: list[str] = []
    atom_lines: list[str] = []

    for hit in hits:
        layer = hit.get("layer", "L1")
        content = hit.get("content", "")
        if not content:
            continue

        if layer == "L3":
            persona_lines.append(content)
        elif layer == "L2":
            title = hit.get("title", "")
            if title:
                scenario_lines.append(f"### 场景: {title}\n{content}")
            else:
                scenario_lines.append(content)
        else:  # L1
            mem_type = hit.get("memory_type", "fact")
            atom_lines.append(f"- [{mem_type}] {content}")

    if persona_lines:
        lines.append("\n### 用户画像")
        lines.extend(persona_lines)

    if scenario_lines:
        lines.append("\n### 相关场景")
        lines.extend(scenario_lines)

    if atom_lines:
        lines.append("\n### 关键事实")
        lines.extend(atom_lines)

    lines.append("\n（以上记忆自动注入，回答时自然参考即可，不必显式引用）")
    return "\n".join(lines)
