"""刷新后气泡时间消失的回归。

真实故障（用户报）：刷新页面后，气泡下方的时间不见了。

链路：时间只存在于 DB 行（``agent_messages.created_at``），wuwei 的
``Message`` 对象没有这个字段。端点原先靠「与 ``load_message_timestamps``
的结果**按下标配对**」来补 —— 但 ``load()`` 在反序列化失败时会
``continue`` 跳过该行，上下文里还可能多出 system / 压缩摘要消息，
一旦条数不一致，下标就整体偏移：

* 前面几条拿到的是别人的时间（错位）；
* 末尾几条超出范围 → ``index < len(...)`` 为假 → **该字段不出现**，
  前端 ``createdAt`` 为 undefined，``parseInt("backend-0")`` 得 NaN，
  时间整块消失。

修法：``load()`` 反序列化时把时间逐条塞进消息 ``metadata.created_at``
（一行 DB 对应一条消息，天然不会错位），端点优先读它、下标作兜底。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest


class TestTimestampAttachedToMessage:
    def test_created_at_lands_in_message_metadata(self, db_session):
        """落库的时间必须挂到对应消息的 metadata 上。"""
        from app.db.models import AgentMessageModel
        from app.services.session_storage import DatabaseAgentStorage
        from wuwei.llm import Message

        sid = "ts-test-session"
        payload = Message.model_validate({'role': 'user', 'content': '你好'}).model_dump_json()
        _ensure_session(db_session, sid)
        db_session.add(AgentMessageModel(session_id=sid, message_json=payload))
        db_session.commit()

        storage = DatabaseAgentStorage(session_factory=lambda: _ctx_session(db_session))

        import asyncio

        session = asyncio.run(storage.load(sid))
        assert session is not None
        msgs = session.context._messages
        # AgentSession 会自动插一条 system 提示词，所以不假设总条数
        user_msgs = [m for m in msgs if getattr(m, "role", None) == "user"]
        assert len(user_msgs) == 1
        meta = getattr(user_msgs[0], "metadata", None) or {}
        assert meta.get("created_at"), "时间没有挂到消息 metadata 上"
        # 必须是 ISO 字符串，前端 new Date(...) 能解析
        assert "T" in meta["created_at"] or "-" in meta["created_at"]

    def test_timestamps_survive_a_skipped_row(self, db_session):
        """中间有无法反序列化的行时，后面的消息时间仍然正确（不错位）。"""
        from app.db.models import AgentMessageModel
        from app.services.session_storage import DatabaseAgentStorage
        from wuwei.llm import Message

        sid = "ts-skip-session"
        _ensure_session(db_session, sid)
        good1 = Message.model_validate({'role': 'user', 'content': '第一条'}).model_dump_json()
        bad = "{not valid json"
        good2 = Message.model_validate({'role': 'user', 'content': '第三条'}).model_dump_json()
        for payload in (good1, bad, good2):
            db_session.add(AgentMessageModel(session_id=sid, message_json=payload))
        db_session.commit()

        # 给三条不同的时间，验证第二条坏行不影响后一条
        from sqlalchemy import select, asc, update

        rows = db_session.scalars(
            select(AgentMessageModel)
            .where(AgentMessageModel.session_id == sid)
            .order_by(asc(AgentMessageModel.id))
        ).all()
        assert len(rows) == 3
        stamps = [
            datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=8))),
            datetime(2026, 1, 1, 11, 0, tzinfo=timezone(timedelta(hours=8))),
            datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=8))),
        ]
        for row, stamp in zip(rows, stamps):
            db_session.execute(
                update(AgentMessageModel)
                .where(AgentMessageModel.id == row.id)
                .values(created_at=stamp)
            )
        db_session.commit()

        storage = DatabaseAgentStorage(session_factory=lambda: _ctx_session(db_session))
        import asyncio

        session = asyncio.run(storage.load(sid))
        msgs = session.context._messages

        # 注意：AgentSession 初始化时会自己插一条 system 提示词，所以
        # 上下文条数 ≠ DB 行数 —— 这正是「下标配对」不可靠的又一来源。
        # 断言只看「挂上时间的那两条 user 消息」，不假设总条数。
        user_msgs = [m for m in msgs if getattr(m, "role", None) == "user"]
        assert len(user_msgs) == 2, "坏行应被跳过，只剩两条 user"

        t_first = (getattr(user_msgs[0], "metadata", None) or {}).get("created_at")
        t_second = (getattr(user_msgs[1], "metadata", None) or {}).get("created_at")
        assert t_first and t_second
        # 关键：第二条拿到的是**它自己**的时间（12:00）。
        # 下标配对会因「坏行被跳过 + system 消息插队」而错位成 11:00。
        assert "10:00" in t_first, f"第一条时间错位: {t_first}"
        assert "12:00" in t_second, f"第二条时间错位: {t_second}"

    def test_context_has_extra_system_message(self, db_session):
        """记录一个事实：上下文里的消息数会多于 DB 行数（system 提示词插队）。

        这就是为什么「按下标配对时间戳」必然在某些会话上错位 —— 端点必须
        优先读消息自带的 metadata.created_at。
        """
        from app.db.models import AgentMessageModel
        from app.services.session_storage import DatabaseAgentStorage
        from wuwei.llm import Message
        import asyncio

        sid = "ts-system-session"
        _ensure_session(db_session, sid)
        db_session.add(
            AgentMessageModel(
                session_id=sid,
                message_json=Message.model_validate({'role': 'user', 'content': 'hi'}).model_dump_json(),
            )
        )
        db_session.commit()

        session = asyncio.run(
            DatabaseAgentStorage(session_factory=lambda: _ctx_session(db_session)).load(sid)
        )
        db_count = 1
        ctx_count = len(session.context._messages)
        assert ctx_count > db_count, "预期上下文多出 system 消息（下标配对的错位来源）"
        assert any(getattr(m, "role", None) == "system" for m in session.context._messages)


def _ensure_session(db_session, session_id: str) -> None:
    """load() 先查会话表，缺失会直接返回 None —— 测试里补一行最小会话。"""
    from app.db.models import AgentSessionModel

    if db_session.get(AgentSessionModel, session_id) is None:
        db_session.add(
            AgentSessionModel(
                session_id=session_id,
                system_prompt="test",
                max_steps=10,
                parallel_tool_calls=False,
                metadata_json="{}",
                last_usage_json="{}",
            )
        )
        db_session.commit()


def _ctx_session(db_session):
    """把已有 Session 包成上下文管理器（storage 内部用 with session_factory()）。"""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        yield db_session

    return _cm()


@pytest.fixture
def db_session(tmp_path):
    """独立文件库：storage.load() 跑在 to_thread 里，内存库跨线程不可用。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    db_file = tmp_path / "ts.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
