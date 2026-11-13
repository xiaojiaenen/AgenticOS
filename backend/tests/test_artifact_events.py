"""产物事件通道测试。

背景（用户报的三个症状同一个根因）：``artifact_ready`` 只是 SSE 事件，
从不落库 —— 刷新会话后前端拿不到 artifactId，于是 PPT 导出静默失败、
主题切换无效、侧栏打开是裸 iframe。本模块负责把产物累积起来供落库挂
metadata，与 chart_events 是同一套模式。
"""
from __future__ import annotations

import pytest

from app.services import artifact_events


@pytest.fixture(autouse=True)
def _clean():
    """每个用例前后清干净（session_artifacts 的进程内 fallback 是全局的）。"""
    artifact_events.clear_accumulated("s-test")
    yield
    artifact_events.clear_accumulated("s-test")


class TestRecordAndAccumulate:
    def test_record_then_accumulate(self):
        artifact_events.record(
            "ppt",
            {"artifact_id": "a1", "title": "季度汇报", "slide_count": 8, "session_id": "s-test"},
            "s-test",
        )
        acc = artifact_events.accumulated("s-test")
        assert "ppt" in acc
        assert acc["ppt"]["artifact_id"] == "a1"
        assert acc["ppt"]["slide_count"] == 8

    def test_latest_wins_for_same_kind(self):
        """同一 kind 记两次 → 后写覆盖（一轮里重建产物时用最新的）。"""
        artifact_events.record("ppt", {"artifact_id": "old"}, "s-test")
        artifact_events.record("ppt", {"artifact_id": "new"}, "s-test")
        acc = artifact_events.accumulated("s-test")
        assert list(acc.keys()) == ["ppt"]
        assert acc["ppt"]["artifact_id"] == "new"

    def test_multiple_kinds_coexist(self):
        artifact_events.record("ppt", {"artifact_id": "p1"}, "s-test")
        artifact_events.record("document", {"artifact_id": "d1"}, "s-test")
        acc = artifact_events.accumulated("s-test")
        assert acc["ppt"]["artifact_id"] == "p1"
        assert acc["document"]["artifact_id"] == "d1"

    def test_website_uses_project_slug_as_identity(self):
        """网站产物可能只有 project_slug（无 artifact_id），也必须记下来。"""
        artifact_events.record(
            "website",
            {"project_slug": "my-site", "title": "官网", "stack": "vue"},
            "s-test",
        )
        acc = artifact_events.accumulated("s-test")
        assert acc["website"]["project_slug"] == "my-site"


class TestSkipAndClear:
    def test_skip_without_identity(self):
        """没有 artifact_id / project_slug 的产物不记（回源不到，记了没用）。"""
        artifact_events.record("ppt", {"title": "空壳"}, "s-test")
        assert artifact_events.accumulated("s-test") == {}

    def test_skip_unknown_kind(self):
        artifact_events.record("unknown-kind", {"artifact_id": "x"}, "s-test")
        assert artifact_events.accumulated("s-test") == {}

    def test_skip_without_session(self):
        artifact_events.record("ppt", {"artifact_id": "a1"}, "")
        assert artifact_events.accumulated("") == {}

    def test_clear_after_persist(self):
        artifact_events.record("ppt", {"artifact_id": "a1"}, "s-test")
        artifact_events.clear_accumulated("s-test")
        assert artifact_events.accumulated("s-test") == {}

    def test_reset_session_is_clear(self):
        """run 入口调 reset_session，避免上一轮产物串到本轮。"""
        artifact_events.record("ppt", {"artifact_id": "prev-round"}, "s-test")
        artifact_events.reset_session("s-test")
        assert artifact_events.accumulated("s-test") == {}

    def test_sessions_are_isolated(self):
        artifact_events.clear_accumulated("s-other")
        artifact_events.record("ppt", {"artifact_id": "a1"}, "s-test")
        artifact_events.record("ppt", {"artifact_id": "b1"}, "s-other")
        assert artifact_events.accumulated("s-test")["ppt"]["artifact_id"] == "a1"
        assert artifact_events.accumulated("s-other")["ppt"]["artifact_id"] == "b1"
        artifact_events.clear_accumulated("s-other")
