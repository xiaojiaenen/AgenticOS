"""图表独立事件通道（累积状态持久化在 Redis，进程重启不丢）。

踩过的坑（两次，都记在这里，别第三次）：

1. 把累积列表挂在 session 上（session._chart_accumulated = []）：
   wuwei 的 AgentSession 是 Pydantic 模型，未知属性会被塞进 metadata 字典，
   取回来就成了 dict，随后 .extend() 报 "'dict' object has no attribute 'append'"。

2. **只靠 contextvar 采集**（这是"图表工具跑完了但前端不显示"的根因）：
   工具是在 agent 的子 task 里执行的，push_chart 里的 `_pending_charts.set(...)`
   只改**子 task 自己那份上下文副本**；orchestrator 在**父上下文**里 drain，
   读到的永远是 None → 事件为空 → 用户看不到图，工具却回报"已展示"。

   对比 A2UI 为什么没这个毛病：orchestrator 在 run 开始调了 reset_pending()，
   在父上下文里种下一个**空 list 对象**；子 task 复制上下文时复制的是同一个
   list 的引用，于是子 task 的 append 对父上下文可见。
   图表通道当初没做这一步，所以采集器在父上下文里始终是 None。

现在的做法：**以 session_id 为键的持久化队列为准**（session_id 从
`_current_session_id` contextvar 读 —— contextvar 的**值**能传播到子 task，
只有**写**不传播）。队列本体在 Redis（AOF + 数据卷持久化，工具 push
时立即写入）—— 之前是进程内 dict，发版/崩溃会整轮丢图，`_emitted`
游标丢失还会导致重启后同一张图重复下发、重复落库。
Redis 不可用时退回进程内 dict（本地开发/单测行为不变）。
contextvar 列表只保留给同上下文调用（单元测试用），
两条路径按 session_id 是否存在互斥，不会重复计数。
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any

logger = logging.getLogger("agenticos.chart")

# 图表消息的协议版本（与前端解析器约定）
CHART_PROTOCOL_VERSION = "v0.9"

# 同上下文采集器（单元测试与"工具和 drain 在同一上下文"的场景）
_pending_charts: contextvars.ContextVar[list[dict[str, Any]] | None] = (
    contextvars.ContextVar("chart_pending", default=None)
)

# 跨上下文队列已迁移到 session_artifacts（Redis 持久化，见模块 docstring）。
# 这两个引用仅作为 Redis 不可用时的进程内 fallback（内存 dict）。
from app.services import session_artifacts  # noqa: E402

_accumulated = session_artifacts._mem_lists["chart"]
_emitted = session_artifacts._mem_emitted["chart"]


def _session_id() -> str:
    """当前 run 的会话 id。取不到就返回空串（走同上下文路径）。"""
    try:
        from app.services.agent_service import _current_session_id

        return _current_session_id.get() or ""
    except Exception:  # noqa: BLE001 -- 取不到不该让工具失败
        return ""


def _collector() -> list[dict[str, Any]]:
    """取当前上下文的采集列表，没有就建一个并绑定。"""
    items = _pending_charts.get()
    if items is None:
        items = []
        _pending_charts.set(items)
    return items


def push_chart(option: dict[str, Any], title: str = "") -> bool:
    """把一张图表塞进本轮采集器。返回是否成功。"""
    message = {
        "version": CHART_PROTOCOL_VERSION,
        "chart": {"title": title, "option": option},
    }
    try:
        session_id = _session_id()
        if session_id:
            # 主路径：进程内按会话累积。子 task 里 push 也能被父上下文读到。
            _accumulated.setdefault(session_id, []).append(message)
        else:
            # 无会话上下文（脚本/测试）：退回同上下文列表
            _collector().append(message)
        return True
    except Exception:  # noqa: BLE001 -- 采集失败不该影响工具返回
        logger.warning("push_chart failed", exc_info=True)
        return False


def drain_pending() -> list[dict[str, Any]]:
    """取走同上下文采集器里的图表（测试/同上下文场景）。"""
    items = _pending_charts.get()
    if not items:
        return []
    _pending_charts.set([])
    return list(items)


def reset_pending() -> None:
    """每轮 run 开始时清空同上下文采集器。

    注意：orchestrator 必须在父上下文里调用一次。否则子 task 的 push
    只写它自己的副本，父上下文 drain 拿到空列表（历史上就是这么丢图的）。
    """
    _pending_charts.set([])


def reset_session(session_id: str) -> None:
    """新一轮 run 开始时清空该会话的累积（避免上一轮的图串到这一轮）。

    contextvar 那份也要清 —— 两者是同一次 push 的两个落点，
    只清一边会让下一轮把上一轮的图重复下发/重复落库。
    """
    reset_pending()
    if session_id:
        session_artifacts.clear("chart", session_id)


def chart_events(session_id: str) -> list[dict[str, Any]]:
    """把尚未下发的图表转成 SSE 事件。

    两个来源合并（互斥，不会重复）：
      - 同上下文采集器（push 时拿不到 session_id 的情况）
      - 按 session_id 的进程内队列（工具在子 task 里执行的情况）
    """
    items = drain_pending()
    buffered = session_artifacts.read_all("chart", session_id)
    start = session_artifacts.get_emitted("chart", session_id)
    if start < len(buffered):
        items.extend(buffered[start:])
        session_artifacts.set_emitted("chart", session_id, len(buffered))
    if not items:
        return []
    return [{
        "event": "chart",
        "data": {"session_id": session_id, "messages": items},
    }]


def accumulated(session_id: str) -> list[dict[str, Any]]:
    """读取该会话累积的全部图表（供落库挂 metadata）。"""
    return session_artifacts.read_all("chart", session_id)


def clear_accumulated(session_id: str) -> None:
    """落库后清空，避免重复写入。"""
    session_artifacts.clear("chart", session_id)
