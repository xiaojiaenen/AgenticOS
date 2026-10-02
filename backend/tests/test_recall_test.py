"""知识库召回测试逻辑测试（用假检索函数，不依赖真实索引）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.knowledge.recall_test import run_recall_test


def _hit(page_id: int, title: str, score: float):
    return SimpleNamespace(page_id=page_id, title=title, score=score, page_type="concept")


class _FakeSearch:
    """按问题关键词返回预设结果。"""

    def __init__(self, mapping: dict[str, list]) -> None:
        self.mapping = mapping
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        results = self.mapping.get(kwargs["query"], [])
        if kwargs.get("score_threshold"):
            results = [r for r in results if r.score >= kwargs["score_threshold"]]
        return results[: kwargs.get("max_results", 10)]


class TestRecallTest:
    @pytest.mark.anyio
    async def test_reports_hit_rate(self):
        search = _FakeSearch({
            "备份保留多久": [_hit(1, "备份与恢复规范", 0.9), _hit(2, "其他文档", 0.2)],
            "不存在的topic": [],
        })
        report = await run_recall_test(
            1, search, questions=["备份保留多久", "不存在的topic"], top_k=3,
        )
        assert report.total == 2
        assert report.matched == 1
        assert report.hit_rate == 0.5
        assert report.avg_rank == 1.0

    @pytest.mark.anyio
    async def test_expected_title_matching(self):
        search = _FakeSearch({
            "问题": [_hit(1, "无关文档", 0.9), _hit(2, "目标文档", 0.5)],
        })
        report = await run_recall_test(
            1, search, questions=["问题"], top_k=3,
        )
        # 无 expect_titles 时只统计"有无结果"
        assert report.cases[0].matched is True
        assert report.cases[0].rank_of_first_expected == 1

    @pytest.mark.anyio
    async def test_top_k_limits_results(self):
        search = _FakeSearch({
            "q": [_hit(i, f"文档{i}", 1.0 - i / 10) for i in range(10)],
        })
        report = await run_recall_test(1, search, questions=["q"], top_k=3)
        assert len(report.cases[0].hits) == 3
        assert search.calls[0]["max_results"] == 3

    @pytest.mark.anyio
    async def test_threshold_filters_low_scores(self):
        search = _FakeSearch({
            "q": [_hit(1, "高分", 0.8), _hit(2, "低分", 0.1)],
        })
        report = await run_recall_test(
            1, search, questions=["q"], top_k=5, score_threshold=0.5,
        )
        titles = [h["title"] for h in report.cases[0].hits]
        assert titles == ["高分"]

    @pytest.mark.anyio
    async def test_threshold_in_params_recorded(self):
        search = _FakeSearch({"q": [_hit(1, "x", 1.0)]})
        report = await run_recall_test(
            1, search, questions=["q"], top_k=7, score_threshold=0.3,
        )
        assert report.params["top_k"] == 7
        assert report.params["score_threshold"] == 0.3

    @pytest.mark.anyio
    async def test_empty_question_list_gives_empty_report(self):
        search = _FakeSearch({})
        report = await run_recall_test(1, search, questions=[])
        # 空问题集会走探针兜底（探针依赖真实库，无数据 → 空报告）
        assert report.total == 0
        assert report.hit_rate == 0.0

    @pytest.mark.anyio
    async def test_report_to_dict_shape(self):
        search = _FakeSearch({"q": [_hit(1, "t", 0.5)]})
        report = await run_recall_test(1, search, questions=["q"], top_k=2)
        data = report.to_dict()
        assert set(data.keys()) == {
            "total", "matched", "hit_rate", "avg_rank", "cases", "params",
        }
        assert data["cases"][0]["hits"][0]["score"] == 0.5