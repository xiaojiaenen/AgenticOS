"""图表独立通道测试（修正版：不再借 A2UI）。"""
from __future__ import annotations

import json
import pathlib

from app.services.chart_events import (
    CHART_PROTOCOL_VERSION,
    chart_events,
    drain_pending,
    push_chart,
    reset_pending,
)


def test_push_and_drain_roundtrip() -> None:
    reset_pending()
    assert push_chart({"xAxis": {"data": ["a"]}, "series": [{"data": [1]}]}, "图1")
    msgs = drain_pending()
    assert len(msgs) == 1
    assert msgs[0]["version"] == CHART_PROTOCOL_VERSION
    assert msgs[0]["chart"]["title"] == "图1"
    assert msgs[0]["chart"]["option"]["series"][0]["data"] == [1]


def test_drain_clears_buffer() -> None:
    reset_pending()
    push_chart({"series": []}, "t")
    drain_pending()
    assert drain_pending() == [], "取走后应为空，避免重复下发"


def test_chart_events_shape() -> None:
    reset_pending()
    push_chart({"series": [{"data": [1, 2]}]}, "柱状图")
    evs = chart_events("sess-1")
    assert len(evs) == 1
    assert evs[0]["event"] == "chart"
    assert evs[0]["data"]["session_id"] == "sess-1"
    assert len(evs[0]["data"]["messages"]) == 1


def test_chart_channel_is_independent_from_a2ui() -> None:
    """图表通道不能污染 A2UI 采集器 —— 混进去会被 zod 拒绝。"""
    from app.services.a2ui import drain_pending as a2ui_drain, reset_pending as a2ui_reset

    a2ui_reset()
    reset_pending()
    push_chart({"series": []}, "t")

    assert a2ui_drain() == [], "图表不该出现在 A2UI 队列"
    assert len(drain_pending()) == 1, "图表应留在自己的队列"


def test_render_chart_uses_chart_channel() -> None:
    """render_chart 必须走独立通道，不能 import a2ui 的 _emit。"""
    from app.tools import chart_render_tools as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "from app.services.chart_events import push_chart" in src
    assert "from app.services.a2ui import _emit" not in src, (
        "图表不该借 A2UI 的事件通道"
    )


def test_render_chart_no_hardcoded_business_names() -> None:
    """工具示例里不能出现可被模型复用的具体名称（ORION 幻觉的根因）。"""
    from app.tools import chart_render_tools as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("销售", "技术", "ORION"):
        assert banned not in src, f"示例里不该出现：{banned}"
    assert "仅示范结构" in src
