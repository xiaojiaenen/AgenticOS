from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re

_logger = logging.getLogger(__name__)
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select

from app.core.timezone import isoformat_app_timezone
from app.db.models import AgentMessageModel, AgentSessionModel
from app.db.session import create_db_session


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _dumps(value: Any) -> str:
    """序列化会话状态。

    ``default=str`` 是必要的兜底，不是偷懒：``session.metadata`` 里可能挂着
    非 JSON 对象 —— wuwei 的 ``ActionLog`` 就是典型（它只在
    ``AgentSession.to_dict()`` 里被包装成 ``{"__type__": "ActionLog", ...}``，
    我们写库时走的是 metadata 原始字典，绕过了那层包装）。

    没有兜底时的症状：第一次新建对话正常（metadata 还没有 action_log），
    第二次发送时 metadata 里已有 ActionLog → ``json.dumps`` 抛
    ``TypeError: Object of type ActionLog is not JSON serializable`` →
    SSE 只吐一个 error 事件 → 前端 AI 回复空白。
    """
    return json.dumps(value, ensure_ascii=False, default=str)


def _action_log_contract():
    """按 wuwei 版本取 action_log 契约（常量 + 收敛函数）。

    ``ACTION_LOG_TYPE`` / ``coerce_action_log`` 是 wuwei **3.3.2** 才引入的。
    内网用 ``/app/data/pylibs`` 热装依赖，实测仍是 3.3.1 —— 直接
    ``from ... import ACTION_LOG_TYPE`` 会在**每次保存会话元数据**时抛
    ImportError（这是每轮对话的热路径），表现为 SSE 只回一个 error、
    AI 回复全空。

    因此这里按可用符号降级：类型标记恒为 ``"ActionLog"``（3.2 起的既有约定，
    两版一致），收敛逻辑在旧版上自解析实现 —— 不调用上游 ``from_dict``，
    因为它内部同样引用 ``ACTION_LOG_TYPE``，符号缺失时会一起炸。
    """
    import wuwei.runtime.action_log as _action_log

    log_type = getattr(_action_log, "ACTION_LOG_TYPE", "ActionLog")
    coerce = getattr(_action_log, "coerce_action_log", None)
    if coerce is not None:
        return log_type, coerce

    def _fallback_coerce(value: Any) -> Any:
        log_cls = _action_log.ActionLog
        if isinstance(value, log_cls):
            return value
        if value is None:
            return log_cls()
        if not isinstance(value, dict):
            raise TypeError(
                f"session.metadata['action_log'] 期望 ActionLog / dict / None，"
                f"实际是 {type(value).__name__}"
            )
        # 历史两种落盘形态都要认：带 __type__ 标记的 {"__type__", "value"}
        # 与裸 {"entries": [...]}。缺 entries 时按空日志处理（旧版本没有
        # 3.3.2 那套「宁可报错也不静默清空」的严格校验，这里保持宽松，
        # 避免历史 checkpoint 直接把会话打挂）。
        payload = value
        if value.get("__type__") == log_type:
            nested = value.get("value")
            payload = nested if isinstance(nested, dict) else {}
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            return log_cls()
        entry_cls = getattr(_action_log, "ActionEntry", None)
        if entry_cls is None:
            return log_cls()
        entries = [
            entry_cls(
                run_id=str(item.get("run_id", "")),
                agent=str(item.get("agent", "")),
                step=int(item.get("step", 0) or 0),
                kind=str(item.get("kind", "")),
                summary=str(item.get("summary", "")),
                digest=str(item.get("digest", "")),
                timestamp=str(item.get("timestamp", "")),
                data=item.get("data") or {},
            )
            for item in raw_entries
            if isinstance(item, dict)
        ]
        return log_cls(entries)

    return log_type, _fallback_coerce


def _session_metadata_for_storage(session) -> dict[str, Any]:
    """把 session.metadata 转成可安全入库的纯 dict。

    **只处理 metadata，不调 ``session.to_dict()``。** 后者会连带序列化
    整个 ``context``（全部历史消息），实测在 200 条消息的会话上单次约
    0.4ms，而这里只需要 metadata 这一个字段 —— 相差 500 倍以上，且随会话
    长度线性增长。持久化发生在每轮对话，属于热路径。

    需要遵守的契约只有一条：``ActionLog`` 必须包成
    ``{"__type__": "ActionLog", "value": ...}``，否则读回时
    ``AgentSession.from_dict()`` 无法还原成对象。这里复刻 wuwei 的那一小段
    逻辑（见 ``wuwei/agent/session.py::to_dict``），其余字段原样透传。
    wuwei 3.3.2 起用 ``coerce_action_log`` + ``ACTION_LOG_TYPE`` 统一了该契约，
    更早的版本按 ``_action_log_contract`` 降级（内网 pylibs 可能停在 3.3.1）。
    """
    from wuwei.runtime.action_log import ACTION_LOG_KEY

    log_type, coerce = _action_log_contract()

    metadata = dict(getattr(session, "metadata", {}) or {})
    if ACTION_LOG_KEY in metadata:
        metadata[ACTION_LOG_KEY] = {
            "__type__": log_type,
            "value": coerce(metadata[ACTION_LOG_KEY]).to_dict(),
        }
    return metadata


def _iso(value: datetime | None) -> str | None:
    return isoformat_app_timezone(value)


def message_signature(payload: Any) -> str:
    """给一条消息算一个稳定指纹，用来判断「这条是不是已经存过了」。

    分两类，因为两者的稳定性来源不同：

    - **tool 结果**：只用 `tool_call_id`。这个 id 由上游 LLM 生成、一次调用
      终身不变，是唯一可靠的锚点。带上正文反而危险 —— 审批重试时框架会把
      工具结果重写（截断、重新格式化），正文一变指纹就失配。
    - **其余消息**：用 role + 工具调用 id + 正文哈希。正文用哈希而不是长度，
      因为等长正文（「你好」/「再见」）必须能区分开，否则两条不同的消息会
      撞成同一指纹。

    刻意不把整个 payload 序列化后哈希：正文里可能有时间戳、绝对路径这类
    每次读取都不同的字段，全量比对会把同一条消息判成不同。

    **必须同时接受消息对象与 dict。** 这个函数有两个调用方，喂的形态不同：

    - ``load_message_signatures`` 从库里读 ``message_json``，是 dict；
    - ``_messages_after`` 拿的是 ``session.context._messages``，是 wuwei 的
      ``BaseMessage`` 实例。

    早期实现只认 dict、其余一律返回 ``"?"``。于是内存侧全是 ``"?"``、
    库里侧是真指纹，**两边永远匹配不上** → ``_messages_after`` 每次判定
    「整段都是新增」→ 每轮对话都把整个消息列表重写一遍。表现就是同一批
    消息在库里成倍重复（10 条写 4 次）。这里统一归一化成 dict 再算。
    """
    data = _as_message_dict(payload)
    if data is None:
        return "?"
    role = data.get("role")
    # tool 结果只认 id：它是这一轮唯一不变的锚点
    if role == "tool":
        return f"tool|{data.get('tool_call_id') or ''}"
    content = data.get("content")
    text = content if isinstance(content, str) else ""
    tool_calls = data.get("tool_calls") or []
    call_ids = ",".join(
        str((tc or {}).get("id") or "") for tc in tool_calls if isinstance(tc, dict)
    )
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16] if text else "-"
    return f"{role}|{call_ids}|{digest}"


def _as_message_dict(payload: Any) -> dict[str, Any] | None:
    """把「消息对象或 dict」统一成 dict；都不像就返回 None。

    ``exclude_none=True`` 与 ``append_messages_batch`` 写库时的序列化保持
    一致，保证内存侧与库侧的指纹来自同一份字段集合。
    """
    if isinstance(payload, dict):
        return payload
    dump = getattr(payload, "model_dump", None)
    if callable(dump):
        try:
            data = dump(exclude_none=True)
        except TypeError:
            data = dump()
        return data if isinstance(data, dict) else None
    # 兜底：兼容没有 model_dump 的轻量消息（dict 子类之外的对象）
    role = getattr(payload, "role", None)
    if role is None:
        return None
    tool_calls = []
    for tc in getattr(payload, "tool_calls", None) or []:
        fn = getattr(tc, "function", None)
        tool_calls.append({
            "id": getattr(tc, "id", None),
            "name": getattr(fn, "name", None) if fn is not None else getattr(tc, "name", None),
        })
    return {
        "role": role,
        "content": getattr(payload, "content", None),
        "tool_call_id": getattr(payload, "tool_call_id", None),
        "tool_calls": tool_calls,
    }


def _first_user_text(message_json: str | None) -> str | None:
    """从 message_json 中取用户消息正文（用于生成会话标题）。"""
    payload = _loads(message_json, None)
    if not isinstance(payload, dict):
        return None
    if payload.get("role") != "user":
        return None
    text = payload.get("text") or payload.get("content") or ""
    if isinstance(text, list):  # 多模态消息：拼接其中的文本片段
        text = " ".join(
            part.get("text", "") for part in text if isinstance(part, dict)
        )
    if not isinstance(text, str):
        return None
    text = text.strip()
    return text or None


def _restore_session_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """把入库的 metadata 还原成运行时形态。

    写库时 ``ActionLog`` 被包成 ``{"__type__": "ActionLog", "value": ...}``
    （见 ``_session_metadata_for_storage``）。本项目的 ``load()`` 是手动构造
    ``AgentSession(metadata=...)``、绕过了 wuwei 的 ``from_dict``，所以这里显式
    还原一次，让会话一加载就拿到对象而不是 dict。

    wuwei 3.3.2 已在 ``get_or_create_log`` / ``from_dict`` 里用
    ``coerce_action_log`` 统一收敛，本函数直接委托同一个入口，避免自写一套
    反序列化逻辑与上游漂移（它同时认带标记与裸 dict 两种历史 checkpoint）。
    3.3.2 之前的版本没有该符号，走 ``_action_log_contract`` 的等价降级实现。
    """
    metadata = dict(raw or {})
    if "action_log" in metadata:
        _log_type, coerce = _action_log_contract()
        metadata["action_log"] = coerce(metadata["action_log"])
    return metadata


class DatabaseAgentStorage:
    """Wuwei storage implementation backed by SQLAlchemy.

    All sync DB operations run via asyncio.to_thread to avoid blocking
    the event loop during long-running SSE stream requests.
    """

    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def save_meta(self, session) -> None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session.session_id)
                if row is None:
                    row = AgentSessionModel(session_id=session.session_id, system_prompt=session.system_prompt)
                    db.add(row)

                metadata = getattr(session, "metadata", {}) or {}
                row.system_prompt = session.system_prompt
                row.user_id = metadata.get("user_id") or row.user_id
                row.agent_profile_id = metadata.get("agent_profile_id") or row.agent_profile_id
                row.max_steps = session.max_steps
                row.parallel_tool_calls = session.parallel_tool_calls
                row.summary = getattr(session, "summary", None)
                row.metadata_json = _dumps(_session_metadata_for_storage(session))
                row.last_usage_json = _dumps(getattr(session, "last_usage", {}) or {})
                row.last_latency_ms = getattr(session, "last_latency_ms", 0) or 0
                row.last_llm_calls = getattr(session, "last_llm_calls", 0) or 0
                db.commit()
        await asyncio.to_thread(_run)

    async def load(self, session_id: str):
        from wuwei.agent.session import AgentSession
        from wuwei.llm import Message

        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None

                metadata = _restore_session_metadata(_loads(row.metadata_json, {}))

                session = AgentSession(
                    session_id=row.session_id,
                    system_prompt=row.system_prompt,
                    max_steps=row.max_steps,
                    parallel_tool_calls=row.parallel_tool_calls,
                    summary=row.summary,
                    metadata=metadata,
                )
                if row.user_id is not None:
                    session.metadata["user_id"] = row.user_id
                if row.agent_profile_id is not None:
                    session.metadata["agent_profile_id"] = row.agent_profile_id
                session.last_usage = _loads(row.last_usage_json, {})
                session.last_latency_ms = row.last_latency_ms
                session.last_llm_calls = row.last_llm_calls

                messages = db.scalars(
                    select(AgentMessageModel)
                    .where(AgentMessageModel.session_id == session_id)
                    .order_by(AgentMessageModel.id.asc())
                ).all()
                for message in messages:
                    # wuwei 2.1 的 BaseMessage 严格验证 tool_calls 不能为 null，
                    # 但旧数据或 LLM 返回可能存储了 "tool_calls": null，清理后再反序列化。
                    raw = message.message_json
                    if '"tool_calls": null' in raw:
                        raw = raw.replace('"tool_calls": null', '"tool_calls": []')
                    if '"reasoning_content": null' in raw:
                        raw = raw.replace('"reasoning_content": null', '"reasoning_content": ""')
                    try:
                        session.context._messages.append(Message.model_validate_json(raw))
                    except Exception as e:
                        _logger.debug("Skipping unparseable message in session %s: %s", session_id, e)
                        continue

                return session
        return await asyncio.to_thread(_run)

    async def delete(self, session_id: str) -> None:
        def _run():
            with self.session_factory() as db:
                db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id == session_id))
                row = db.get(AgentSessionModel, session_id)
                if row is not None:
                    db.delete(row)
                db.commit()
        await asyncio.to_thread(_run)

    async def describe(self, session_id: str) -> dict[str, Any] | None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None

                message_count = db.scalar(
                    select(func.count(AgentMessageModel.id)).where(AgentMessageModel.session_id == session_id)
                ) or 0
                return {
                    "session_id": row.session_id,
                    "user_id": row.user_id,
                    "agent_profile_id": row.agent_profile_id,
                    "summary": row.summary,
                    "metadata": _loads(row.metadata_json, {}),
                    "last_usage": _loads(row.last_usage_json, {}),
                    "last_latency_ms": row.last_latency_ms,
                    "last_llm_calls": row.last_llm_calls,
                    "message_count": message_count,
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                    "storage": "sqlalchemy",
                }
        return await asyncio.to_thread(_run)

    async def get_owner_id(self, session_id: str) -> int | None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None
                return row.user_id
        return await asyncio.to_thread(_run)

    async def list_user_sessions(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        def _run():
            with self.session_factory() as db:
                rows = db.scalars(
                    select(AgentSessionModel)
                    .where(AgentSessionModel.user_id == user_id)
                    .order_by(AgentSessionModel.updated_at.desc())
                    .limit(limit)
                ).all()

                session_ids = [row.session_id for row in rows]
                if not session_ids:
                    return []

                message_counts = dict(
                    db.execute(
                        select(
                            AgentMessageModel.session_id,
                            func.count(AgentMessageModel.id),
                        )
                        .where(AgentMessageModel.session_id.in_(session_ids))
                        .group_by(AgentMessageModel.session_id)
                    ).all()
                )

                # 会话展示标题：优先 metadata.title（建会话时的用户输入），
                # 其次 summary（wuwei 上下文压缩摘要，正常为空），
                # 最后兜底首条用户消息摘录。summary 不能直接当标题用，
                # 否则前端只能回退成智能体名（如"通用助手"）。
                titles: dict[str, str] = {}
                pending: list[str] = []
                for row in rows:
                    metadata = _loads(row.metadata_json, {}) or {}
                    meta_title = metadata.get("title") if isinstance(metadata, dict) else None
                    if isinstance(meta_title, str) and meta_title.strip():
                        titles[row.session_id] = meta_title.strip()[:40]
                    elif row.summary:
                        titles[row.session_id] = row.summary
                    else:
                        pending.append(row.session_id)
                if pending:
                    first_messages = db.execute(
                        select(
                            AgentMessageModel.session_id,
                            AgentMessageModel.message_json,
                        )
                        .where(AgentMessageModel.session_id.in_(pending))
                        .order_by(
                            AgentMessageModel.created_at.asc(),
                            AgentMessageModel.id.asc(),
                        )
                        .limit(2000)
                    ).all()
                    for sid, payload in first_messages:
                        if sid in titles:
                            continue
                        text = _first_user_text(payload)
                        if text:
                            titles[sid] = text[:40]

                sessions = []
                for row in rows:
                    sessions.append({
                        "session_id": row.session_id,
                        "summary": row.summary,
                        "title": titles.get(row.session_id),
                        "metadata": _loads(row.metadata_json, {}),
                        "message_count": message_counts.get(row.session_id, 0),
                        "created_at": _iso(row.created_at),
                        "updated_at": _iso(row.updated_at),
                    })
                return sessions
        return await asyncio.to_thread(_run)

    async def append_messages_batch(self, session_id: str, messages: list) -> int:
        """Batch insert messages in a single DB transaction. Returns count inserted."""
        def _run():
            import time
            for attempt in range(3):
                try:
                    with self.session_factory() as db:
                        for msg in messages:
                            db.add(
                                AgentMessageModel(
                                    session_id=session_id,
                                    message_json=msg.model_dump_json(exclude_none=True),
                                )
                            )
                        db.commit()
                    return len(messages)
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise
        return await asyncio.to_thread(_run)

    async def get_message_count(self, session_id: str) -> int:
        """Return the number of messages in a session."""
        def _run():
            with self.session_factory() as db:
                return db.scalar(
                    select(func.count(AgentMessageModel.id)).where(
                        AgentMessageModel.session_id == session_id
                    )
                ) or 0
        return await asyncio.to_thread(_run)

    async def load_message_timestamps(self, session_id: str) -> list[str | None]:
        """按落库顺序返回每条消息的时间（ISO 字符串），供前端显示。

        为什么要单独一个方法：``load()`` 把行反序列化成 wuwei 的 Message
        对象，而 Message 上没有 created_at —— 时间只在 DB 行上。前端历史
        消息的时间戳此前靠 ``parseInt(message.id)`` 从流式 id 里抠，历史
        消息 id 是 ``backend-0`` 这种，抠出来是 NaN，于是时间整块消失。

        顺序必须与 ``load()`` 一致（``id.asc()``），调用方按下标配对。
        """
        def _run():
            with self.session_factory() as db:
                rows = db.execute(
                    select(AgentMessageModel.created_at)
                    .where(AgentMessageModel.session_id == session_id)
                    .order_by(AgentMessageModel.id.asc())
                ).all()
            return [isoformat_app_timezone(row[0]) for row in rows]
        return await asyncio.to_thread(_run)

    async def load_message_signatures(self, session_id: str) -> list[str]:
        """按顺序返回已落库消息的指纹，供调用方对齐内存与 DB 的分界点。

        指纹刻意只用「role + 工具调用 id + 正文长度」三样：既能区分
        assistant/tool 的不同轮次，又不会因为 JSON 序列化字段顺序或
        无关字段（如 reasoning）的增删而误判成不同消息。
        """
        def _run():
            with self.session_factory() as db:
                rows = db.execute(
                    select(AgentMessageModel.message_json)
                    .where(AgentMessageModel.session_id == session_id)
                    .order_by(AgentMessageModel.created_at.asc(), AgentMessageModel.id.asc())
                ).all()
            return [message_signature(_loads(row[0], {})) for row in rows]
        return await asyncio.to_thread(_run)

    async def assign_owner(self, session_id: str, user_id: int) -> None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is not None and row.user_id is None:
                    row.user_id = user_id
                    metadata = _loads(row.metadata_json, {})
                    metadata["user_id"] = user_id
                    row.metadata_json = _dumps(metadata)
                    db.commit()
        await asyncio.to_thread(_run)

    async def assign_agent_profile(self, session_id: str, agent_profile_id: int | None) -> None:
        if agent_profile_id is None:
            return

        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is not None and row.agent_profile_id is None:
                    row.agent_profile_id = agent_profile_id
                    metadata = _loads(row.metadata_json, {})
                    metadata["agent_profile_id"] = agent_profile_id
                    row.metadata_json = _dumps(metadata)
                    db.commit()
        await asyncio.to_thread(_run)

    async def save_session_meta(
        self,
        session,
        *,
        user_id: int | None,
        agent_profile_id: int | None,
    ) -> None:
        """单事务完成 owner 绑定 + agent profile 绑定 + 元数据持久化。

        等价于原先三段独立事务的组合（TECH-DEBT-2026-09 顺手修复）：
            assign_owner(session_id, user_id)
            → assign_agent_profile(session_id, agent_profile_id)
            → save_meta(session)
        终态语义保持一致：owner/profile 仅在行上未绑定时写入兜底值，
        随后 session metadata 中的值照常覆盖（与 save_meta 原逻辑相同）。
        """
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session.session_id)
                if row is None:
                    row = AgentSessionModel(session_id=session.session_id, system_prompt=session.system_prompt)
                    db.add(row)

                metadata = getattr(session, "metadata", {}) or {}
                # 1) assign_owner 语义：仅当未绑定 owner 时写入
                if row.user_id is None and user_id is not None:
                    row.user_id = user_id
                # 2) assign_agent_profile 语义：仅当未绑定时写入
                if agent_profile_id is not None and row.agent_profile_id is None:
                    row.agent_profile_id = agent_profile_id
                # 3) save_meta 语义：session metadata 覆盖（或回退到行上已绑定值）
                row.system_prompt = session.system_prompt
                row.user_id = metadata.get("user_id") or row.user_id
                row.agent_profile_id = metadata.get("agent_profile_id") or row.agent_profile_id
                row.max_steps = session.max_steps
                row.parallel_tool_calls = session.parallel_tool_calls
                row.summary = getattr(session, "summary", None)
                row.metadata_json = _dumps(_session_metadata_for_storage(session))
                row.last_usage_json = _dumps(getattr(session, "last_usage", {}) or {})
                row.last_latency_ms = getattr(session, "last_latency_ms", 0) or 0
                row.last_llm_calls = getattr(session, "last_llm_calls", 0) or 0
                db.commit()
        await asyncio.to_thread(_run)


def dump_json(value: Any) -> str:
    return _dumps(value)


def load_json(value: str | None, default: Any) -> Any:
    return _loads(value, default)


def parse_approval_sub_tools(json_str: str | None) -> list[str]:
    """Parse a JSON array of sub-tool names from a string, returning [] on failure."""
    if not json_str:
        return []
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def slugify(value: str, *, fallback: str = "agent") -> str:
    """Convert a string to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower().replace("_", "-"))
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or fallback
