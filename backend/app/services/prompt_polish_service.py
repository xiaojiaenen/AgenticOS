"""提示词润色服务。

对用户在输入框里写的原始提示词做「意图分析 → 结构化改写」，
输出更适合 Agent 执行的长提示词。前端支持一键取消（还原原文）。

设计要点：
- 纯提示词服务，不落库：润色结果属于"发送前草稿"，没有会话上下文时
  也应可用（session_id 仅用于透传当前智能体，避免润色出的 prompt
  与所选智能体能力错配）。
- 只做改写不改意图：明确要求模型不得自行发挥或追加需求。
- 复用与聊天一致的 LLM 构建路径（cookie 优先、OPENAI_* 回退）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000
MAX_OUTPUT_CHARS = 2000

POLISH_SYSTEM_PROMPT = """你是 AgenticOS 的提示词工程师。你的任务是把用户的原始需求改写成一条意图清晰、要求明确、可直接执行的高质量提示词。

工作步骤（先理解，再改写）：
1. 意图分析：判断用户的真实目标、交付物类型（问答 / 代码 / 文档 / 数据 / 网站 / 演示文稿）、关键约束与隐含期待。
2. 结构化改写：输出一条完整的中文提示词，必要时包含目标、上下文、约束、输出要求。

铁律：
- 不得改变或臆造用户意图，不得自行追加用户没提的需求、示例数据或技术选型；信息不足的地方用「（待补充）」占位。
- 保留用户给出的所有具体信息（数字、文件名、字段名、指标口径）。
- 不要输出解释、评论、标题或 Markdown 代码块围栏，只输出润色后的提示词正文。
- 用户输入已足够清晰时，改写幅度要小，保持贴近原文。
"""


def build_polish_messages(raw_text: str) -> list[Any]:
    """构造润色请求的消息列表（便于单测断言提示词约定）。"""
    from wuwei.core.message import HumanMessage, SystemMessage

    return [
        SystemMessage(content=POLISH_SYSTEM_PROMPT),
        HumanMessage(content=f"用户的原始提示词：\n\n{raw_text}"),
    ]


def _clean_polished(text: str) -> str:
    """清理模型输出：去掉可能的围栏/前缀说明，压缩多余空行。"""
    result = (text or "").strip()
    if result.startswith("```"):
        # ```markdown ... ``` / ```text ... ```
        lines = result.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        result = "\n".join(lines).strip()
    # 少数模型会加「润色后的提示词：」之类前缀
    for prefix in ("润色后的提示词：", "润色后的提示词:", "提示词：", "优化后的提示词："):
        if result.startswith(prefix):
            result = result[len(prefix) :].strip()
            break
    result = "\n".join(line.rstrip() for line in result.splitlines())
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    return result[:MAX_OUTPUT_CHARS].strip()


async def polish_prompt(raw_text: str, *, user_id: int | None = None, timeout: int = 60) -> dict[str, Any]:
    """润色提示词，返回 {polished, changed, original}。"""
    from app.core.config import get_settings
    from app.services.upstream.llm_factory import build_llm_for_user

    original = (raw_text or "").strip()
    if not original:
        return {"polished": "", "changed": False, "original": ""}
    if len(original) > MAX_INPUT_CHARS:
        original = original[:MAX_INPUT_CHARS]

    settings = get_settings()
    llm = build_llm_for_user(
        user_id,
        max_tokens=min(settings.agent_max_tokens, 2000),
        timeout=timeout,
        model=settings.openai_model,
        prefer_cookie=True,
    )
    response = await llm.generate(build_polish_messages(original))
    polished = _clean_polished(getattr(getattr(response, "message", None), "content", "") or "")

    logger.info(
        "prompt polished: user=%s in_len=%d out_len=%d changed=%s",
        user_id, len(original), len(polished), polished != original,
    )
    return {
        "polished": polished,
        "changed": bool(polished) and polished != original,
        "original": original,
    }