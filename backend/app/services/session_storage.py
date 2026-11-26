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


def _message_from_row(row, Message) -> Any | None:
    """从 agent_messages 行重建 Message：结构化列优先，JSON 回退。

    阶段一双写灰度：新行结构化列齐全直接用；迁移未覆盖/老行
    role 为空时回退解析 message_json，并顺手清理 legacy null 字段。
    """
    from app.services.agent.native.types import ToolCall as NativeToolCall
    from app.services.agent.native.types import FunctionCall

    raw_json = row.message_json
    if not getattr(row, "role", None):
        if not raw_json:
            return None
        raw = raw_json
        if '"tool_calls": null' in raw:
            raw = raw.replace('"tool_calls": null', '"tool_calls": []')
        if '"reasoning_content": null' in raw:
            raw = raw.replace('"reasoning_content": null', '"reasoning_content": ""')
        try:
            return Message.model_validate_json(raw)
        except Exception:
            return None

    # 结构化列重建
    tool_calls = []
    for tc in _loads(getattr(row, "tool_calls_json", None), []) or []:
        try:
            fn = tc.get("function") or {}
            tool_calls.append(NativeToolCall(
                id=str(tc.get("id") or ""),
                type="function",
                function=FunctionCall(
                    name=str(fn.get("name") or tc.get("name") or ""),
                    arguments=fn.get("arguments") if isinstance(fn.get("arguments"), dict) else {},
                ),
            ))
        except Exception:  # noqa: BLE001 - 单条坏工具调用不影响整条消息
            continue
    payload = {
        "id": row.message_id or str(row.id),
        "role": row.role,
        "content": row.content_text or "",
        "content_parts": _loads(getattr(row, "content_parts_json", None), []) or [],
        "reasoning_content": getattr(row, "reasoning_text", None) or "",
        "tool_calls": tool_calls,
        "tool_call_id": getattr(row, "tool_call_id", None),
        "name": getattr(row, "name", None),
        "metadata": _loads(getattr(row, "metadata_json", None), {}) or {},
    }
    # status 列是结构化列的默认 "success"：老数据/非工具消息没有显式失败态，
    # 一律当作默认值。只有显式 "error" 才覆盖 metadata.tool_outcome —— 否则
    # 默认 "success" 会把写入端已记下的失败态抹掉（刷新后失败工具"变绿"）。
    # 写入端（engine.py _sync_context）现在会把 outcome 同时写进 status 列和
    # metadata.tool_outcome，这里只需要在 error 时同步，保证两个来源一致。
    row_status = getattr(row, "status", None)
    if row_status and row_status != "success":
        payload["metadata"]["tool_outcome"] = {"status": row_status}
    try:
        return Message.model_validate(payload)
    except Exception:
        # 结构化解析失败再回退 JSON（双写灰度安全网）
        if raw_json:
            try:
                return Message.model_validate_json(raw_json)
            except Exception:
                pass
        return None


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
    import app.services.agent.native.action_log as _action_log

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


def _mark_external_source(stored: dict[str, Any]) -> None:
    """给来自对外 API Key 网关的会话打上 ``source`` 标记（原地修改）。

    为什么需要区分：外部客户端用 API Key 调 `/v1/*` 时，会话仍然记在
    API Key 所属用户名下（归属正确 —— 用量与额度算他的）。但**网页对话页
    不该显示这些记录**：那是程序化调用，用户并没有在页面上跟 AI 聊过，
    混进会话列表只会让人困惑"我什么时候问过这个"。

    标记只写一次（已有 source 就不再覆盖，避免老会话被后来的网页请求改写）。
    判断依据是 contextvar，只有网关入口会置位（见 gateway_v1 / gateway_multi）。
    """
    if stored.get("source"):
        return
    try:
        from app.core.data_path import is_external_api_call

        if is_external_api_call():
            stored["source"] = "external_api"
    except Exception:  # noqa: BLE001 —— 标记失败绝不能影响保存
        pass


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
    from app.services.agent.native.action_log import ACTION_LOG_KEY

    log_type, coerce = _action_log_contract()

    metadata = dict(getattr(session, "metadata", {}) or {})
    if ACTION_LOG_KEY in metadata:
        log_dict = coerce(metadata[ACTION_LOG_KEY]).to_dict()
        metadata[ACTION_LOG_KEY] = {
            "__type__": log_type,
            "value": _slim_action_log(log_dict),
        }
    return metadata


# action_log 保留的条目上限。超过就只留最近的 —— 它是「最近发生了什么」的
# 审计线索，不是完整回放日志，早期条目对排查价值有限。
_ACTION_LOG_MAX_ENTRIES = 60
# 单条 summary 的字符上限。上游写 llm 条目时已经截到 200，但 tool 条目的
# summary 是「工具名 -> 完整返回结果」，可能几 KB。
_ACTION_LOG_SUMMARY_LIMIT = 600


def _slim_action_log(log_dict: dict[str, Any]) -> dict[str, Any]:
    """写库前给 action_log 瘦身。

    为什么必须做：上游 ``agent_runner.py:607`` 每步都往 action_log 追加一条，
    其中 ``data`` 存的是**完整的 tool_calls 参数**：

        data={"tool_calls": [tc.model_dump(mode="json") for tc in pending]}

    模型写一个文件，整份 CSS/JS/HTML 内容都被原样存进去。实测一个 31 条的
    会话，action_log 占 54 KB —— 而同期 session.metadata 的其余全部字段
    加起来只有 2.4 KB。会话越长涨得越多，且**永不裁剪**，最终把
    MySQL 的 TEXT 列（64KB）撑爆，连带整轮消息落库失败。

    关键事实：**这份数据没有任何读取方**。上游只写不读（`get_or_create_log`
    只用于 append），本项目也从不读 entries。它是纯负担。

    所以这里做两件事，都不影响任何现有功能：
    1. 丢掉 ``data.tool_calls``（完整参数）—— 摘要里已经有「哪个工具、做了什么」
    2. summary 截断到 600 字，条目数保留最近 60 条

    保留 ``digest`` / ``timestamp`` / ``kind`` / ``step``，审计需要的字段都在。
    """
    entries = log_dict.get("entries")
    if not isinstance(entries, list):
        return log_dict

    trimmed: list[dict[str, Any]] = []
    for entry in entries[-_ACTION_LOG_MAX_ENTRIES:]:
        if not isinstance(entry, dict):
            continue
        slim = dict(entry)
        summary = slim.get("summary")
        if isinstance(summary, str) and len(summary) > _ACTION_LOG_SUMMARY_LIMIT:
            slim["summary"] = summary[:_ACTION_LOG_SUMMARY_LIMIT] + "…"
        data = slim.get("data")
        if isinstance(data, dict) and "tool_calls" in data:
            # 只留工具名，去掉完整 arguments
            calls = data.get("tool_calls")
            names = [
                ((tc.get("function") or {}).get("name") if isinstance(tc, dict) else None)
                for tc in (calls if isinstance(calls, list) else [])
            ]
            slim["data"] = {
                k: v for k, v in data.items() if k != "tool_calls"
            }
            kept = [n for n in names if n]
            if kept:
                slim["data"]["tool_names"] = kept
        trimmed.append(slim)

    return {**log_dict, "entries": trimmed}


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


def _clean_session_title(raw: str) -> str:
    """清洗会话标题：剥掉注入的 prompt catalog，截到 40 字。"""
    text = (raw or "").strip()
    if text:
        try:
            from app.services.agent.prompts import strip_injected_catalog

            text = strip_injected_catalog(text).strip()
        except Exception:  # noqa: BLE001 —— 剥离失败按原样截断
            pass
    return text[:40]


def _first_user_text(message_json: str | None) -> str | None:
    """从 message_json 中取用户消息正文（用于生成会话标题）。

    **必须剥掉注入的 prompt catalog**：库里的 user 消息是注入后形态
    （website/ppt 模式会拼上资源速查文档），不剥的话会话列表标题变成
    「做一个…培训 --- ## ⚠️ 工作流顺序（严格遵守）…」这种半截 skill 文档。
    """
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
    if text:
        try:
            from app.services.agent.prompts import strip_injected_catalog

            text = strip_injected_catalog(text).strip()
        except Exception:  # noqa: BLE001 —— 剥离失败按原样截断
            pass
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
                # 来源标记：对外 API Key 网关产生的会话要能识别出来，前端对话页
                # 不该显示它们（那是外部客户端的调用记录，不是本人在网页上聊的）。
                # 用 contextvar 判断 —— 保存的那一刻才知道是哪个入口发起的。
                stored = _session_metadata_for_storage(session)
                _mark_external_source(stored)
                row.metadata_json = _dumps(stored)
                row.last_usage_json = _dumps(getattr(session, "last_usage", {}) or {})
                row.last_latency_ms = getattr(session, "last_latency_ms", 0) or 0
                row.last_llm_calls = getattr(session, "last_llm_calls", 0) or 0
                db.commit()
        await asyncio.to_thread(_run)

    async def load(self, session_id: str):
        from app.services.agent.native.types import AgentSession
        from app.services.agent.native.types import BaseMessage as Message

        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None

                metadata = _restore_session_metadata(_loads(row.metadata_json, {}))

                # wuwei 3.4.1 起 AgentSession 不再有 summary 字段（dataclass
                # 里删了），直接传参会 TypeError 让整个会话加载失败。
                # 摘要属于本项目自己的会话元数据，改存进 metadata 保留，
                # 前端从 metadata.summary 读取（见 describe / convert 路径）。
                metadata.setdefault("summary", None)
                if row.summary:
                    metadata["summary"] = row.summary

                session = AgentSession(
                    session_id=row.session_id,
                    system_prompt=row.system_prompt,
                    max_steps=row.max_steps,
                    parallel_tool_calls=row.parallel_tool_calls,
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
                    parsed = _message_from_row(message, Message)
                    if parsed is None:
                        _logger.debug("Skipping unparseable message in session %s", session_id)
                        continue
                    # 把落库时间塞进消息 metadata：时间只存在于 DB 行上
                    # （wuwei 的 Message 没有这个字段），而端点原先靠「与
                    # load_message_timestamps 的结果按下标配对」来补 —— 那条
                    # 路一旦有条目被上面的 continue 跳过，或上下文里多出
                    # system / 压缩摘要消息，下标就整体错位，前端拿到的
                    # created_at 要么错位、要么 undefined，表现为**刷新后
                    # 气泡下方的时间消失**。
                    #
                    # 挂在消息本身上就不会错位：一行 DB 对应一条消息，
                    # 无论中间跳过谁、上下文里多出什么。
                    try:
                        ts = isoformat_app_timezone(message.created_at)
                        if ts:
                            meta = dict(getattr(parsed, "metadata", None) or {})
                            meta.setdefault("created_at", ts)
                            parsed.metadata = meta
                    except Exception:  # noqa: BLE001 -- 时间缺失不影响消息本身
                        pass
                    session.context._messages.append(parsed)

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
                        titles[row.session_id] = _clean_session_title(meta_title)
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
                            titles[sid] = _clean_session_title(text)

                sessions = []
                for row in rows:
                    metadata = _loads(row.metadata_json, {})
                    # 对外 API Key 网关产生的会话不进网页对话列表：
                    # 那是外部客户端的程序化调用，用户没在页面上跟 AI 聊过，
                    # 混进来只会让人困惑"我什么时候问过这个"。
                    # 后台「聊天记录」里仍可按 source 标记识别。
                    if isinstance(metadata, dict) and metadata.get("source") == "external_api":
                        continue
                    sessions.append({
                        "session_id": row.session_id,
                        "summary": row.summary,
                        "title": titles.get(row.session_id),
                        "metadata": metadata,
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
                            # 阶段一双写：结构化列（可查询）+ message_json（灰度回退）。
                            # 读路径在结构化列缺失时回退到 JSON，兼容迁移未覆盖的行。
                            def _json_or_none(value):
                                import json as _json
                                return _json.dumps(value, ensure_ascii=False) if value else None

                            db.add(
                                AgentMessageModel(
                                    session_id=session_id,
                                    message_id=msg.id,
                                    role=getattr(msg, "role", None),
                                    content_text=getattr(msg, "content", "") or "",
                                    content_parts_json=_json_or_none(
                                        getattr(msg, "content_parts", None)
                                    ),
                                    tool_calls_json=_json_or_none(
                                        [tc.model_dump() for tc in (getattr(msg, "tool_calls", None) or [])]
                                    ),
                                    tool_call_id=getattr(msg, "tool_call_id", None),
                                    name=getattr(msg, "name", None),
                                    reasoning_text=getattr(msg, "reasoning_content", None) or None,
                                    metadata_json=_json_or_none(getattr(msg, "metadata", None)),
                                    status=getattr(msg, "status", None),
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
                # 来源标记：对外 API Key 网关产生的会话要能识别出来，前端对话页
                # 不该显示它们（那是外部客户端的调用记录，不是本人在网页上聊的）。
                # 用 contextvar 判断 —— 保存的那一刻才知道是哪个入口发起的。
                stored = _session_metadata_for_storage(session)
                _mark_external_source(stored)
                row.metadata_json = _dumps(stored)
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
