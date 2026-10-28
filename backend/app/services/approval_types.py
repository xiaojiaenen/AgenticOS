"""审批请求 / 决策的数据契约。

为什么自己定义，而不是从 wuwei 导入：
- wuwei 3.2.1 移除了 ``wuwei.runtime.ApprovalRequest`` / ``ApprovalDecision``
  （审批机制重构为「抛 InterruptSignal + checkpointer 持久化 + resume 恢复」）。
- 但这两个类**本来就没有任何行为** —— 只是两个 ``@dataclass``，而且我们的
  审批流程（Redis pub/sub 跨 worker 通信 + DB 持久化 + SSE 推送）**完全是自己
  实现的**，上游那两个类只被当作「传参容器」用。

所以这里定义等价物，好处有三：
1. 升级 wuwei 时不会因为上游删掉一个数据结构而整站起不来；
2. 语义归属清晰 —— 这是 AgenticOS 的审批契约，不是 wuwei 的；
3. 字段与旧版逐一对齐，存量 Redis 消息 / DB 记录不受影响。

字段与 wuwei 3.0.2 的 ``wuwei/runtime/approval.py`` 逐字对应：
    ApprovalRequest:  id / session_id / action_type / payload / metadata
    ApprovalDecision: status / reason
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApprovalRequest:
    """一次待审批的请求。

    Attributes:
        id: 审批单 id（前端据此回传决策）。
        session_id: 所属会话 id，Redis 频道按它分。
        action_type: 动作类型，如 ``tool_call``。
        payload: 动作细节（工具名、参数等）。
        metadata: 附加信息。
    """

    id: str
    session_id: str
    action_type: str = ""
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ApprovalDecision:
    """审批结果。

    Attributes:
        status: ``approved`` 或 ``rejected``。
        reason: 拒绝原因 / 备注。
    """

    status: str  # "approved" | "rejected"
    reason: str | None = None
