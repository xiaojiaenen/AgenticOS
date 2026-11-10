"""图表跨上下文采集回归测试。

真实链路：工具在 agent 的**子 task** 里执行 push_chart，orchestrator 在
**父上下文**里 drain。contextvar 的值会复制进子 task，但子 task 里的
`set()` 不会回写父上下文 —— 所以父上下文必须预先种一个空 list，
否则子 task 的 append 写进自己的副本，drain 永远读到空。

这就是「render_chart 工具跑完、模型说已展示、用户却看不到图」的根因。
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import chart_events as ce


@pytest.fixture(autouse=True)
def _clean():
    """清空同上下文采集器 + 本文件用到的会话级队列（Redis/内存都要清）。

    push 侧与读侧统一走 session_artifacts 后，"会话级队列"在 Redis 在线时
    落在 Redis 里（TTL 7 天）—— 只清进程内 dict 挡不住上一次失败运行留下的
    脏数据，必须按会话 id 显式 clear。contextvar 归零交给 conftest 的
    autouse 夹具（before/after 各一次），这里不再重复。
    """
    from app.services import session_artifacts as sa

    sids = ("s1", "sess-child", "sess-dup", "sess-hist")
    ce.reset_pending()
    for sid in sids:
        sa.clear("chart", sid)
    yield
    ce.reset_pending()
    for sid in sids:
        sa.clear("chart", sid)


def test_same_context_push_and_drain() -> None:
    assert ce.push_chart({"series": [{"data": [1, 2]}]}, "柱状图")
    events = ce.chart_events("s1")
    assert len(events) == 1
    assert events[0]["event"] == "chart"
    assert events[0]["data"]["messages"][0]["chart"]["title"] == "柱状图"


def test_push_from_child_task_reaches_parent_drain() -> None:
    """工具在子 task 里 push，父上下文 drain 必须能取到。"""
    from app.services.agent_service import _current_session_id

    _current_session_id.set("sess-child")
    ce.reset_pending()          # orchestrator 在父上下文的准备动作

    async def scenario() -> list[dict]:
        async def tool_task() -> None:
            ce.push_chart({"series": [{"data": [3, 4]}]}, "任务量")

        await asyncio.create_task(tool_task())
        return ce.chart_events("sess-child")

    events = asyncio.run(scenario())
    assert len(events) == 1, "子 task 里的 push 必须能落到父上下文的 drain"
    assert events[0]["data"]["messages"][0]["chart"]["option"]["series"][0]["data"] == [3, 4]
    _current_session_id.set(None)


def test_no_duplicate_event_on_repeated_drain() -> None:
    """同一张图不能被重复下发（每轮 tool_end 都会 drain 一次）。"""
    from app.services.agent_service import _current_session_id

    _current_session_id.set("sess-dup")
    ce.reset_pending()
    ce.push_chart({"series": []}, "图")
    first = ce.chart_events("sess-dup")
    second = ce.chart_events("sess-dup")
    assert len(first) == 1
    assert second == [], "已下发的图表不该再发一次"
    _current_session_id.set(None)


def test_accumulated_keeps_full_history_for_persistence() -> None:
    from app.services.agent_service import _current_session_id

    _current_session_id.set("sess-hist")
    ce.reset_pending()
    ce.push_chart({"series": []}, "A")
    ce.push_chart({"series": []}, "B")
    assert len(ce.chart_events("sess-hist")[0]["data"]["messages"]) == 2
    assert len(ce.accumulated("sess-hist")) == 2, "落库要用全量，不能被 drain 清掉"
    ce.clear_accumulated("sess-hist")
    assert ce.accumulated("sess-hist") == []
    _current_session_id.set(None)
