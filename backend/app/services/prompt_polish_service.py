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

POLISH_SYSTEM_PROMPT = """你是一个提示词改写器。用户会给你一句他自己写的、可能很模糊的话（比如「帮我看下数据」「搞个总结」）。你的工作是把这句话**改写得更清楚、更具体**，让另一台 AI 能准确执行。

**输出必须仍然是一条「用户对 AI 说的话」**（第一人称或祈使句，像用户在提要求），不是 AI 的回答。绝不能写成：
- 「好的，我来帮你…」这类回应
- 「根据您提供的信息…」这类分析
- 分点罗列你已经完成的结论

改写要做的事（按需，不必全做）：
1. **补全目标**：这句话想要什么结果？（一份总结 / 一张对比表 / 一段可运行的代码）
2. **补全对象与范围**：对什么做、覆盖哪些部分、时间/数量范围。
3. **补全约束**：格式、篇幅、语言、风格、必须包含或必须避免的内容。
4. **修正模糊指代**：「那个表」「上边说的」——如果原文没有上下文，用「（补充：具体指哪个）」标注待确认，不要凭空编造事实。
5. 修正错别字、语病、标点，整理成通顺的中文。

**边界**：
- 可以把一句话扩展成一小段（含要求要点），因为模糊的短句本来就缺信息；但不要写成长篇报告，一般不超过原文的 4 倍。
- 不要替用户做业务决策（不要编造具体的数字、文件名、人名）。
- 不要解释你在做什么，不要加「润色后：」之类前缀，直接输出改写后的提示词。
- 如果用户原句已经很完整清楚，小幅优化即可。

示例：
原文：帮我看下数据
输出：请分析我提供的数据，说明整体趋势、异常值和你发现的主要问题，并用要点列出结论。

原文：写个总结
输出：请把下面的内容总结成一段 200 字以内的概述，先给结论，再列 2-3 条关键依据。

原文：帮我搞个网站
输出：请帮我做一个单页网站：包含顶部标题区、三栏功能介绍和底部联系方式；整体风格简洁、适配手机；不需要后端接口。"""


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

    # 护栏一：扩写上限。润色允许把模糊短句补成一小段（缺信息本来就该补），
    # 但 4 倍以上通常意味着模型在写报告而不是改提示词。
    if polished and len(polished) > max(120, int(len(original) * 4)):
        logger.warning(
            "prompt polish rejected (over-expanded): user=%s in_len=%d out_len=%d",
            user_id, len(original), len(polished),
        )
        polished = ""

    # 护栏二：回复体识别。模型有时会把"改写提示词"理解成"回答问题"，
    # 输出「好的，我来帮你…」「根据您提供的信息…」这类 AI 回应。这类文本
    # 填回输入框等于把 AI 的话当用户指令再发一遍，必须拦掉。
    if polished:
        head = polished[:40]
        reply_markers = ("好的", "当然可以", "我来帮你", "以下是", "根据您提供", "为您", "希望这", "总结如下")
        if any(head.startswith(m) for m in reply_markers):
            logger.warning(
                "prompt polish rejected (looks like an AI reply): user=%s head=%r",
                user_id, head,
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