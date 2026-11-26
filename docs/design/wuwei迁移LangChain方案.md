# 把 wuwei 全量替换为 LangChain / DeepAgents / LangGraph 的可执行迁移方案

> **实施状态（2026-11-25）：已实施完成。** wuwei 依赖与代码已全部移除；引擎为 DeepAgents
> `create_deep_agent` 0.7.41 + LangChain 1.5.2 + LangGraph 1.2.24，绑定其自身
> `FilesystemBackend`。下方「未实施」为原始方案状态，保留作历史档案；实施差异见 `AGENTS.md`。

> 状态：调研 + 方案（未实施，未改任何代码）
> 调研日期：2026-11-17
> 适用代码版本：backend `wuwei>=3.4.1` / Python `>=3.13,<3.14`
> 调研方式：联网核实 PyPI / 官方文档当前版本 + 只读梳理仓库 `backend/` 实际 import 面

---

## 0. 结论先行（说人话版）

**一句话：这是一次「重写核心引擎」，不是「换个 import」。不建议全量替换，建议按能力维度渐进式替换，且永远保留一个可回退的 wuwei 通道。**

理由（基于实际排查，不是拍脑袋）：

1. **项目对 wuwei 的依赖远超「Agent 循环」这一处。** 全仓 95 个 `.py` 文件提到 wuwei（`backend/` 全量约 94 处引用，含 pycache），分布在 9 个能力维度：Agent 编排 / SSE 事件 / 工具注册 / 中间件栈 / LLM 网关适配器 / 多智能体 / MCP / 会话持久化 / HITL 审批。真正和 wuwei 强耦合的核心文件就有 6 个、合计约 **4200+ 行**：`orchestrator.py`(1693) + `factory.py`(1012) + `wuwei_patches.py`(688) + `session_storage.py`(777) + `llm_providers/adapter.py`(487) + `mcp_service.py`(676)。

2. **很多「框架能力」其实已经是项目自研的，wuwei 只是宿主。** 审批（Redis pub/sub 跨 worker + DB 持久化 + SSE 推送 + 用户改参）、用量记账、多提供商网关 / 企业 Cookie 账号池、`direct` 直通通道、A2UI、workflow 引擎——这些是 AgenticOS 的资产，不是 wuwei 的。迁移时它们**必须原样保留**，需要做的只是把它们「挂」到新引擎上。好消息：这部分不会因为换框架而消失；坏消息：挂接代码要全部重写。

3. **补丁层是迁移的隐藏成本。** `wuwei_patches.py` 用 688 行兜住上游 17+ 条残留缺陷（R-1 ~ R-17），有 27 条回归测试 + 5 条版本兼容守护测试。换框架意味着：这些补丁不再适用（要删），但**它们防的 bug 语义要用新框架重新实现并重新验证**（例如 `_tool_result_is_unknown`、`MAX_CONCURRENT_TOOLS=8` 并发上限、`MAX_TOOL_OUTPUT_CHARS=20000` 截断、`finish_reason="length"` 时工具调用不能丢、usage 收尾帧不能吞）。这部分工作量容易被低估。

4. **框架侧 2026 年的现状是「LangGraph 稳、DeepAgents 新」。** LangGraph 1.2.22、LangChain 1.5.0 已是 Production/Stable；DeepAgents 0.7.39 仍是 **Beta**。DeepAgents 在能力上和 AgenticOS 的需求惊人地契合（subagents / filesystem / skills / memory / HITL / MCP 全是内置），但把 Beta 版当生产核心底座需要评估风险。**推荐主底座选 LangGraph（稳），DeepAgents 作为「参考实现/可选增强」而非第一天就 all-in。**

5. **SSE 事件格式是对前端的硬契约。** 前端消费至少 15 种事件（`text_delta` / `reasoning_delta` / `tool_start` / `tool_end` / `tool_error` / `done` / `error` / `approval_required` / `api_approval_required` / `keepalive` / `run_status` / `artifact_ready` / `chart` / `a2ui` / `user_input_required` …）。LangGraph 有自己的 stream 事件模型（`values`/`updates`/`custom`/`messages`/`debug`，v2/v3 格式还在演进）。**必须写一层事件适配 mapper，把新引擎事件翻译成旧 SSE 事件，前端零改动**——否则前端要跟着大改，风险翻倍。

**总体判断表：**

| 维度 | 判断 |
|---|---|
| 技术可行性 | 高（LangGraph 能力完整覆盖 wuwei 的编排需求） |
| 迁移性质 | 重写核心，非换 import |
| 工作量 | 大（粗估 8–16 人周，见第 8 节，需验证） |
| 风险等级 | 高（SSE 契约、审批语义、多提供商网关、补丁语义） |
| 是否建议全量替换 | **不建议**。建议「绞杀者模式」渐进替换 + 长期双轨 |
| 是否建议现在启动 | 除非有明确痛点（wuwei 上游停止维护 / 招人困难 / 生态诉求），否则**优先级低于还清技术债** |

---

## 1. 调研：2026-11 当下框架现状（联网核实）

> 以下版本均来自 PyPI 官方页面（抓取日期 2026-11-16/17），附录带链接。版本号变化快，**落地时请重新核对**。

### 1.1 三层栈关系（官方定义）

LangChain 官方把整套生态分成三层，这是理解「选谁」的关键：

| 层 | 组件 | 当前稳定版本 | 成熟度 | 定位 |
|---|---|---|---|---|
| 运行时（runtime） | **LangGraph** | **1.2.22**（2026-11-14） | Production/Stable (5) | 有状态图、checkpoint、中断恢复、流式、多智能体编排的底层引擎 |
| 框架 / 轻量 harness | **LangChain** `create_agent` | **1.5.0**（2026-11-11） | Production/Stable (5) | 模型/工具/中间件集成 + 薄 agent harness，底层跑在 LangGraph 上 |
| 重型 harness | **DeepAgents** | **0.7.39**（2026-11-16） | **Beta (4)** | 在 `create_agent` 之上打包了 filesystem / subagents / skills / memory / HITL / shell |

官方原话（deepagents PyPI FAQ）：*"LangGraph is the graph runtime. LangChain's `create_agent` is a minimal agent harness on top of it. Deep Agents is a more opinionated harness on top of `create_agent`."* 三层可组合：**任何 LangGraph `CompiledStateGraph` 都能作为 sub-agent 传给 Deep Agent**。

### 1.2 关键能力边界（与本项目强相关）

| 能力 | LangGraph / DeepAgents 现状 | 对 AgenticOS 的意义 |
|---|---|---|
| **Agent 循环 / 工具调用** | LangGraph 的 `create_react_agent` / LangChain `create_agent`；DeepAgents 默认带完整工具循环 | 可直接映射 wuwei 的 `Agent` + `AgentRunner` |
| **checkpoint / 持久化** | LangGraph checkpointer：内存 / SQLite / Postgres，节点间自动落盘；DeepAgents 继承 | 对应 wuwei `AgentSession` 持久化 + 自研 `session_storage.py`。**但注意**：项目当前**未启用** wuwei checkpointer（补丁层 R-10 注明），消息持久化是自研 DB 方案，迁移时不需要强行套 checkpointer |
| **HITL / 中断恢复** | `interrupt()` + `Command(resume=...)`；1.2.12 起 `interrupt()` 支持 `response_schema`；1.2.20 起每个 interrupt 独立 ID + 可选 `strict_resume`（拒绝过期审批）；`HumanInTheLoopMiddleware` 在 langchain 1.4.6 增加 `interrupt_mode="per_call"`（每个工具调用独立审批） | 对应项目审批。**关键语义差异**：LangGraph 节点从 `interrupt()` 恢复时会**从节点第一行重新执行**（不是 Python 协程挂起点续跑），要求节点逻辑幂等 —— 这与项目「审批后可改参数再执行」吻合，但要专门设计 |
| **流式 SSE** | LangGraph `stream()`/`astream()`，1.2 引入 `version="v2"` 统一 `StreamPart`，v3 streaming 仍 Beta；DeepAgents v0.6 起用 v3 event streaming | 需自建 **SSE 事件适配层**，不能指望前端零成本升级 |
| **多智能体** | LangGraph 原生 supervisor / subgraph / swarm 模式；DeepAgents 内置 `task` 工具派发 sub-agent（独立上下文，0.5 起支持 async subagents，0.7 起 fork 模式保留父 prompt cache） | 对应项目三 Agent PPT（Planner/Designer/Reviewer）+ `AsyncSubAgent` + `ppt_pipeline.py` 的 `StateGraph` |
| **MCP 集成** | LangGraph 1.0（2025-10）起 MCP 工具成为**一等图节点**，享受 checkpoint / 中断 / 流式；langchain 1.4.0（2026-09-01）把 MCP 收进 `langchain.mcp` 命名空间（基于 FastMCP，`MCPAdapter` 取代 `MultiServerMCPClient`），**该命名空间仍 Beta**；MCP elicitation 请求映射为 `interrupt()` | 对应 `mcp_service.py` 的 `HTTPMCPClient`/`StdioMCPClient`/`MCPToolAdapter`。**注意 Beta 状态 + 替换的是不同抽象层** |
| **记忆 / 上下文压缩** | DeepAgents 内置 filesystem（把大文档移出对话历史）+ SummarizationMiddleware（1.4 后改为在 state 保留完整历史） | 对应 `compression.py` 的 `ContextCompressionMiddleware` + `memory_pipeline.py` |
| **技能系统** | DeepAgents 内置 Skills（按需加载的可复用行为） | 对应项目 skill 插件 + `SkillManager`/`FileSystemSkillProvider`。映射度高 |
| **可观测性** | LangSmith 一等支持（tracing/eval/monitoring） | 对应 `TracingMiddleware` + 自建 traces 页面。**是加分项但要评估数据出境/自托管** |
| **安全模型** | DeepAgents 明示 "trust the LLM"，边界要**在工具/沙箱层**强制，不能指望模型自律 | 项目 `approval_policy` / tool_policy 必须保留在工具层，不能依赖框架 |

### 1.3 版本/兼容性快速核对

- 项目 Python 约束 `>=3.13,<3.14`；LangGraph 要求 `>=3.10`、LangChain `>=3.11`、DeepAgents `>=3.11`（分类器覆盖 3.13）。**版本兼容无障碍**。
- DeepAgents 0.7.39 依赖 `langchain≈1.4.6` / `langchain-core≈1.6.10` / `langsmith>=0.14.8`（不同小版本依赖会变，以安装时解析为准，**需验证**）。
- DeepAgents 是 Beta、发版极快（libraries.io 记录 138 次发布、几乎每天一版）。**生产落地必须 pin 版本 + 回归集**，不能跟 latest。

---

## 2. 现状盘点：项目到底用了 wuwei 什么（只读排查结果）

### 2.1 依赖面按能力维度归类

| # | 能力维度 | 关键文件（行数） | 用到的 wuwei 符号 | 复杂度 | 与 wuwei 耦合度 |
|---|---|---|---|---|---|
| 1 | **Agent 编排 / 主循环** | `agent/orchestrator.py`(1693)、`agent/service.py`(327) | `Agent`、`AgentEvent`、`StateGraph` | 极高 | 高（事件 + 循环） |
| 2 | **Agent 工厂 / 中间件栈** | `agent/factory.py`(1012) | `Agent`、`LLMGateway`、`MiddlewareStack`、`HitlMiddleware`、`LoggingMiddleware`、`AsyncSubAgent(Middleware)`、`BudgetMiddleware`、`TracingMiddleware`、`SkillManager`、`FileSystemSkillProvider`、`PluginContext`、内置插件 `calc/python/git/file/text/skill` | 极高 | **极高**（11 类中间件 + 自研子类） |
| 3 | **补丁层** | `agent/wuwei_patches.py`(688) | `Agent`、`AgentRunner`、`ToolExecutor`、`Tool`、`ToolCall`、`Message` | 极高 | **极高**（直接改上游执行语义） |
| 4 | **SSE 事件映射** | `agent/orchestrator.py` 内 `_map_agent_event` + 各处 `yield` | `AgentEvent.type/data` 共 7+ 种事件 | 极高 | 高（前端硬契约） |
| 5 | **LLM 网关 / 适配器** | `llm_providers/adapter.py`(487)、`direct.py`(525)、`runtime.py`(936)、`credentials.py`(803)、`spec.py`(652)、`presets.py`(495)、`discovery.py` 等 | `LLMGateway`、`OpenAIAdapter`、`LLMResponse(Chunk)`、`Message`、`FunctionCall`、`ToolCall`、`LLMError` | 极高 | 中（已有 `direct.py` 做了抽象隔离） |
| 6 | **工具注册** | `app/tools/*.py`（22 文件 / ~5665 行）、`tool_config_service.py` | `ToolRegistry`、`@registry.tool(display_name=…, requires_approval=…)`、`Tool`、`ToolParameters`、`ToolExecutionPolicy` | 高 | 中（装饰器 API 可批量替换，元数据要保住） |
| 7 | **HITL 审批** | `approval_manager.py`(352)、`approval_types.py`(59)、`approval_policy.py` | 仅 `HitlMiddleware.approval_provider` 接口（`ToolCall → bool`）；契约已自建 | 高 | **低**（好消息：审批主体早已自研，wuwei 3.2.1 删掉的类项目自带等价物） |
| 8 | **会话 / 消息持久化** | `session_storage.py`(777) | `AgentSession`、`Message`、`action_log`(ACTION_LOG_KEY/ActionLog) | 高 | 高（按 wuwei 类反序列化，且针对 3.4.1 删字段做了兼容） |
| 9 | **多智能体** | `multi_agent_ppt_service.py`(317)、`ppt_pipeline.py`(228) | `Swarm`/`TeamMember`（注释）、实际用 `LLMGateway`+`ToolRegistry`+`Planner`+`StateGraph` | 中 | 中（PPT 流程实际是顺序 phase + 图编排） |
| 10 | **MCP 工具桥** | `mcp_service.py`(676) | `HTTPMCPClient`、`StdioMCPClient`、`MCPConfig`、`MCPServerConfig`、`MCPToolAdapter` | 高 | 高（直接 import wuwei.mcp） |
| 11 | **上下文压缩 / 记忆** | `agent/compression.py`(89)、`memory_pipeline.py` | `ContextCompressionMiddleware`、`MiddlewareContext`、`State` | 高 | 中高 |
| 12 | **零散使用** | 约 15 个 service（`prompt_polish`、`website_title`、`eval_grader`、`memory_pipeline`、`workflow/nodes`、`knowledge/wiki_compiler` 等） | 多为 `HumanMessage`/`SystemMessage`/`Message` 构造 | 低 | 低（构造消息对象，替换成本低） |

### 2.2 几个影响迁移判断的关键事实

- **补丁层防的是真实线上 bug，不是洁癖。** 例如 R-6（工具结果含 `"status":"unknown"` 被误判 → 丢弃结果并封死会话）、R-8（`CancelledError` 判定失效 → 同批次成功结果全丢）、R-7（装了审批/子智能体中间件后 `parallel_tool_calls` 被静默关闭）、R-1（`finish_reason="length"` 时工具调用被静默丢弃）。**换框架后这些 bug 不会自动消失，要用新框架的 middleware / hook 重新兜住并补回归测试。**
- **`adapter.py` 的 3 处容错同理**：usage 收尾帧被吞、收尾只给 `stop` 时工具调用丢失、兼容网关省略 usage 导致 500。这是 `HardenedOpenAIAdapter` + `RetryingGateway` 存在的理由。
- **`approval_types.py` 已经「半迁移」**：wuwei 3.2.1 删掉了 `ApprovalRequest`/`ApprovalDecision`，项目自己定义了等价 dataclass，并明确「审批流程（Redis pub/sub + DB + SSE）完全自研」。**这是迁移的有利条件：审批状态机不依赖 wuwei。**
- **`direct.py` 已经「半迁移」**：直通通道用 `_to_wuwei_messages` / `openai_tools_to_wuwei` / `wuwei_tool_calls_to_openai` 做转换，语义已是 OpenAI-compatible。**这是另一个有利条件：可以把它改造成 LangChain 的 `ChatOpenAI` 通道，不动上层业务。**
- **消息时间戳、系统消息去重、压缩可观测性等一批测试，本质测的是 wuwei 行为边界**（`test_message_timestamps` / `test_system_message_normalization` / `test_compression_observability` / `test_context_compression`）。换框架后这批测试要重写成「测新框架行为 + 测自定义 mapper」。

---

## 3. 能力映射表：wuwei 现有能力 → LangGraph / DeepAgents 对应方案

| wuwei 能力 | 首选新方案 | 可行性 | 需要自研适配层 | 会倒退 / 需重写 |
|---|---|---|---|---|
| `Agent` + `AgentRunner` 工具循环 | LangGraph `create_react_agent` 或 LangChain `create_agent`（底层 LangGraph） | 高 | 自定义 state（含 session_id / usage / 中间件钩子） | wuwei 特有的 `max_steps`、`parallel_tool_calls`、步骤上限提示语要重写 |
| `AgentEvent` 事件流 | LangGraph `astream(stream_mode=[...])` → **自建 SSE mapper** | 中 | **必须**：把 LangGraph 事件翻译成现有 15+ 种 SSE 事件 | 事件的粒度和时序不会 1:1，前端“看起来”的行为可能变（如 tool_start 时机） |
| `MiddlewareStack` + 11 类中间件 | LangGraph middleware / node hooks；DeepAgents 内置 middleware 可参考 | 中 | **必须**：自研或移植 9 个自定义中间件 | `LenientHitl`、`ObservableCompression`、`SkillInstruction`、`ThinkingHistoryCompatibility`、`ToolPairRepair`、`BatchSafe` 无现成对应 |
| `HitlMiddleware` 审批 | LangGraph `interrupt()` + `Command(resume=)` 或 `HumanInTheLoopMiddleware` | 中 | **必须**：接住现有 `ApprovalManager`（Redis/DB/SSE） | 审批「改参后执行」要用 `response_schema` + update state；跨 worker 需用外部 checkpointer + interrupt ID 对齐；**语义需重点验证** |
| `ToolRegistry` + `@registry.tool` | LangChain `@tool` / `StructuredTool` + 自建 registry | 高 | 需要：保留 `display_name` / `requires_approval` / TOOL_CATALOG 元数据 | 装饰器签名不同，22 个工具文件要批量改；`ToolExecutionPolicy` / 并发 / 截断策略要重做 |
| `LLMGateway` / `OpenAIAdapter` | LangChain `ChatOpenAI` + `init_chat_model` + 自定义 `BaseChatModel` | 中 | **必须**：企业 Cookie 池、账号池、多提供商路由、TLS/超时、`RetryingGateway` 语义 | `adapter.py`/`direct.py` 的 3+ 容错要重写；`openai>=3.40` 与 LangChain 的 openai 依赖可能冲突（`openai>=3.40,<4` vs langchain-openai 要求，**需验证**） |
| `session_storage.py` 持久化 | 保留自研 DB 方案 + 可选 LangGraph checkpointer（Postgres/SQLite） | 中 | 需要：把 `AgentSession`/`Message` 换成 LangChain `BaseMessage` 序列化 | 存量会话/消息 JSON 要迁移或双读；`message_signature` / 时间戳逻辑要重写 |
| `action_log` (ACTION_LOG_KEY) | LangGraph state 自定义字段 | 中 | 需要 | A2UI / artifact 链路依赖它 |
| `Swarm`/`TeamMember`/`StateGraph`（PPT） | LangGraph supervisor / subgraph / `StateGraph` | 高 | 少量 | 现有 PPT 流程实际是顺序 phase，可直接用 LangGraph 图重编排；`Planner` 要自研 |
| `AsyncSubAgent` | DeepAgents `task` 子智能体 / LangGraph 子图 | 中高 | 需要：子智能体结果回灌主 SSE 流 | 0.5 起支持 async、0.7 fork 模式是新特性，**需验证**行为 |
| `mcp_service.py` | `langchain.mcp.MCPAdapter`（Beta）或保留 `mcp` 官方 SDK 自建 | 中 | **必须**：现有 HTTP/Stdio client 配置 + 内网 access 迁移 | langchain.mcp 仍 Beta；`destructive_hint` 等注解可用于审批策略（加分）；MCP elicitation→interrupt 要接审批 |
| `ContextCompressionMiddleware` | DeepAgents filesystem + SummarizationMiddleware，或自研 | 中 | 需要：保留可观测性（压缩事件/统计） | 1.4 后 SummarizationMiddleware 保留全历史，与现有压缩策略语义不同，**需验证** |
| `SkillManager` + skill 插件 | DeepAgents 内置 Skills | 中高 | 少量 | 技能定义格式不同，要转换 |
| `BudgetMiddleware` / 用量记账 | 自研（LangGraph 无等价计费） + node-level timeout/error handler（1.2） | 中 | **必须**：保留现有预算断路器 + `agent_usage_events` | 完全自研，框架只提供 hook 点 |
| `TracingMiddleware` | LangSmith（一等支持）或保留自建 | 中 | 需要：数据出境 / 自托管评估 | 引入 LangSmith 依赖会改变运维形态 |
| `JsonOutputParser`（announcement） | LangChain `JsonOutputParser` | 高 | 无 | 直接映射 |

**贯穿结论**：真正「开箱即用、几乎不用改」的只有零散消息构造、`JsonOutputParser`、PPT 图编排这几类；**核心引擎、事件、中间件、网关、审批、持久化、MCP 全都需要自建适配层或重写**。这就是「重写核心」的含义。

---

## 4. 分层迁移路线

把上面的映射按「改造方式」分成三层，按此顺序推进：

### 第 1 层：可直接映射（低风险，先做，建立信心）
- 零散 `HumanMessage`/`SystemMessage`/`Message` 构造 → LangChain message 类（约 15 个 service，逐个换）
- `JsonOutputParser` → LangChain 同名组件
- PPT 的 `StateGraph` 流程 → LangGraph `StateGraph`（`Planner` 自研）
- `openai` SDK 调用点 → 保持（LangChain 也用 openai，**但先验证版本冲突，见风险 R-9**）

### 第 2 层：需自研适配层（工作量大头，核心战场）
- **SSE 事件适配 mapper**（新引擎事件 → 现有 15+ 种 SSE 事件，前端零改动）—— 这是整个迁移的「咽喉」，先写它并用契约测试锁死。
- **LLM 网关适配层**：`ChatOpenAI` / 自定义 `BaseChatModel` 承载企业 Cookie 池、账号池、多提供商路由、3+ 容错。
- **工具注册适配层**：`@tool` + 元数据 registry，保住 `display_name`/`requires_approval`/TOOL_CATALOG。
- **审批适配层**：`interrupt()`/`Command(resume=)` ↔ 现有 `ApprovalManager`（Redis/DB/SSE/改参）。
- **持久化适配层**：`BaseMessage` 序列化 ↔ 现有 DB 表；可选叠加 LangGraph checkpointer（Postgres）。
- **中间件移植**：9 个自定义中间件逐个用 LangGraph hook / DeepAgents middleware 重写，每个配回归测试。
- **MCP 适配层**：`langchain.mcp.MCPAdapter`（Beta）或保留官方 SDK 自建（更稳）。

### 第 3 层：能力会倒退 / 需要重新实现（重点评估，可能选择「不迁」）
- **补丁层 17+ 条缺陷的防护语义**：要在新框架重新实现 + 重新验证，否则迁移即回归。
- **wuwei 特有的 run 语义**：`max_steps` 步骤上限、步骤上限提示语（`ThinkingHistoryCompatibilityMiddleware` 依赖逐字匹配）、`parallel_tool_calls` 开关行为。
- **用量记账**：与 wuwei `done` 事件的 `usage` 字段绑定，改成从 LangGraph state / LLM response 抓取。
- **A2UI / `action_log` / 图表 / artifact_ready**：依赖 wuwei `AgentEvent.data` 的形状，要逐一核对新事件能否提供等价数据。
- **结论**：第 3 层里的「能力倒退」项，应在每阶段验收时逐项打勾，打不了勾的能力要么自研补齐，要么明确接受降级（需产品确认）。

---

## 5. 分阶段执行计划

> 总原则：**绞杀者模式（Strangler Fig）**——新引擎先在隔离的路口接管一小部分流量，验证后再逐步扩大；wuwei 通道始终保留，任一阶段可秒级切回。
> 前置条件：先建一个「行为基线回归集」——用现有 1364 个测试里的 Agent 相关用例 + 一批真实会话录制，作为新老引擎对拍的 oracle。

### 阶段 0：准备与基线（不碰生产）
- 锁定版本：pin `langgraph==1.2.22` / `langchain==1.5.0`（DeepAgents 暂不引入），验证 Python 3.13 + openai 3.x 依赖可解析。
- 建行为基线：跑通现有全量测试，录制 20–30 条代表性会话（含审批、工具并发、多轮、压缩、MCP、PPT）的输入/输出 SSE 序列。
- **验收**：全量测试绿；基线会话文件入库。
- **回退**：无代码改动，天然回退。

### 阶段 1：地基适配层（新引擎只跑「直通 / 无状态」场景）
- 实现 LLM 网关适配层（`ChatOpenAI` + 自定义 BaseChatModel），先覆盖 `direct.py` 直通通道（无工具、无会话、无审批）。
- 实现消息/工具注册的适配层（`@tool` + 元数据 registry），补元数据一致性测试。
- 验证 3+ 容错（usage 收尾帧、工具调用收尾、usage 缺失）在新通道上仍成立。
- **验收**：`direct` 通道的端点在对拍基线上输出一致；工具元数据 100% 对齐 TOOL_CATALOG。
- **回退**：`direct` 通道保留 wuwei 开关，一个配置切回。

### 阶段 2：SSE 事件适配 + 单 Agent 工具循环（最关键的咽喉）
- 实现 SSE mapper：LangGraph `astream` → 现有 15+ 种事件；用基线会话做逐事件对拍。
- 用 LangGraph 搭一个最小工具循环，`parallel_tool_calls`、`max_steps`、步骤上限提示语对齐。
- 移植第 3 层里的工具侧补丁（并发上限 8、输出截断 20000、unknown 判定、finish_reason=length 工具调用）。
- **验收**：基线会话（无审批）的 SSE 序列与 wuwei 输出**逐事件等价**（允许时间戳等非语义字段差异）；27 条补丁回归测试「 migrating 版」全绿。
- **回退**：`stream_chat` 入口按 session/feature flag 路由到 wuwei 或新引擎。

### 阶段 3：HITL 审批（语义最复杂，单独一期）
- 用 `interrupt()` + `Command(resume=)` 接住现有 `ApprovalManager`；实现「改参后执行」（`response_schema` + update state）。
- 跨 worker：接入 LangGraph checkpointer（Postgres）+ interrupt ID / strict_resume，验证多 tab / 重试 / 过期审批不串单（对应 1.2.20 的 per-interrupt ID + strict resume 能力）。
- SSE 审批事件（`approval_required` / `api_approval_required` / `user_decision`）格式对齐前端。
- **验收**：审批全链路回归（发起→预览→改参→批准/拒绝→工具执行→结果回灌）+ 并发/过期审批安全测试全绿。
- **回退**：审批开关独立；审批路径可单独切回 wuwei。

### 阶段 4：持久化 / 记忆 / 多智能体 / MCP
- 会话/消息持久化适配（含存量数据双读）；压缩中间件移植（保留可观测性）。
- PPT 三 Agent 流程迁到 LangGraph supervisor/subgraph；`AsyncSubAgent` → DeepAgents task 或 LangGraph 子图（**此处再决定要不要引入 DeepAgents**）。
- MCP 迁到 `langchain.mcp.MCPAdapter`（Beta，需特性开关）或保留官方 SDK 自建（更稳）。
- **验收**：会话跨重启恢复、压缩、多 Agent PPT、MCP 工具调用四组基线对拍通过。
- **回退**：各子能力独立开关。

### 阶段 5：全量切换 + 补丁层退役
- 流量 100% 切到新引擎，观察期（建议 2–4 周）内 wuwei 通道保持热备。
- 确认稳定后，删除 `wuwei_patches.py` / `adapter.py` 的 wuwei 依赖 / `pyproject.toml` 的 `wuwei` 依赖；保留补丁语义对应的新测试。
- **验收**：全量测试绿 + 观察期内 P0/P1 故障为零；`grep -r wuwei backend/app` 无生产代码命中（测试/文档除外）。
- **回退**：观察期内可整体回切；退役后回退需回滚版本发布。

> 每阶段都必须「可独立验收 + 可独立回退」，禁止跨阶段合并提交造成无法定位的回归。

---

## 6. 风险清单

| ID | 风险 | 等级 | 说明与缓解 |
|---|---|---|---|
| R-1 | **94 处引用 + 4200+ 行核心代码重写** | 高 | 不是机械替换；用绞杀者模式分阶段，每阶段对拍；禁止一次性 PR |
| R-2 | **补丁层 17+ 缺陷语义回归** | 高 | 27 条补丁测试是资产，迁移时逐条转成「新引擎行为测试」；补丁能删，语义不能丢 |
| R-3 | **SSE 事件格式对前端兼容性** | 高 | 自建 mapper + 逐事件契约测试，前端零改动；对事件时序差异做产品确认 |
| R-4 | **审批 / HITL 语义** | 高 | LangGraph 节点从 `interrupt()` 重入（非协程续跑），节点须幂等；改参、跨 worker、过期审批要专项验证；现有审批是自研 Redis/DB，状态机不依赖 wuwei 是利好 |
| R-5 | **用量记账 / 多提供商网关 / 企业 Cookie 账号池** | 高 | 完全自研能力，框架无对应；网关适配层必须逐一保留重试/超时/fallback/账号池逻辑与 3+ 容错 |
| R-6 | **MCP 集成** | 中高 | `langchain.mcp` 仍 Beta 且抽象层不同；更稳的选择是保留官方 SDK 自建适配，避免绑 Beta |
| R-7 | **DeepAgents 仍是 Beta、发版极快** | 中高 | 不作为第一天主底座；pin 版本 + 回归集；主底座用稳定的 LangGraph |
| R-8 | **依赖冲突：openai 3.x vs langchain-openai** | 中高 | `openai>=3.40,<4` 与 LangChain 生态可能不匹配，**落地前必须做依赖解析验证** |
| R-9 | **存量会话/消息 JSON 兼容** | 中 | `session_storage.py` 按 wuwei `Message` 反序列化且绕过 3.4.1 删字段；迁移要双读或数据迁移脚本 |
| R-10 | **A2UI / artifact / chart 对事件 data 形状的依赖** | 中 | 逐一核对新事件能否提供等价字段（`tool_call_id` / `display_name` / `error_type` / `usage`） |
| R-11 | **可观测性 / 数据出境** | 中 | 是否引入 LangSmith 需评估运维与合规；可先保留自建 traces |
| R-12 | **团队学习曲线与「两套并存」期的维护成本** | 中 | 双轨期会有两套 dev 体验；用 feature flag 收敛，限定双轨时长 |
| R-13 | **上游 wuwei 仍在演进** | 低中 | 迁移期间 wuwei 可能继续修 bug，基线会漂移；冻结 wuwei 版本直到切换完成 |

---

## 7. 工作量与优先级建议

### 7.1 粗估工作量（需验证，按 1 名熟悉本项目的工程师）

| 阶段 | 粗估 | 说明 |
|---|---|---|
| 0 准备与基线 | 3–5 天 | 测试梳理 + 会话录制 |
| 1 地基适配层 | 1.5–2.5 周 | 网关 / 消息 / 工具注册 / 容错 |
| 2 SSE + 单 Agent 循环 | 2.5–4 周 | **咽喉**，含补丁语义移植与对拍 |
| 3 HITL 审批 | 1.5–2.5 周 | 语义最复杂 |
| 4 持久化/多智能体/MCP | 2–3 周 | 可拆并行 |
| 5 全量切换 + 退役 | 1–2 周 + 观察期 | 含热备观察 |
| **合计** | **约 9–16 人周** | 不含产品验收与不可预见回归 |

> 这是乐观估计（假设 1 人全程、基线良好）。若并行度低、基线测试不全、审批/网关坑多，可能显著上浮。

### 7.2 优先级建议（诚实版）

1. **默认选项：不全量替换，做「渐进式 + 双轨」。** 在 wuwei 还在维护、项目没有因它受阻的情况下，全量替换的 ROI 不高——迁移成本（9–16 人周 + 高风险）换来的主要是「生态现代化 / 招人友好 / 上游缺陷不再需要补丁」，而项目已有的自研资产（审批、网关、记账、SSE）并不会因为换框架而变简单。

2. **触发全量替换的合理时机**（满足其一再启动）：
   - wuwei 上游停更 / 社区萎缩，补丁层开始兜不住新问题；
   - 招聘/协作明确要求主流栈，或要接 LangSmith 生态；
   - 新能力（如复杂多智能体、长程任务）wuwei 难以支撑而 LangGraph 明显更合适。

3. **无论是否全量替换，立刻可做的低风险动作**：
   - 把 `direct.py` 改造成 LangChain `ChatOpenAI` 通道（无状态、隔离，风险最低，能先验证依赖兼容）。
   - 给 SSE mapper 写契约测试（即便暂不迁移，也能锁住前端契约）。
   - 用 LangGraph 重写 PPT 的 `StateGraph` 流程（独立模块，可快速验证收益）。

4. **底座选择**：主底座用 **LangGraph（Stable）**；DeepAgents（Beta）作为「能力参考 + 阶段 4 可选引入」，不要第一天就绑死。

5. **最后强调**：迁移的成败不在于「能不能 import 成功」，而在于**那 27 条补丁测试所代表的线上 bug 语义、15+ 种 SSE 事件的时序契约、以及审批改参/跨 worker 的正确性**能否在新引擎上被完整重建。把这三件事作为一票否决的验收项。

---

## 8. 调研来源附录（带链接）

### 官方 / PyPI（版本与能力，抓取 2026-11-16/17）
- LangGraph PyPI（1.2.22，Production/Stable，Python>=3.10，durable execution/streaming/HITL/persistence）：https://pypi.org/project/langgraph/
- LangChain PyPI（1.5.0，Production/Stable，agents 构建在 LangGraph 之上）：https://pypi.org/project/langchain/
- DeepAgents PyPI（0.7.39，Beta，Python>=3.11，subagents/filesystem/context/shell/memory/HITL/skills/MCP，"trust the LLM" 安全模型，三层栈 FAQ）：https://pypi.org/project/deepagents/
- LangChain 生态三层栈官方说明（products/concepts）：https://docs.langchain.com/oss/python/concepts/products
- LangGraph 官方概览：https://docs.langchain.com/oss/python/langgraph/overview
- DeepAgents 官方文档：https://docs.langchain.com/oss/python/deepagents/overview
- LangChain agents（create_agent）：https://docs.langchain.com/oss/python/langchain/agents
- LangGraph API Reference：https://reference.langchain.com/python/langgraph/
- DeepAgents API Reference：https://reference.langchain.com/python/deepagents/
- DeepAgents 变更日志（版本历史）：https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/CHANGELOG.md
- LangGraph Releases：https://github.com/langchain-ai/langgraph/releases

### 版本/变更细节（2026 年时间线，需以官方 changelog 二次核实）
- LangGraph 更新汇总（1.2.12 response_schema、1.2.20 每 interrupt 独立 ID + strict resume、langchain 1.4.0 `langchain.mcp`、HumanInTheLoopMiddleware per_call）：https://linkneon.com/langgraph-updates
- LangGraph 1.2.20 strict resume 深度解析（节点重入语义、per-interrupt ID）：https://gyanaangan.in/blog/langgraph-1220-deep-dive-safer-human-in-the-loop-agents-with-strict-resume
- LangGraph 1.0 / 1.2 能力（v2 streaming、per-node timeout、graceful shutdown、checkpoint）：https://jbinternational.co.uk/article/view/4680
- LangGraph 1.0 MCP 一等图节点：http://agentmarketcap.ai/blog/2026/08/05/langgraph-10-mcp-first-class-graph-nodes
- DeepAgents 版本演进（0.4/0.5/0.6/0.7、async subagents、v3 streaming）：https://aiwiki.ai/wiki/langgraph/edit?section=deep-agents
- DeepAgents 0.7 评测与安全/生产化解读：https://wavect.io/blog/langchain-deep-agents-review
- deepagents 版本与依赖历史（libraries.io）：https://libraries.io/pypi/deepagents

### 项目内事实来源（本地文件，非网络）
- `backend/pyproject.toml`（Python 3.13 / wuwei>=3.4.1 / openai>=3.40,<4 / MCP extra）
- `backend/app/services/agent/{orchestrator,factory,wuwei_patches,service,compression}.py`
- `backend/app/services/{approval_manager,approval_types,session_storage,mcp_service,multi_agent_ppt_service,ppt_pipeline}.py`
- `backend/app/services/llm_providers/{adapter,direct,runtime,credentials,spec}.py`
- `backend/app/tools/*.py`（22 文件 / ~5665 行）
- `backend/tests/test_wuwei_patches.py`（27 测试）、`test_wuwei_compat.py`（5 测试）
- `frontend/src`（SSE 事件消费：`error`/`done`/`approval_required`/`a2ui`/`tool_*`/`chart`/`run_status` 等）

> 凡标注「**需验证**」处（依赖冲突、DeepAgents async subagent 行为、SummarizationMiddleware 语义、langchain.mcp Beta 特性），落地阶段必须以实际 pin 版本 + 回归集验证为准，不要照搬本文结论。

---

## 9. 立场修正：能用现成就别自研（2026-11-17 追加）

> 用户明确要求：**"能用已有的就不要自研，哪怕改动比较大"**，并点名 HITL 用 DeepAgents、RAG 用现成框架。
> 这一节**修正本文前文（第 0 / 7 节）偏保守的"保留自研资产"立场**。原判断从"迁移风险最小化"出发，现按"长期维护成本最小化 + 拥抱生态"重新评估。两版判断并列保留，便于对比决策。

### 9.1 修正前后对照

| 能力 | 原文立场（保守） | 修正后立场（拥抱现成） | 触发原因 |
|---|---|---|---|
| **HITL 审批** | 保留自研 `ApprovalManager`（Redis/DB/SSE），LangGraph `interrupt()` 只是挂接 | **改用 DeepAgents 内置 `interrupt_on` + `HumanInTheLoopMiddleware`**，自研层缩薄为"审批 UI + 决策回灌适配" | 官方确认 HITL 是内置能力，`approve/edit/reject/respond` 四决策齐全，**明确不需要自己写审批状态机** |
| **RAG 检索** | 保留自研 BM25+向量 RRF+启发式重排，只换重排器 | **检索/索引层迁 LlamaIndex**（内置 hybrid search + rerank + 160+ loader），LangGraph 只管编排，评估接 RAGAS | 检索是 LlamaIndex 的看家本领，自研 RRF/重排在功能与可维护性上都不划算 |
| **技能 / 记忆 / 上下文** | 保留自研 skill + memory_pipeline + compression | **迁 DeepAgents 的 Skills + Memory + filesystem 上下文管理**，自研特化逻辑做插件 | 三项均为 DeepAgents 内置，映射度高 |
| **LLM 网关** | LiteLLM **仅 SDK 库旁路 PoC**（零部署），Cookie 网关自研保留；**不用 Proxy**（外部系统） | **标准 provider 统一调用走 LiteLLM SDK 库**，只保留企业 Cookie 账号池这一小块自研 | LiteLLM SDK 100+ provider 统一接口是现成的；Proxy 的"成本/预算/虚拟 key"是外部服务，本项目已自研，不需要 |
| **沙箱** | 分级加固（可选后端） | **必须换真隔离**（E2B / gVisor / Firecracker），正则黑名单不可接受 | 这是安全底线，不是"要不要拥抱生态"的问题 |

### 9.2 DeepAgents HITL：核实到的事实（官方文档）

- `interrupt_on={tool_name: True | False | InterruptOnConfig}` 即可为工具配置审批策略；设置后框架**自动把 `HumanInTheLoopMiddleware` 加入栈**。
- 支持四种决策：`approve`（原参数执行）/ `edit`（改参后执行）/ `reject`（跳过并反馈）/ `respond`（人工代答，用于 ask_user）。可配 `allowed_decisions` 限定。
- `when` predicate 支持**条件中断**（仅特定情况暂停，其余自动放行，需 `langchain>=1.3.3`）→ 正好对应项目"三档审批策略（ask/auto/full）"。
- 中断时 `PatchToolCallsMiddleware` 自动修复 message history（对应补丁层部分 bug 语义）。
- **恢复机制**：`agent.invoke(Command(resume={"decisions": [...]}) , config={"configurable":{"thread_id": ...}})`，多工具审批批处理、decisions 需与 action_requests 顺序一致，流式下用 `messages`+`updates` 双 mode。
- **硬性前提**：必须有 checkpointer 持久化 interrupt↔resume 之间的状态，且恢复必须用同一个 `thread_id`。→ 这就是要把项目审批的 Redis/DB 状态**改造成 LangGraph checkpointer**（可用 Redis/Postgres checkpointer），而不是反过来让框架迁就自研状态机。
- 官方**没有要求自建审批状态机**：应用只需"展示待审批动作 → 收集决策 → 按顺序构造 decisions → resume"。

**对迁移的影响**：阶段 3（HITL）从"用 `interrupt()` 手工接住 `ApprovalManager`"简化为"用 DeepAgents `interrupt_on` 声明式配置 + 把审批 UI/通知/审计事件适配到新回调"。**但注意**：DeepAgents 仍是 Beta（见 1.1），若阶段 3 时它已稳定则直接用；否则退路是 LangGraph `HumanInTheLoopMiddleware`（已 Stable，能力同源）。

### 9.3 RAG：业界主流分工（2026）

| 层 | 推荐 | 理由 |
|---|---|---|
| 检索 / 索引 | **LlamaIndex** | 内置 dense+sparse hybrid search、automerging/递归检索、rerank、160+ document loader；检索精度公认最优（对比 LangChain "adequate"） |
| 编排 / agentic RAG | **LangGraph** | 有状态多步工作流、HITL、LangSmith 可观测；与本文主底座一致 |
| 重排器 | **FlashRank / bge-reranker-v2-m3**（详见优化方案 3B.1） | 轻量 CPU 或高精度多语言两档 |
| 评估 | **RAGAS** | RAG 质量客观指标的事实标准，可配 Langfuse 做实时监控 |
| 向量库 | Qdrant / pgvector（详见数据库评估文档） | 规模上来了再上，小规模先用现有 |

业界共识（多来源一致）：**"LlamaIndex for data/retrieval + LangGraph for orchestration" 是 2026 生产 RAG 的主流混合栈**，不是二选一。对本项目意味着：自研的 `knowledge/`（retrieval 888 行 / ingest_pipeline 526 行 / wiki_compiler 814 行 / rerank）中，**检索与索引职责应交给 LlamaIndex，自研只保留业务特化部分（visibility/Casbin 行级鉴权、scope 过滤、与 workspace/知识库模型的绑定）**。这些鉴权规则要在 LlamaIndex retriever 外包一层过滤，不能丢。

### 9.4 修正后的分层迁移路线（替换第 4 层内容）

- **第 1 层（可直接映射）**：不变。
- **第 2 层（适配层）**：SSE mapper、LLM 网关（标准 provider → LiteLLM **SDK 库**）、工具注册、持久化、MCP——不变，但网关层用 SDK 做统一调用（**不用 Proxy 服务**）。
- **第 3 层（原"需重写"的能力，现大量改为"用现成"）**：
  - HITL 审批 → DeepAgents `interrupt_on`（原自研状态机大部分可删）
  - RAG 检索/索引 → LlamaIndex（原自研 BM25/RRF/重排大部分可删）
  - 技能 → DeepAgents Skills；记忆/压缩 → DeepAgents Memory + filesystem
  - 多智能体 → LangGraph supervisor/subgraph；AsyncSubAgent → DeepAgents `task`
  - 评估 → RAGAS；可观测 → Langfuse 或 LangSmith
  - **仍需自研的只剩**：SSE 事件适配、企业 Cookie 账号池、用量按 user 归属记账、业务鉴权规则（Casbin/visibility）、差异化的工具元数据与审批 UI。
- **结论变化**：原文说"核心引擎、事件、中间件、网关、审批、持久化、MCP 全都要自建适配层或重写"——修正后，**审批、RAG、技能、记忆、多智能体、评估这六项可以从"重写"降级为"配置+薄适配"**，真正必须自研的收敛到"事件契约 + 差异化鉴权/记账/网关"。**总工作量可能下降，但前端/数据/鉴权的适配风险仍高**。

### 9.5 修正后的风险与取舍

| 风险 | 说明 |
|---|---|
| **DeepAgents Beta** | 拿 Beta 当 HITL 底座仍需谨慎；用 LangGraph `HumanInTheLoopMiddleware`（Stable）作等价退路 |
| **LlamaIndex 与现有数据模型整合** | 需把 visibility/Casbin 鉴权包在 retriever 外层；存量切片/embedding 格式要对齐；这是"改动大"的主要来源 |
| **多框架并存复杂度** | LangGraph（编排）+ LlamaIndex（检索）+ LiteLLM **SDK 库**（网关调用）+ DeepAgents（harness）+ RAGAS（评估）五套栈，依赖与版本管理成本显著上升，CI 需锁版本矩阵；**均为纯库，无外部系统部署负担** |
| **权限边界不能交给框架** | DeepAgents 明示 "trust the LLM"，鉴权/沙箱边界必须在工具层强制；换成现成框架**不等于**可以放松自研安全逻辑 |
| **工作量重估** | 原文 9–16 人周按"大量自研"估；改用现成后总工时可能下降，但引入 5 套框架的集成与回归成本会补回来，**净变化需重新评估（需验证）** |

### 9.6 两轮能力调研的引用

本节结论结合了同日两项补充调研，完整内容见：
- `docs/design/项目逐功能优化方案.md` 第 **3B 节**（自研 → 成熟库替换映射：JWT/密码哈希/MemoryRedis/重排/LiteLLM/沙箱/任务队列）
- `docs/design/项目逐功能优化方案.md` 第 **3C 节**（HelloGitHub / GitHub Trending 近一年可接入项目：Langfuse / SOPS / browser-use / Qdrant / Lightpanda，及 Phoenix 的 Elastic License 红线）
- `docs/design/数据库选型评估-MySQL到PostgreSQL.md`（向量检索与 JSONB 选型）

### 9.7 技能系统与框架内置能力替换（2026-11-17 追加）

用户追问「skill 为啥要自研，DeepAgents/LangGraph 有的就别自研」。逐项核对代码 + 官方文档后的结论：

**技能系统真相**：并非全自研。**加载层本就是 wuwei 框架**（`factory.py` 的 `setup_skill_plugin` + `SkillManager`，暴露 `list_skills`/`load_skill`）。自研的只有三层中的后两层——管理层（`skill_service.py` 394 行：DB/CRUD/zip 上传/后台 UI/画像绑定）和一句提示词注入（`SKILL_INSTRUCTION` + `SkillInstructionMiddleware`）。
- 加载层 → 换 DeepAgents `SkillsMiddleware`：机制同构（启动时只读 name/description，命中才读全文），22 个 SKILL.md 是标准 Agent Skills 格式、原样兼容 → **直接删换**。
- 提示词注入 → 框架自带技能发现提示词 → **直接删**。
- 管理层 → 框架没有（不管 DB/上传/权限）→ **保留**，改为管理磁盘 SKILL.md 目录、DB 退化为索引。
- 唯一坑：项目 SKILL.md 有 `allowed_tools`/`when_to_use` 等自定义 frontmatter，框架只读 `name`/`description`，需用工具过滤或写进正文适配。

**其余能力替换决策**（详见 `系统改造总方案.md` 第 5.4 节）：

| 自研 | 框架内置 | 决策 |
|---|---|---|
| 上下文压缩 89 行（仅 wuwei 上游补日志） | 自动摘要 + 大结果转文件 | 直接删 |
| 记忆 L0-L3（1310 行） | Memory(AGENTS.md) + StoreBackend 隔离 + 后台整合 | 部分换（蒸馏规则留） |
| 子智能体 | `task` 工具（同步/异步并行） | 直接换 |
| todos（几乎无） | `write_todos` | 白捡 |
| 文件工具（零散） | 虚拟文件系统 ls/read/write/glob/grep | 白捡 |
| 多智能体 PPT（317 行） | LangGraph supervisor/subgraph | 部分换（领域提示词留） |
| MCP（1039 行） | langchain-mcp 官方支持 | 部分换（凭据注入/SSRF 外壳留） |
| shell/沙箱（216 行黑名单可绕过） | shell 工具 + 可插拔沙箱后端 | 必须换（安全底线） |

**说明**：用户立场是「能用现成就用、哪怕改动大」，故「部分换」项也倾向尽量交给框架；只有框架确实没有（管理后台/权限外壳/业务蒸馏规则）或换框架会降能力（自定义 frontmatter）时才保留。注意 DeepAgents 明示 "trust the LLM"，安全边界仍须在工具层强制。

---

## 10. 调研来源追加（2026-11-17）

- DeepAgents HITL 官方文档（`interrupt_on` / 四决策 / `when` predicate / checkpointer 前提 / `Command(resume=)`）：https://docs.langchain.com/oss/python/deepagents/human-in-the-loop
- LangGraph `HumanInTheLoopMiddleware`（Stable 退路，per-call 审批）：https://docs.langchain.com/oss/python/langchain/agents
- RAG 框架分工对比（LlamaIndex 检索最优 / LangGraph 编排 / 混合栈是主流）：https://ortemtech.com/blog/langchain-vs-llamaindex-vs-custom-rag-comparison-2026/ 、https://www.marsdevs.com/compare/langchain-vs-llamaindex
- 向量 RAG → GraphRAG 演进与框架定位：https://automationcalling.com/2026/04/23/evolving-pure-vector-rag-into-graph-aware-retrieval-a-practical-path-for-existing-pipelines/
- DeepAgents Skills（Agent Skills 规范 / SKILL.md frontmatter / 三级渐进加载 / SkillsMiddleware）：https://docs.langchain.com/oss/python/deepagents/skills
- DeepAgents Memory（文件式记忆 / AGENTS.md / StoreBackend 按 user·agent 命名空间隔离 / 后台整合 / checkpointer 情景记忆）：https://docs.langchain.com/oss/python/deepagents/long-term-memory
- RAGAS / Langfuse 评估监控事实标准：https://checkthat.ai/ai-answers/b6f52f3a-a19b-4ea8-9b8f-89574a032722
