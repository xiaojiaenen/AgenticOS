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

POLISH_SYSTEM_PROMPT = """你是文字编辑。用户的输入是他在输入框里要说给 AI 听的一句话（或几句话），请把它改得更清楚、更书面、更少歧义。

这是**润色**，不是扩写，也不是回答。三条铁律：
- 输出长度与原文相当（最多比原文长 20%）。绝不扩写成多段、绝不加标题/小标题/列表/编号/「目标」「上下文」「约束」「输出要求」等结构化小节。
- 不回答问题、不执行任务、不评论、不解释你在做什么。只返回改写后的同一句话。
- 不改用户意图，不补充他没说的信息、示例、字段或技术选型；只修正语病、口语碎片、指代不清、错别字与标点。

示例：
原文：帮我把那个表弄一下
输出：请整理一下这份表格。

原文：ppt 那个配色再改改 太花了
输出：PPT 的配色再调整一下，现在有点花。

原文：你好
输出：你好

直接输出最终句子，不要任何前后缀。"""


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
    from app.services.llm_factory import build_llm_for_user

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
        # 润色是轻任务：按「快速」用途取模型，没绑定时退回提供商主模型。
        # 用主模型也行，但企业网关里把小任务指到小模型能省下可观的额度。
        model=None,
        role="fast",
    )
    response = await llm.generate(build_polish_messages(original))
    polished = _clean_polished(getattr(getattr(response, "message", None), "content", "") or "")

    # 长度护栏：润色不该把一句话膨胀成一段话。模型偶发无视提示词时，
    # 宁可放弃这次润色（changed=False，前端提示「已经足够清晰」），
    # 也不要把一段 AI 腔扩写塞回用户输入框。
    if polished and len(polished) > max(60, int(len(original) * 1.6)):
        logger.warning(
            "prompt polish rejected (over-expanded): user=%s in_len=%d out_len=%d",
            user_id, len(original), len(polished),
        )
        polished = ""

    logger.info(
        "prompt polished: user=%s in_len=%d out_len=%d changed=%s",
        user_id, len(original), len(polished), polished != original,
    )
    return {
        "polished": polished,
        "changed": bool(polished) and polished != original,
        "original": original,
    }