"""会话产物持久化（session_artifacts）+ 启动收尸 回归。

背景：A2UI / 图表通道原来是进程内 dict，发版或崩溃会把还没落库的
界面/图表整轮丢掉。现在走 Redis（不可用时退内存 dict，行为不变）。
本文件在**内存 fallback 模式**下验证 API 语义（测试环境无 Redis），
Redis 路径的 key 结构由线上部署验证。
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import chart_events as ce
from app.services import session_artifacts as sa
from app.services.agent_service import _current_session_id
from app.services.startup_cleanup import mark_interrupted_runs


@pytest.fixture()
def session_ctx():
    """把当前 run 的 session_id 放进上下文（真实路径：push 走持久层）。"""
    token = _current_session_id.set("s-art-1")
    yield "s-art-1"
    _current_session_id.reset(token)
    sa.clear("chart", "s-art-1")
    sa.clear("a2ui", "s-art-1")


def test_chart_append_read_cursor_clear(session_ctx):
    sid = session_ctx
    assert sa.read_all("chart", sid) == []

    assert ce.push_chart({"series": [1]}, title="a")
    assert ce.push_chart({"series": [2]}, title="b")
    all_items = sa.read_all("chart", sid)
    assert [m["chart"]["title"] for m in all_items] == ["a", "b"]

    # 下发游标：第一次取全部，第二次不重复
    events = ce.chart_events(sid)
    assert len(events[0]["data"]["messages"]) == 2
    assert sa.get_emitted("chart", sid) == 2
    assert ce.chart_events(sid) == []

    # 落库后 clear
    ce.clear_accumulated(sid)
    assert sa.read_all("chart", sid) == []
    assert sa.get_emitted("chart", sid) == 0


def test_a2ui_accumulate_persisted_in_fallback(session_ctx):
    import app.services.a2ui as a2ui_mod

    sid = session_ctx
    a2ui_mod.accumulate(sid, [{"type": "createSurface"}, {"type": "updateComponents"}])
    assert len(a2ui_mod.accumulated(sid)) == 2
    a2ui_mod.clear_accumulated(sid)
    assert a2ui_mod.accumulated(sid) == []


def test_empty_inputs_are_noop():
    sa.append("chart", "", [{"x": 1}])  # 无 session_id：安静跳过
    sa.append("chart", "s-x", [])  # 空消息：安静跳过
    assert sa.read_all("chart", "s-x") == []
    assert sa.read_all("unknown-kind", "s-x") == []


def test_redis_failure_falls_back_to_memory(monkeypatch):
    """Redis 写失败时退内存（工具不能因为观测层挂掉而失败）。"""

    class BoomClient:
        def pipeline(self):
            raise ConnectionError("redis down")

    monkeypatch.setattr(sa, "_redis", lambda: BoomClient())
    sa.append("chart", "s-boom", [{"chart": {"title": "x"}}])
    assert sa.read_all("chart", "s-boom") == [{"chart": {"title": "x"}}]
    sa.clear("chart", "s-boom")


@pytest.fixture()
def sqlite_env(monkeypatch):
    """内存 SQLite 替换 create_db_session（与 test_memory_pipeline_extract 同款）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import session as db_session_mod
    from app.db.models import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(db_session_mod, "create_db_session", factory)
    # startup_cleanup 从 app.db.session 导入 create_db_session（函数内 from 导入），
    # 上面 patch 的就是源头模块 ✓
    return factory


@pytest.mark.asyncio
async def test_startup_cleanup_marks_zombie_runs(sqlite_env):
    """重启收尸：running 状态的 eval run / trace 被标为 error。"""
    from app.db.models import AgentRunTraceModel, EvalRunModel
    from app.db.session import create_db_session

    with create_db_session() as db:
        run = EvalRunModel(dataset_id=1, profile_id=1, status="running")
        done = EvalRunModel(dataset_id=1, profile_id=1, status="done", passed=1, total=1)
        trace = AgentRunTraceModel(session_id="s1", status="running")
        db.add_all([run, done, trace])
        db.commit()
        run_id, done_id, trace_id = run.id, done.id, trace.id

    counts = await asyncio.to_thread(mark_interrupted_runs)

    with create_db_session() as db:
        assert db.get(EvalRunModel, run_id).status == "error"
        assert "restart" in (db.get(EvalRunModel, run_id).error or "")
        assert db.get(EvalRunModel, done_id).status == "done"  # 正常终态不动
        assert db.get(AgentRunTraceModel, trace_id).status == "error"
    assert counts["eval_runs"] >= 1 and counts["traces"] >= 1
