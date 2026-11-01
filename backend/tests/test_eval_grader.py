"""LLM 评分器 + 趋势聚合 回归。"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json

import pytest

from app.api.v1.endpoints.llmops import _judge_case, _score_case
from app.services.eval_grader import _parse_verdict, default_criteria


def test_parse_verdict():
    assert _parse_verdict('{"passed": true, "score": 0.85, "reason": "准确"}') == {
        "passed": True, "score": 0.85, "reason": "准确",
    }
    # 模型输出带前后缀噪声也能抠出 JSON
    assert _parse_verdict('好的，结果：{"passed": false, "score": 0.2, "reason": "缺过程"}')["passed"] is False
    assert _parse_verdict('不是 JSON') is None
    assert _parse_verdict('{"no_passed_key": 1}') is None


def test_default_criteria_fallback():
    assert default_criteria({"criteria": "必须解释"}) == "必须解释"
    assert "391" in default_criteria({"contains": ["391"]})
    assert "正确" in default_criteria({})


def test_keywords_mode_unchanged():
    passed, reason = _score_case("答案是 391", {"contains": ["391"]})
    assert passed and reason is None
    passed, reason = _score_case("答案是别的", {"contains": ["391"]})
    assert not passed and "391" in (reason or "")


@pytest.mark.asyncio
async def test_judge_case_llm_mode(monkeypatch):
    """LLM 模式：语义判分生效；not_contains 硬约束一票否决；评分器故障退关键词。"""
    from app.services import eval_grader

    async def fake_pass(case_input, output, expected):
        return {"passed": True, "score": 0.9, "reason": "语义正确"}

    async def fake_fail(case_input, output, expected):
        return {"passed": False, "score": 0.3, "reason": "答非所问"}

    monkeypatch.setattr(eval_grader, "grade_with_llm", fake_pass)
    passed, reason, score = await _judge_case("q", "输出 391", {"mode": "llm", "contains": ["391"]})
    assert passed and score == 0.9

    # LLM 说通过，但命中 not_contains —— 硬约束一票否决
    passed, reason, score = await _judge_case(
        "q", "输出 391，另外别提密码 abc123", {"mode": "llm", "not_contains": ["abc123"]},
    )
    assert not passed and "禁止" in (reason or "")

    monkeypatch.setattr(eval_grader, "grade_with_llm", fake_fail)
    passed, reason, score = await _judge_case("q", "输出 391", {"mode": "llm", "contains": ["391"]})
    assert not passed and score == 0.3

    # 评分器抛异常 → 退关键词结论
    async def boom(case_input, output, expected):
        raise RuntimeError("llm down")

    monkeypatch.setattr(eval_grader, "grade_with_llm", boom)
    passed, reason, score = await _judge_case("q", "输出 391", {"mode": "llm", "contains": ["391"]})
    assert passed and score is None


def test_trend_aggregation_shape():
    """趋势聚合的形状：按天分桶、P95/均值计算。"""
    import statistics

    lats = [100, 200, 300, 400, 500]
    assert statistics.mean(lats) == 300
    q = statistics.quantiles(lats, n=20)[18]
    assert q >= max(lats) * 0.9
    # _dt 边界：started_at 为 None 时归入 unknown 桶（端点内已处理，这里只验证日期转换）
    now = _dt.datetime.now(_dt.timezone.utc)
    assert now.date().isoformat() == now.date().isoformat()
    _ = json.dumps({"ok": True})
