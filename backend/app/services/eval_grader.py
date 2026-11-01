"""LLM 评分器：评测用例的语义判分（关键词规则之上的升级）。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

_logger = logging.getLogger("llmops.grader")

_SYSTEM = (
    "你是一个严格的 AI 输出质量评分器。根据评分要求判断「智能体输出」是否合格。"
    "只输出 JSON：{\"passed\": true/false, \"score\": 0.0~1.0, \"reason\": \"一句话理由\"}。"
    "宁可严格，不要放水。"
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_verdict(text: str) -> dict[str, Any] | None:
    try:
        match = _JSON_RE.search(text)
        if not match:
            return None
        data = json.loads(match.group(0))
        if not isinstance(data, dict) or "passed" not in data:
            return None
        score = data.get("score")
        return {
            "passed": bool(data.get("passed")),
            "score": round(float(score), 2) if isinstance(score, (int, float)) else (1.0 if data.get("passed") else 0.0),
            "reason": str(data.get("reason") or "")[:300],
        }
    except Exception:  # noqa: BLE001
        return None


def default_criteria(expected: dict[str, Any]) -> str:
    """评分依据：显式 criteria > 关键词要求 > 「回答正确且切题」。"""
    criteria = str(expected.get("criteria") or "").strip()
    if criteria:
        return criteria
    parts = []
    if expected.get("contains"):
        parts.append("必须包含这些信息：" + "、".join(str(k) for k in expected["contains"]))
    if expected.get("not_contains"):
        parts.append("不得包含这些内容：" + "、".join(str(k) for k in expected["not_contains"]))
    return "；".join(parts) if parts else "回答正确、切题且完整。"


async def grade_with_llm(case_input: str, output: str, expected: dict[str, Any]) -> dict[str, Any] | None:
    """LLM 语义判分。任何失败返回 None（调用方退回关键词规则）。"""
    criteria = default_criteria(expected)
    try:
        from wuwei.core.message import HumanMessage, SystemMessage

        from app.services.memory_pipeline import build_llm

        gateway = build_llm(role="fast", max_tokens=300, timeout=45)
        prompt = (
            f"【用户输入】\n{case_input[:1500]}\n\n"
            f"【智能体输出】\n{output[:2500] or '（空输出）'}\n\n"
            f"【评分要求】\n{criteria}\n\n"
            "请评分并只输出 JSON。"
        )
        resp = await gateway.generate([SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)])
        content = getattr(getattr(resp, "message", None), "content", "") or ""
        verdict = _parse_verdict(content)
        if verdict is None:
            _logger.warning("llm grader returned unparsable output: %s", content[:120])
        return verdict
    except Exception as e:  # noqa: BLE001 -- 评分失败绝不拖垮评测
        _logger.warning("llm grader failed: %s", e)
        return None
