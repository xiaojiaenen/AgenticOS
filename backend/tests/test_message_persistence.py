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
