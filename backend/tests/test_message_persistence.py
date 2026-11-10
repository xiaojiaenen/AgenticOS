"""校验消息持久化的对齐逻辑（不依赖真实 LLM/DB）。

背景：审批中断重试后 wuwei 会重写上下文里的 assistant 消息，内存消息列表与
库里的不再是一一对应的前缀关系。原实现按「条数差」切片（messages[existing:]），
错位时会重复落库。重复的 tool 消息会让上游 LLM 永久拒绝该会话后续请求
（DeepSeek: "Messages with role 'tool' must be a response to a preceding
message with 'tool_calls'"），表现为所有后续回复全空。
"""

from app.services.agent.orchestrator import _messages_after
from app.services.session_storage import message_signature


def _sig(role, content="", tool_call_id=None, tool_calls=None):
    payload = {"role": role, "content": content}
    if tool_call_id:
        payload["tool_call_id"] = tool_call_id
    if tool_calls:
        payload["tool_calls"] = [{"id": i} for i in tool_calls]
    return message_signature(payload)


def test_fingerprint_distinguishes_turns():
    assert _sig("user", "你好") != _sig("user", "再见")
    # 同一 role 同一正文，但工具调用 id 不同 → 必须是两条不同消息
    assert _sig("assistant", "", tool_calls=["call_a"]) != _sig("assistant", "", tool_calls=["call_b"])
    # tool 消息靠 tool_call_id 区分
    assert _sig("tool", "2", "call_a") != _sig("tool", "3", "call_b")


def test_fingerprint_ignores_serialization_noise():
    """JSON 字段顺序、无关字段增删不应改变指纹，否则会把同一条判成新消息。"""
    a = {"role": "assistant", "content": "好的", "reasoning": "xxx"}
    b = {"reasoning": "yyy", "content": "好的", "role": "assistant"}
    assert message_signature(a) == message_signature(b)


def test_no_existing_messages_persists_all():
    msgs = [{"role": "user", "content": "hi"}]
    assert len(_messages_after(msgs, [])) == 1


def test_normal_append_only_saves_tail():
    """正常路径：内存 = 库 + 新增一条，只应写入新增那条。"""
    existing = [_sig("user", "问题"), _sig("assistant", "回答")]
    msgs = [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "追问"},
    ]
    pending = _messages_after(msgs, existing)
    assert len(pending) == 1
    assert pending[0]["content"] == "追问"


def test_rewritten_assistant_message_does_not_duplicate_tool_result():
    """核心回归：assistant 消息被重写后，不能把已存过的 tool 结果再写一遍。

    复现真实故障——库里已有 assistant(tool_calls=[X]) + tool(X)，
    重试后内存里 assistant 的正文被填上了（原来是空），指纹不再匹配。
    按条数切片会从错误位置开始，把 tool(X) 重复写出去。
    """
    existing = [
        _sig("system", "sys"),
        _sig("user", "写文档"),
        _sig("assistant", "", tool_calls=["call_X"]),   # 当时正文是空
        _sig("tool", "结果", "call_X"),
    ]
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "写文档"},
        # 重试后同一位置被重写：tool_calls 还在，但正文多了内容
        {"role": "assistant", "content": "我来处理", "tool_calls": [{"id": "call_X"}]},
        {"role": "tool", "content": "结果", "tool_call_id": "call_X"},
        {"role": "assistant", "content": "已完成"},
    ]
    pending = _messages_after(msgs, existing)
    # 关键断言：call_X 的 tool 结果绝不能再次出现
    tool_ids = [m.get("tool_call_id") for m in pending if m.get("role") == "tool"]
    assert "call_X" not in tool_ids
    assert all(m.get("content") != "结果" or m.get("role") != "tool" for m in pending)


def test_memory_shorter_than_db_persists_nothing():
    """内存消息比库里少（上下文被压缩/重置）时不应乱写。"""
    existing = [_sig("user", "a"), _sig("assistant", "b"), _sig("user", "c")]
    msgs = [{"role": "user", "content": "a"}]
    assert _messages_after(msgs, existing) == []


def test_last_matching_point_wins():
    """取最后一个匹配位置：内存开头与库不一致时，尾部稳定点才是分界。"""
    existing = [_sig("user", "老问题"), _sig("assistant", "老回答")]
    msgs = [
        {"role": "system", "content": "新加的 system"},   # 开头对不上
        {"role": "user", "content": "老问题"},            # 重新对上
        {"role": "assistant", "content": "老回答"},
        {"role": "user", "content": "新问题"},
    ]
    pending = _messages_after(msgs, existing)
    assert [m["content"] for m in pending] == ["新问题"]


# ---------------------------------------------------------------------------
# session metadata 序列化：ActionLog 等非 JSON 对象
# ---------------------------------------------------------------------------


def test_dump_json_tolerates_non_json_objects():
    """``dump_json`` 必须有兜底：metadata 里可能挂着任意非 JSON 对象。"""
    from wuwei.runtime.action_log import ActionLog

    from app.services.session_storage import dump_json

    # 不应抛 TypeError
    text = dump_json({"action_log": ActionLog(), "n": 1})
    assert isinstance(text, str)
    assert '"n": 1' in text


def test_session_metadata_uses_upstream_contract_for_action_log():
    """写库必须走 ``session.to_dict()`` 的 ActionLog 包装。

    用户症状：第一次新建对话正常（metadata 还没 action_log），
    第二次发送时 metadata 里已有 ActionLog → json.dumps 抛
    ``Object of type ActionLog is not JSON serializable`` → SSE 只吐 error →
    前端 AI 回复空白。
    """
    from wuwei.agent.session import AgentSession
    from wuwei.runtime.action_log import ACTION_LOG_KEY, ActionLog

    from app.services.session_storage import (
        _session_metadata_for_storage,
        dump_json,
        load_json,
    )

    session = AgentSession(session_id="probe-1", system_prompt="p")
    log = ActionLog()
    log.append(run_id="r1", agent="main", step=1, kind="llm", summary="first call")
    session.metadata[ACTION_LOG_KEY] = log

    stored = _session_metadata_for_storage(session)

    # 走 to_dict 契约时会被包成 {"__type__": "ActionLog", "value": {...}}
    assert isinstance(stored[ACTION_LOG_KEY], dict)
    assert stored[ACTION_LOG_KEY]["__type__"] == "ActionLog"
    assert stored[ACTION_LOG_KEY]["value"]["entries"][0]["summary"] == "first call"

    # 入库不报错，且读回后能还原成 ActionLog 实例
    payload = dump_json(stored)
    assert "ActionLog" in payload

    restored = AgentSession.from_dict(
        {
            "session_id": "probe-1",
            "system_prompt": "p",
            "metadata": load_json(payload, {}),
            "context": {},
        }
    )
    assert isinstance(restored.metadata[ACTION_LOG_KEY], ActionLog)
    assert len(restored.metadata[ACTION_LOG_KEY]) == 1


def test_session_metadata_falls_back_when_to_dict_fails():
    """``to_dict()`` 抛错时退回原始字典，不能让持久化整体失败。"""

    from app.services.session_storage import _session_metadata_for_storage

    class Broken:
        metadata = {"user_id": 7}

        def to_dict(self):
            raise RuntimeError("boom")

    assert _session_metadata_for_storage(Broken()) == {"user_id": 7}


def test_session_metadata_handles_object_without_to_dict():
    from app.services.session_storage import _session_metadata_for_storage

    class Plain:
        metadata = {"user_id": 3, "agent_profile_id": 4}

    assert _session_metadata_for_storage(Plain()) == {"user_id": 3, "agent_profile_id": 4}


def test_restore_session_metadata_rebuilds_action_log():
    """load() 手动构造 AgentSession，绕过了 wuwei 的 from_dict。

    若不显式还原，metadata["action_log"] 会是入库时的 dict，上游
    get_or_create_log() 只处理 None → agent_runner.py 调 .append() 抛
    AttributeError，表现为「工具执行后 agent 崩溃、没有最终回复」。
    """
    from wuwei.runtime.action_log import ActionLog, get_or_create_log

    from app.services.session_storage import _restore_session_metadata

    log = ActionLog()
    log.append(run_id="r1", agent="main", step=1, kind="tool", summary="生图")
    stored = {"action_log": {"__type__": "ActionLog", "value": log.to_dict()}}

    class Session:
        metadata = _restore_session_metadata(stored)

    session = Session()
    assert isinstance(session.metadata["action_log"], ActionLog)
    assert len(session.metadata["action_log"].entries) == 1
    # 后续 append 不再崩溃
    get_or_create_log(session).append(
        run_id="r1", agent="main", step=2, kind="llm", summary="最终回复"
    )
    assert len(session.metadata["action_log"].entries) == 2


def test_restore_session_metadata_handles_untagged_action_log():
    """3.2 前的无标记裸 dict 也要还原（wuwei 3.3.2 coerce_action_log 语义）。

    其它 metadata 字段保持原样，不误改。
    """
    from wuwei.runtime.action_log import ActionLog

    from app.services.session_storage import _restore_session_metadata

    raw = {"user_id": 7, "title": "会话标题", "action_log": {"entries": []}}
    restored = _restore_session_metadata(raw)
    assert isinstance(restored["action_log"], ActionLog)
    assert len(restored["action_log"].entries) == 0
    assert restored["user_id"] == 7
    assert restored["title"] == "会话标题"


def test_action_log_contract_degrades_on_wuwei_before_3_3_2(monkeypatch):
    """wuwei < 3.3.2 没有 ``ACTION_LOG_TYPE`` / ``coerce_action_log``。

    内网用 ``/app/data/pylibs`` 热装依赖，实测停在 3.3.1。原来的实现是
    模块级 ``from wuwei.runtime.action_log import ACTION_LOG_TYPE``，
    在**每次保存会话元数据**时抛 ImportError —— 这是每轮对话的热路径，
    表现为 SSE 只回一个 error 事件、AI 回复全空。

    这里把 3.3.2 才有的符号摘掉，验证写库/读库仍能走等价降级路径。
    """
    import wuwei.runtime.action_log as action_log_module

    from app.services.session_storage import (
        _action_log_contract,
        _restore_session_metadata,
        _session_metadata_for_storage,
    )

    monkeypatch.delattr(action_log_module, "ACTION_LOG_TYPE", raising=False)
    monkeypatch.delattr(action_log_module, "coerce_action_log", raising=False)

    log_type, coerce = _action_log_contract()
    # 类型标记是 3.2 起的既有约定，两个版本一致
    assert log_type == "ActionLog"

    log = action_log_module.ActionLog()
    log.append(run_id="r1", agent="main", step=1, kind="tool", summary="hello")

    class Session:
        metadata = {"action_log": log}

    stored = _session_metadata_for_storage(Session())
    assert stored["action_log"]["__type__"] == "ActionLog"
    assert len(stored["action_log"]["value"]["entries"]) == 1

    # 带标记与裸 dict 两种历史形态都要能还原
    for payload in (
        stored,
        {"action_log": {"entries": [{"summary": "s"}]}},
    ):
        restored = _restore_session_metadata(payload)
        assert isinstance(restored["action_log"], action_log_module.ActionLog)
