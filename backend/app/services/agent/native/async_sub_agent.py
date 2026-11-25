"""异步子代理（自 wuwei/agent/async_sub_agent.py 移植，wuwei 退役 A5-5）。

父代理可把任务委派给后台子代理，不阻塞主对话：
- start_async_task / check_async_task / cancel_async_task / list_async_tasks 四工具
- 子代理用**本引擎**执行（LangGraphAgent + 子代理专属工具集）
- 有界清理：终态句柄超上限按创建顺序淘汰；running 永不清理
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field

logger = logging.getLogger("agenticos.async_sub_agent")

#: 任务句柄上限（超过时淘汰终态句柄）
_MAX_TASKS = 64

MAX_STEPS_LIMIT_MESSAGE = (
    "任务未完成，已达到最大步骤限制（{max_steps} 步）。"
    "如需继续，请提高 max_steps 或把任务拆小。"
)


@dataclass
class AsyncSubAgent:
    """异步子代理配置。"""

    name: str
    description: str
    system_prompt: str = "You are a helpful assistant."
    tools: list | None = None
    max_steps: int = 10
    inherit_context: bool = True
    """是否将父代理的对话历史注入子代理上下文"""


@dataclass
class AsyncTaskHandle:
    """后台任务句柄。"""

    task_id: str
    sub_agent_name: str
    status: str = "pending"  # pending | running | completed | failed | cancelled
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    elapsed_ms: int = 0
    steps: int = 0
    usage: dict = field(default_factory=dict)
    llm_calls: int = 0
    owner_session: str | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)


class AsyncSubAgentManager:
    """管理后台子代理任务；以回调方式执行子代理（引擎注入 run_fn）。"""

    def __init__(self, sub_agents: list[AsyncSubAgent], run_fn) -> None:
        """
        Args:
            sub_agents: 子代理配置列表
            run_fn: 异步执行器 ``(sub_agent, task_text, parent_context) -> dict``
                返回 ``{"result", "status", "usage", "llm_calls", "steps"}``。
                由引擎注入（用本引擎跑子代理），保持单一执行实现。
        """
        self.sub_agents: dict[str, AsyncSubAgent] = {sa.name: sa for sa in sub_agents}
        self._run_fn = run_fn
        self._tasks: dict[str, AsyncTaskHandle] = {}

    # ── 工具 schema（注册进注册表用）────────────────────────────────────

    def tool_schemas(self) -> list[dict]:
        sub_descs = "\n".join(f"- {sa.name}: {sa.description}" for sa in self.sub_agents.values())
        return [
            {
                "type": "function",
                "function": {
                    "name": "start_async_task",
                    "description": (
                        f"Start a background sub-agent task. Available agents:\n{sub_descs}"
                        "\nReturns a task_id for later checking."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_name": {
                                "type": "string",
                                "description": "Name of the sub-agent to use.",
                                "enum": list(self.sub_agents.keys()),
                            },
                            "task": {"type": "string", "description": "Task description"},
                        },
                        "required": ["agent_name", "task"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_async_task",
                    "description": "Check background task status. Completed tasks include the result.",
                    "parameters": {
                        "type": "object",
                        "properties": {"task_id": {"type": "string"}},
                        "required": ["task_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_async_task",
                    "description": "Cancel a running background task.",
                    "parameters": {
                        "type": "object",
                        "properties": {"task_id": {"type": "string"}},
                        "required": ["task_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_async_tasks",
                    "description": "List all background tasks and their statuses.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    # ── 工具实现（供 tools_adapter 调用）────────────────────────────────

    async def handle_tool(self, tool_name: str, args: dict, owner_session: str | None) -> str:
        """分发异步子代理工具调用，返回 JSON 字符串结果。"""
        if tool_name == "start_async_task":
            return await self._start_task(
                args.get("agent_name", ""), args.get("task", ""), owner_session
            )
        if tool_name in {"check_async_task", "cancel_async_task"} and args.get("task_id") in self._tasks and (
            self._tasks[args["task_id"]].owner_session != owner_session
        ):
            return json.dumps({"ok": False, "error": "Task not found in this session"})
        if tool_name == "check_async_task":
            return await self._check_task(args.get("task_id", ""))
        if tool_name == "cancel_async_task":
            return await self._cancel_task(args.get("task_id", ""))
        if tool_name == "list_async_tasks":
            return self._list_tasks(owner_session)
        return json.dumps({"ok": False, "error": f"Unknown tool: {tool_name}"})

    async def _start_task(self, agent_name: str, task: str, owner_session: str | None) -> str:
        sub = self.sub_agents.get(agent_name)
        if not sub:
            return json.dumps({"ok": False, "error": f"Unknown agent: {agent_name}"})
        if not task.strip():
            return json.dumps({"ok": False, "error": "Missing task"})

        task_id = f"async_{uuid.uuid4().hex[:12]}"
        # 有界清理：终态句柄超过上限时按创建顺序淘汰
        if len(self._tasks) >= _MAX_TASKS:
            terminal = [
                key
                for key, h in sorted(self._tasks.items(), key=lambda kv: kv[1].created_at)
                if h.status in ("completed", "failed", "cancelled")
            ]
            for key in terminal[: len(self._tasks) - _MAX_TASKS + 1]:
                self._tasks.pop(key, None)

        handle = AsyncTaskHandle(
            task_id=task_id,
            sub_agent_name=agent_name,
            status="running",
            started_at=time.time(),
            owner_session=owner_session,
        )

        async def _run():
            try:
                payload = await self._run_fn(sub, task)
                handle.result = payload.get("result")
                handle.status = payload.get("status", "unknown")
                handle.usage = payload.get("usage", {})
                handle.llm_calls = payload.get("llm_calls", 0)
                handle.steps = payload.get("steps", 0)
            except asyncio.CancelledError:
                handle.status = "cancelled"
                handle.error = "Task cancelled"
            except Exception as e:  # noqa: BLE001
                handle.status = "failed"
                handle.error = str(e)
            finally:
                handle.completed_at = time.time()
                handle.elapsed_ms = int((handle.completed_at - handle.started_at) * 1000)

        handle._task = asyncio.create_task(_run())
        self._tasks[task_id] = handle

        return json.dumps(
            {
                "ok": True,
                "task_id": task_id,
                "agent_name": agent_name,
                "status": "running",
                "message": f"Task started. Use check_async_task('{task_id}') to get results.",
            },
            ensure_ascii=False,
        )

    async def _check_task(self, task_id: str) -> str:
        handle = self._tasks.get(task_id)
        if not handle:
            return json.dumps({"ok": False, "error": f"Task not found: {task_id}"})
        return json.dumps(
            {
                "ok": handle.status not in {"failed", "error", "cancelled"},
                "task_id": task_id,
                "status": handle.status,
                "result": handle.result,
                "error": handle.error,
                "usage": handle.usage,
                "llm_calls": handle.llm_calls,
                "steps": handle.steps,
                "elapsed_ms": (
                    int((time.time() - handle.started_at) * 1000)
                    if handle.status == "running"
                    else handle.elapsed_ms
                ),
            },
            ensure_ascii=False,
        )

    async def _cancel_task(self, task_id: str) -> str:
        handle = self._tasks.get(task_id)
        if not handle:
            return json.dumps({"ok": False, "error": f"Task not found: {task_id}"})
        if handle.status != "running":
            return json.dumps({"ok": False, "error": f"Task is not running (status: {handle.status})"})
        if handle._task:
            handle._task.cancel()
            with suppress(asyncio.CancelledError):
                await handle._task
        if handle.status != "unknown":
            handle.status = "cancelled"
        return json.dumps({"ok": True, "task_id": task_id, "status": handle.status})

    def _list_tasks(self, owner_session: str | None) -> str:
        tasks = [
            {
                "task_id": h.task_id,
                "agent_name": h.sub_agent_name,
                "status": h.status,
                "elapsed_ms": h.elapsed_ms,
            }
            for h in self._tasks.values()
            if owner_session is None or h.owner_session == owner_session
        ]
        return json.dumps({"ok": True, "tasks": tasks}, ensure_ascii=False)

    @staticmethod
    def summarize_context(messages: list) -> str:
        """父代理上下文的最近消息截断预览（非 LLM 摘要）。"""
        parts = []
        for msg in messages[-6:]:
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "") or ""
            if content and role in ("user", "assistant"):
                parts.append(f"[{role}]: {content[:200]}")
        return "\n".join(parts)
