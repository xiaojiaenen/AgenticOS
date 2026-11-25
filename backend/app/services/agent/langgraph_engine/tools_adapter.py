"""工具注册适配层 + 审批策略移植（迁移方案阶段 1 / 阶段 3 HITL）。

- ``registry_to_langchain_tools``：wuwei ``ToolRegistry`` → LangChain
  ``StructuredTool``，保留 display_name / requires_approval / side_effect /
  is_concurrency_safe 元数据（TOOL_CATALOG 元数据 100% 对齐是阶段 1 验收项）；
- ``EngineApprovalPolicy``：``LenientHitlMiddleware`` 三档审批语义 + 阶段 3
  的 **声明式 ``interrupt_on`` 配置**（形状对齐 DeepAgents
  ``InterruptOnConfig``）与 **四决策语义**（approved / rejected / respond，
  edit 由 approve+改参承担）——复用同一个 ``ApprovalManager`` 的 Redis
  pub/sub / DB 审计 / SSE ``approval_required`` 泵，业务外壳零改动。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime

_logger = logging.getLogger("agenticos.langgraph.tools")

#: 与 factory.LenientHitlMiddleware._REJECTED_TOOL_NAME 一致 —— 拒绝由
#: 注册表里的 ``__tool_rejected__`` 工具承接（LLM 收到明确拒绝消息）
REJECTED_TOOL_NAME = "__tool_rejected__"

#: 工具输出截断（原 wuwei ToolExecutor serialize 语义，A5-5 移植）：
#: 超长输出在送入 LLM 上下文前截断，防止撑爆上下文窗口
MAX_TOOL_OUTPUT_CHARS = 20_000


def _truncate_output(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit], True

#: ``respond``（人工代答）决策下回灌给模型的工具结果形态
RESPOND_OUTPUT_KEY = "user_response"


def _serialize_output(result: Any) -> str:
    """工具结果统一序列化成 JSON 字符串（orchestrator 的
    ``_extract_tool_output_metadata`` 按 JSON 解析 ok/error 字段）。"""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def _invoke_handler(tool: Any, arguments: dict[str, Any]) -> Any:
    """调用 wuwei Tool.handler（同步 handler 挪线程，异步直接 await）。"""
    handler = tool.handler
    if asyncio.iscoroutinefunction(handler):
        return handler(**arguments)
    return asyncio.to_thread(handler, **arguments)


@dataclass(frozen=True)
class InterruptOnConfig:
    """声明式审批配置（对齐 DeepAgents ``InterruptOnConfig`` 形状）。

    - ``True`` → 使用默认配置（三种决策全开放）；
    - ``allowed_decisions``：限定前端可提交的决策集合；
    - ``description``：随审批事件下发给前端的说明文案。

    ``edit`` 决策在本项目由「approved + modified_arguments」承担（审批面板
    已支持改参预览），因此决策词汇表为 approved / rejected / respond。
    """

    allowed_decisions: tuple[str, ...] = ("approved", "rejected", "respond")
    description: str = ""


@dataclass
class ApprovalOutcome:
    """审批中间结果：放行（可能带改参）/ 拒绝 / 人工代答。

    ``responded=True`` 时工具**不执行**，``response`` 文本作为工具结果回灌。
    """

    rejected: bool = False
    arguments: dict[str, Any] = field(default_factory=dict)
    reject_reason: str = ""
    responded: bool = False
    response: str = ""


class EngineApprovalPolicy:
    """LenientHitl 审批语义 + DeepAgents 式声明式 interrupt_on（阶段 3）。

    优先级（与 LenientHitlMiddleware.before_tool 逐条对齐）：
    1. ``interrupt_on`` 无此工具 / auto_approve 名单（含 ``*`` 哨兵）→ 放行；
    2. auto 档只读工具 → 放行；
    3. 等待人工决策：approved（可带改参）/ rejected（转拒绝工具）/
       respond（人工代答回灌）/ 超时 → 按拒绝。
    """

    def __init__(
        self,
        *,
        approval_manager: Any = None,
        auto_approve_tools: set[str] | list[str] | None = None,
        approval_mode: str = "auto",
        approval_timeout: float = 300.0,
        interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    ) -> None:
        self.approval_manager = approval_manager
        self.auto_approve_tools = set(auto_approve_tools or [])
        from app.services.approval_policy import normalize_approval_mode

        self.approval_mode = normalize_approval_mode(approval_mode)
        self.approval_timeout = float(approval_timeout)
        # interrupt_on 归一化：True → 默认配置；False → 忽略（= 自动放行）
        self.interrupt_on: dict[str, InterruptOnConfig] = {}
        for name, cfg in (interrupt_on or {}).items():
            if cfg is True or isinstance(cfg, InterruptOnConfig):
                self.interrupt_on[name] = cfg if isinstance(cfg, InterruptOnConfig) else InterruptOnConfig()
            elif cfg is False:
                # 显式放行：即使同名出现在 auto_approve 反推里也不中断
                self.auto_approve_tools.add(name)

    def _interrupt_config(self, tool_name: str) -> InterruptOnConfig | None:
        """该工具的中断配置；返回 None 表示自动放行。"""
        if tool_name in self.interrupt_on:
            return self.interrupt_on[tool_name]
        if "*" in self.auto_approve_tools or tool_name in self.auto_approve_tools:
            return None
        # 不在任何放行名单（interrupt_on / auto_approve）→ 需要审批
        # （与阶段 2 的 auto_approve 反推语义一致）
        if self.approval_manager is not None:
            return InterruptOnConfig()
        return None

    def allowed_decisions_for(self, tool_name: str) -> tuple[str, ...]:
        cfg = self._interrupt_config(tool_name)
        return cfg.allowed_decisions if cfg else ()

    async def before_execute(
        self, tool: Any, arguments: dict[str, Any], tool_call_id: str | None = None,
    ) -> ApprovalOutcome:
        """工具执行前的审批判定（LenientHitlMiddleware.before_tool 对齐）。"""
        tool_name = tool.name

        cfg = self._interrupt_config(tool_name)
        if cfg is None:
            return ApprovalOutcome(rejected=False, arguments=arguments)

        # auto 档：只读工具（含细粒度工具的只读子操作）自动放行
        if self.approval_mode == "auto":
            from app.services.approval_policy import is_read_only_tool

            if is_read_only_tool(tool_name, arguments):
                return ApprovalOutcome(rejected=False, arguments=arguments)

        # 请求用户审批（复用 ApprovalManager 完整链路；批准可带改参）
        decision = await self._request_approval(tool, arguments, cfg, tool_call_id=tool_call_id)
        status = getattr(decision, "status", "") if decision is not None else ""
        if status == "respond":
            answer = (getattr(decision, "response", None) or "").strip()
            return ApprovalOutcome(responded=True, response=answer or "（用户未提供答案）")
        if status != "approved":
            # 无决策/超时/拒绝一律按拒绝：宁可让模型换方案，也不把会话卡死
            reason = "审批超时，已按拒绝处理" if decision is None else "用户拒绝了此工具的执行"
            return ApprovalOutcome(rejected=True, reject_reason=reason)
        modified = getattr(decision, "modified_arguments", None)
        if isinstance(modified, dict) and modified:
            return ApprovalOutcome(rejected=False, arguments=modified)
        return ApprovalOutcome(rejected=False, arguments=arguments)

    async def _request_approval(
        self, tool: Any, arguments: dict[str, Any], cfg: InterruptOnConfig,
        tool_call_id: str | None = None,
    ) -> Any:
        if self.approval_manager is None:
            return None
        import uuid as _uuid

        from app.services.agent_service import _current_session_id
        from app.services.approval_types import ApprovalRequest

        request = ApprovalRequest(
            id=_uuid.uuid4().hex,
            session_id=_current_session_id.get() or "default",
            action_type="tool_call",
            payload={
                # 真实 tool_call_id（与 tool_start/tool_results 事件一致）；
                # 无注入上下文（直调工具）时退回随机 id
                "tool_call_id": tool_call_id or f"lg-{_uuid.uuid4().hex[:12]}",
                "tool_name": tool_name_of(tool),
                "arguments": arguments,
                # 声明式决策集随事件下发，前端据此渲染可选项（含代答入口）
                "allowed_decisions": list(cfg.allowed_decisions),
                **({"description": cfg.description} if cfg.description else {}),
            },
        )
        try:
            return await asyncio.wait_for(
                self.approval_manager.request_approval(request),
                timeout=self.approval_timeout,
            )
        except asyncio.TimeoutError:
            _logger.warning(
                "审批等待超过 %.0f 秒，按拒绝处理：tool=%s", self.approval_timeout, tool_name_of(tool)
            )
            return None


def tool_name_of(tool: Any) -> str:
    return getattr(tool, "name", "") or ""


def registry_to_langchain_tools(registry: Any, approval_policy: EngineApprovalPolicy | None = None) -> list[StructuredTool]:
    """wuwei ToolRegistry → LangChain StructuredTool（元数据全保留）。"""
    lc_tools: list[StructuredTool] = []
    rejected_tool = registry.get(REJECTED_TOOL_NAME)
    for tool in registry.list_tools():
        lc_tools.append(_convert_tool(tool, approval_policy, rejected_tool))
    return lc_tools


def _convert_tool(tool: Any, approval_policy: EngineApprovalPolicy | None, rejected_tool: Any) -> StructuredTool:
    execution = getattr(tool, "execution", None)
    side_effect = bool(getattr(execution, "side_effect", False)) if execution is not None else False
    requires_approval = bool(getattr(execution, "requires_approval", False)) if execution is not None else False

    async def _arun(runtime: ToolRuntime | None = None, **kwargs: Any) -> str:
        # LangGraph ToolNode 会按注解注入 ToolRuntime（携带真实 tool_call_id），
        # args_schema 是显式构造的所以注入参数不会进模型可见 schema。
        # 审批事件必须带与 tool_start/tool_results 相同的 tool_call_id，
        # 否则前端按 id 合并失败 → 出现重复工具行 + 审批面板永不关闭。
        import uuid as _uuid

        real_tool_call_id = (getattr(runtime, "tool_call_id", None) if runtime is not None else None) or f"lg-{_uuid.uuid4().hex[:12]}"
        # 有审批策略时先过审批（拒绝 → 走注册表里的 __tool_rejected__ 工具，
        # 与原路径共用同一个 handler，语义/输出一致；respond → 人工代答）
        if approval_policy is not None:
            outcome = await approval_policy.before_execute(tool, kwargs, tool_call_id=real_tool_call_id)
            if outcome.responded:
                return _serialize_output({RESPOND_OUTPUT_KEY: outcome.response, "tool": tool.name})
            if outcome.rejected:
                result = await _invoke_rejected(rejected_tool, {
                    "original_tool": tool.name,
                    "reason": outcome.reject_reason,
                })
                return _serialize_output(result)
            kwargs = outcome.arguments
        result = await _invoke_handler(tool, kwargs)
        serialized = _serialize_output(result)
        # 工具输出截断（原 ToolExecutor 语义移植）
        text, was_truncated = _truncate_output(serialized, MAX_TOOL_OUTPUT_CHARS)
        if was_truncated:
            text += f"\n... [输出已截断，原始 {len(serialized)} 字符]"
        return text

    lc_tool = StructuredTool(
        name=tool.name,
        description=tool.description or tool.name,
        args_schema=tool.parameters.to_schema(),
        coroutine=_arun,
        metadata={
            "display_name": getattr(tool, "display_name", None) or tool.name,
            "side_effect": side_effect,
            "requires_approval": requires_approval,
            "is_concurrency_safe": getattr(tool, "is_concurrency_safe", None),
            # gateway 的 bind_tools 依赖这个反向引用（StructuredTool 是 pydantic
            # 模型，不能挂任意属性；metadata 是 LangChain 的正式扩展点）
            "wuwei_tool": tool,
        },
    )
    return lc_tool


async def _invoke_rejected(rejected_tool: Any, arguments: dict[str, Any]) -> Any:
    """执行注册表里的 ``__tool_rejected__``（LLM 收到明确拒绝消息）。"""
    if rejected_tool is not None:
        try:
            return await _invoke_handler(rejected_tool, arguments)
        except Exception as exc:  # noqa: BLE001 —— 拒绝工具挂了不能打断流程
            _logger.warning("rejected-tool handler failed: %s", exc)
    return {
        "rejected": True,
        "original_tool": arguments.get("original_tool", ""),
        "message": arguments.get("reason", ""),
    }
