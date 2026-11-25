# AGENTS.md

This file provides guidance to Reasonix/Claude Code when working with code in this repository.

## Project overview

AgenticOS is a general-purpose AI agent platform with a FastAPI backend and React+Vite frontend. It supports multi-mode AI chat, configurable agent profiles, local skill storage, human-in-the-loop (HITL) approval workflows, and an admin dashboard.

## Development commands

**Backend** (requires Python >=3.13,<3.14, managed with `uv`):

```bash
cd backend
uv sync                                    # install dependencies
uv run python main.py                      # start dev server on :8001 with live reload
uv run pytest                              # run all tests
uv run pytest tests/test_auth.py           # run a single test file
uv run pytest -k "test_name"               # run tests matching a pattern
```

**Frontend** (managed with `npm`):

```bash
cd frontend
npm install                                # install dependencies
npm run dev                                # start Vite dev server on :3001
npm run build                              # production build
npm run lint                               # TypeScript type-check (tsc --noEmit) + eslint
```

The Vite dev server proxies `/api` to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8001`). Set `DISABLE_HMR=true` to disable HMR if needed.

**Docker**: `cd deploy && docker compose up -d --build` deploys both services. Backend on :8001, frontend served by nginx on :3001 (proxies `/api` to backend).

## Architecture

### Backend (FastAPI + LangGraph / 自研 native 层)

编排引擎是 **DeepAgents 0.7.41（`create_deep_agent`，底层 LangChain 1.5.2 / LangGraph 1.2.24 Stable）**；
技能 / 上下文压缩 / 子代理 / 文件系统已全部换成 DeepAgents 内置 middleware，绑定它自己的
`FilesystemBackend`（root=`data/`）。LLM 网关仍是自研 `NativeLLMGateway`（多提供商/Cookie 池容错），
MCP 走官方 SDK，预算断路因 DeepAgents 无等价计费语义而保留自研。wuwei 已整体退役。

```
backend/
  main.py                          # uvicorn launcher, chdir to project root
  app/
    main.py                        # FastAPI app factory, CORS, lifespan (init_db, Redis),
                                   #   exception handlers, 32MB request size limit
    db/
      models.py                    # all SQLAlchemy ORM models (AppDateTime timezone-aware)
      session.py                   # engine, session factory, init_db
    core/
      config.py                    # Pydantic Settings — reads all env vars from .env
      security.py                  # JWT (PyJWT, 算法白名单) + Argon2id (pbkdf2 双验过渡)
      redis.py                     # Redis connection manager (single/cluster), fakeredis fallback
    api/
      router.py                    # top-level router, mounts v1 sub-router
      deps.py                      # dependency injection: get_db, get_current_user, require_admin
      v1/
        router.py                  # mounts all endpoint routers
        endpoints/
          auth.py, agent.py, agent_profiles.py, skills.py,
          dashboard.py, health.py, tool_config.py, users.py,
          announcements.py, email.py, external_systems.py,
          files.py, memory.py, suggest.py, website.py,
          api_keys.py, knowledge.py, permissions.py, settings.py,
          tasks.py, credentials.py
        # api_keys.py: 用户级 API Key（表 api_keys，供 OpenAI 兼容网关鉴权）
    tools/
      email_tools.py               # IMAP/SMTP email tools
    services/
      agent/                       # core orchestrator package (agent_service.py is a
                                   #   facade re-exporting this package; keep new code here)
        service.py                 # AgentService = AgentFactory + StreamOrchestrator + ArtifactFactory (mixins)
        orchestrator.py            # StreamOrchestrator — SSE event mapping, event pump
                                   #   (approval / user-input / api-approval / decision queues),
                                   #   usage recording, session persistence, keepalive
        factory.py                 # AgentFactory — 组装 LangGraphAgent（工具注册表 / 审批策略 /
                                   #   预算 / 压缩器 / 异步子代理 / 技能工具箱）
        langgraph_engine/
          engine.py                # LangGraphAgent：LangChain create_agent 编排 + 引擎语义
                                   #   (tool-pair 修复 / thinking 兼容过滤 / max_steps 截断)
          chat_model.py            # GatewayChatModel：自研 NativeLLMGateway → BaseChatModel
                                   #   （流式 tool_call_chunks 做「累积快照→增量」换算，回归见
                                   #   test_langgraph_engine.py）
          tools_adapter.py         # registry → LC StructuredTool；EngineApprovalPolicy
                                   #   （声明式 interrupt_on + 四决策 + ToolRuntime 注入真实
                                   #   tool_call_id）；MAX_TOOL_OUTPUT_CHARS 截断
        native/                    # 自研运行时层（原 wuwei 能力逐文件移植，行为语义保留）
          types.py                 # BaseMessage/AgentEvent/LLMResponse（wire 格式与
                                   #   agent_messages.message_json 兼容）
          gateway.py               # NativeLLMGateway：openai SDK 直连多提供商（Cookie 账号池/
                                   #   重试容错/usage 收尾帧/工具调用收尾 finish 纠正）
          tool_registry.py         # ToolRegistry + @registry.tool 装饰器（jsonschema 校验）
          budget.py                # check_budget 函数式预算断路（BudgetExhausted）
          context_compression.py   # ContextCompressor：阈值触发 + LLM 结构化摘要 + 配对回补
          async_sub_agent.py       # AsyncSubAgentManager（start/check/cancel/list 四工具）
          skill.py + fs_provider.py# SkillManager（load_token 账本 + allowed_tools 白名单）
          action_log.py, builtin/  # 动作日志 + 10 个内置工具插件
        artifacts.py, prompts.py
      llm_providers/               # 多提供商配置（NativeLLMGateway 构建，litellm_poc PoC）
      mcp_native/                  # MCP 客户端/会话/工具桥（官方 mcp SDK，自研层）
      mcp_service.py               # MCP 服务器配置 CRUD（imports mcp_native）
      agent_profile_service.py     # profile CRUD, built-in default profiles, runtime resolution
      skill_service.py             # skill CRUD, zip upload, filesystem management
      approval_manager.py          # HITL approval workflow (Redis pending + subscriber broadcast,
                                   #   persisted to agent_approvals; restart-survivable)
      interactions.py              # InteractionBroker — unified "wait-for-human" coordinator for
                                   #   the three light kinds (api_approval / user_input / decision):
                                   #   session queue + per-interaction futures + Redis pub/sub
                                   #   (multi-worker safe) + unified timeout + stream-end cleanup.
                                   #   Tool approval does NOT go through it (ApprovalManager keeps
                                   #   DB audit + modified_arguments). coordinators.py / decision_tools
                                   #   are thin facades over this broker; SSE event names unchanged.
      redis_relay.py               # shared Redis pub/sub → asyncio.Queue forwarding helpers
      tool_config_service.py       # tool catalog with per-mode defaults, sub-tool approval
      session_storage.py           # DB-backed 会话/消息持久化（native wire 格式）
      knowledge/                   # LlamaIndex 全量接管的检索栈（见下方检索小节）
      llm_factory.py               # 角色化 LLM 构建（chat/fast/embed），OTel 埋点统一入口
      otel_service.py              # OTel SDK（OTEL_ENABLED 默认关）→ DBSpanExporter 写 otel_spans
      sandbox.py                   # SANDBOX_BACKEND (auto/none/nsjail/bubblewrap) 命令沙箱
      secret_loader.py             # SOPS_FILE 解密合并（app/core/secret_loader）
      ppt_artifact_service.py      # assembles the SVG deck artifact from save_slide /
                                   #   save_slides_batch tool outputs (XML sanitize, finalize hook)
      ppt/                         # PPT SVG pipeline: svg_layouts / svg_quality_checker(+checkers/)
                                   #   svg_position_calculator / theme_token_resolver (brand design
                                   #   themes from data/design-systems) / svg_finalize / svg_to_pptx
                                   #   (native .pptx export) / pptx_to_svg / template_import /
                                   #   svg_editor / image_backends / anti_slop_checker / design_craft
      auth_service.py              # registration, login, session management, rate limiting
      rate_limiter.py              # Redis fixed-window rate limiting (auth + agent stream)
      cache_service.py             # Redis-backed cache (input suggestions, presence, approval queues)
      memory_service.py            # agent memory management
      external_system_service.py   # external system integrations (+ external_systems/ coordinators)
      website_deploy_service.py    # website deployment
      announcement_service.py      # announcement CRUD
        engine.py                  # pure computation: graph validation, scheduler,
                                   #   {{inputs.x}} / {{nodes.<id>.output}} variable
                                   #   resolution (restricted dotted-path lookup, no eval)
        nodes.py                   # built-in handlers: llm / knowledge / http (SSRF
                                   #   guarded, redirects off) / template / start
        service.py                 # DB orchestration: per-step persistence,
                                   #   human_input pause/resume (DB is the only
                                   #   source of truth; resume survives restart)
      admin_ops.py + app_platform.py  # /api/v1/admin/* 批量运维 + 网站应用化平台端点
    prompts.py                     # system prompts for agent modes
```

### 知识库检索（LlamaIndex 全量接管）

`services/knowledge/retrieval.py` 的检索机制全部由 LlamaIndex 组件承担，
旧手写实现（MySQL FULLTEXT / PG trgm / Python BM25 三路 + 手写 RRF）已退役：

- **BM25**：`llama_index.retrievers.bm25.BM25Retriever`（bm25s 引擎），页级语料
  jieba 预分词；检索器实例走进程内缓存（TTL/LRU/超限不缓存，
  `invalidate_knowledge_cache` 失效钩子不变）。
- **向量**：`KBVectorRetriever`（BaseRetriever）—— 段级余弦 + 页级 max 聚合，
  无切片时页级兜底；embedding 不可用自动退化为纯 BM25。
- **融合**：`QueryFusionRetriever`（RECIPROCAL_RANK，RRF k=60，`num_queries=1`
  不引入 LLM）；模块导入时置 `Settings.llm = None` 阻断懒加载 OpenAI。
- **重排**：启发式四信号（`rerank.score_result`）+ FlashRank cross-encoder
  精排（`KB_RERANK_*`）。**score 契约不变**：对外 0~1 相对相关度 +
  `score_threshold` 可解释；ACL/visibility 过滤在检索器构建前完成。
- 回归：`test_kb_hybrid_retrieval.py`（score 语义/纯语义召回/双通道提升）、
  `test_kb_retrieval_regression.py`（8 个中文查询 top-3 + 缓存 + 失效钩子）、
  `test_kb_chunk_rerank_acl.py`。
- **pgvector 可选加速**（`knowledge/pgvector.py`）：PG + vector 扩展 + vector 列
  三者齐备时走库内 `<=>` 排序（HNSW 生效），任一条件不满足自动降级应用侧余弦
  —— 行为一致、零迁移负担；回归 `test_kb_pgvector.py`。
- **检索质量在线指标**：滑窗采样（2000 条）记录 hit_rate/empty_rate/延迟分位/
  无结果查询 Top50，`GET /api/v1/knowledge/metrics/search-quality`。
- **RAGAS 旁路 PoC**（`eval_ragas_poc.py`，对齐 litellm_poc 纪律）：纯库零部署、
  不接 Langfuse；四指标（faithfulness/answer_relevancy/context_precision/
  context_recall）+ 零依赖离线指标（hit_rate/context_overlap）。
  ⚠️ ragas **不进 pyproject**（连 extra 都不行）：uv lock 解析全环境时
  ragas→instructor 钉 `openai<3.0` 与本项目 `openai>=3.40` 硬冲突（实测
  No solution）；真实联网评估在**独立 venv** 里 `pip install ragas`，
  代码契约由 test_eval_ragas_poc.py（fake-module）锁定，无 ragas 也能跑。
- **任务队列运维台**：提交时登记 Redis 元数据注册表（TTL 7 天/上限 500），
  `GET /tasks`（列表+过滤）、`GET /tasks/stats`（队列深度）、
  `POST /tasks/{id}/retry`（CAP_DANGEROUS）；前端「任务队列」面板。
  路由顺序注意：`/tasks` 与 `/tasks/stats` 必须注册在 `/tasks/{task_id}` **之前**。

### Agent modes & engine semantics

| Mode | Default tools | Behavior summary |
|------|--------------|-----------------|
| `general` | calc, time, file (approval required) | Daily Q&A, lightweight tool use |
| `ppt` | SVG slide tools (`save_slide` / `save_slides_batch`, quality & theme tools) | Structured presentation generation — agent writes SVG slides, backend pipeline exports native .pptx |
| `website` | calc, time, file, npm | Web/frontend development mode |
| `office` | Univer document/sheet tools | Office document & spreadsheet editing (Univer integration) |
| `email` | calc, time, skill | Email management via IMAP/SMTP |

引擎语义（原 wuwei middleware 栈的等价物，已内建进 LangGraphAgent /
`factory.py` 组装）：
- **HITL（`EngineApprovalPolicy`）** — session-level three-tier approval
  (`ask`/`auto`/`full`)，lenient rejection（拒绝转 `__tool_rejected__` 消息，
  LLM 可响应而非异常）；四决策 approved（含改参=edit）/ rejected /
  **respond（人工代答：工具不执行，用户答案回灌模型）**，超时按拒绝
- **thinking 兼容过滤** — 过滤合成 assistant 回复，适配 provider 思考模式
- **SkillInstruction** — 技能说明注入 agent 上下文；`allowed_tools` 白名单
  在工具执行前由引擎检查（`ALWAYS_ALLOWED_TOOLS` 豁免）
- **AsyncSubAgentManager** — 后台异步子代理（code_analyst / file_processor）
- **并发工具执行** — `AGENT_PARALLEL_TOOL_CALLS` 门控；并发安全的只读工具
  并行、写类串行（LangChain ToolNode 层由 policy 钩子保持审批语义）

### DeepAgents + LangGraph 单引擎

引擎图由 `create_deep_agent` 构建（替代原 `create_agent`），内置 FilesystemMiddleware /
SummarizationMiddleware / SubAgentMiddleware / SkillsMiddleware / PatchToolCallsMiddleware
通过 backend 参数启用。factory 传 `FilesystemBackend(root_dir=data/)` + profile 的 skill 目录
+ 声明式子代理；SSE mapper 与审批 tool_call_id 注入保持兼容。

`AGENT_ENGINE` 兼容开关已移除——langgraph 是唯一引擎（`config.py` 保留
`agent_engine` 字段读取历史 env，但工厂不再分支）。编排链路：
`GatewayChatModel`（自研网关挂接）→ `create_agent` → `ToolNode`（审批策略钩子
复用同一个 `ApprovalManager`）→ 引擎吐 `AgentEvent`，orchestrator 的 SSE
mapper / 持久化 / 审批泵 / trace 零改动消费；契约测试 `test_langgraph_engine.py`。

- 战线 B 自研归位已完成：JWT→PyJWT（算法白名单）、密码哈希→Argon2id（pbkdf2 双验过渡，
  登录成功自动升级）、内存 Redis fallback→fakeredis、检索重排→FlashRank（`KB_RERANK_BACKEND`，
  不可用自动降级启发式）、task_queue arq 时代废弃壳已删（关闭入口 `close_queue`）。
- 战线 C：PG 为生产推荐（`uv sync --extra pg` + `DATABASE_URL=postgresql+psycopg://...`），
  双轨回归 `test_postgres_dualtrack.py`；启动迁移失败在**生产环境阻断**
  （`ENVIRONMENT=production`）。
- 权限双轨已统一（3H 档 A）：后端 `role == "admin"` 硬编码全部换成 `roles.is_admin_like()` /
  `require_capability`（published-items 审批按 `gallery:manage`），KB 管理员判定收敛在
  `acl.is_kb_admin`；Casbin 策略改动经 Redis 广播即时失效（`POLICY_INVALIDATION_CHANNEL`）。
  前端 `AdminSidebar` 菜单按 capability 过滤渲染。
- 前端 API 类型生成：`npm run gen:api`（openapi-typescript，数据源 backend/openapi.json 或
  `--url`）产出 `src/types/api-schema.ts`；新前端模块优先用它配合 `openapi-fetch`
  （`services/openapiClient.ts` 提供 `apiV1` 客户端 + `unwrap` 解包，试点：tasks 运维台；
  老的 27 个手写 service 按「新模块先用」渐进迁移）。

### HITL 阶段 3 + 沙箱 + 可观测 + 密钥 + LiteLLM

- **A3 HITL（`test_hitl_phase3.py`）**：引擎采用**声明式 `interrupt_on`**
  （`{tool: True | InterruptOnConfig}`，factory 从 profile.approval_tools 构建）；
  决策词汇表对齐四决策 —— approved（含改参=edit）/ rejected（转
  `__tool_rejected__` 消息）/ **respond（人工代答：工具不执行，用户答案回灌
  模型）**，超时按拒绝。审批事件携带**真实 tool_call_id**（LangGraph
  `ToolRuntime` 注入，与 tool_start/tool_results 一致 —— 否则前端按 id 合并
  失败出现重复工具行 + 审批面板永不关闭）。前端审批面板带代答输入行；
  后端 `ApprovalDecisionRequest.status` 支持 `respond`。并发/过期/跨 worker
  pub/sub 回归齐备；复用同一个 ApprovalManager（Redis pub/sub + DB 审计不变）。
- **沙箱真隔离**：`SANDBOX_BACKEND`（auto/none/nsjail/bubblewrap）——auto 在
  Linux 检测 nsjail/bwrap 即启用（根只读 + 工作区可写 + rlimits，保留网络供
  npm build），命令黑名单在所有模式下仍先行生效；非 Linux/缺二进制安全退档。
- **OTel 纯库埋点**：`OTEL_ENABLED`（默认关）→ TracerProvider + 自定义
  DBSpanExporter 写 `otel_spans` 表（0028 迁移）；`llm_factory` 构建入口统一
  包装 LLM 网关 generate（provider/model/stream 属性），FastAPI 请求中间件
  可按需取 tracer；不接 Langfuse/不部署 collector。
- **SOPS**：`SOPS_FILE` 指向 sops 加密的 dotenv，`app/core/secret_loader.py`
  在 Settings 读 env 前解密合并（真实环境变量优先；失败 CRITICAL 告警不阻断）。
- **LiteLLM 旁路 PoC**：`provider_type=litellm`（可选 extra `litellm`）→
  `litellm_poc.py` 统一调用映射（非流式 PoC，流式走主路径自研网关）；
  **Proxy 形态按红线排除**。
- **E-P1 后台运维**：`/api/v1/admin/users/batch`（删除叠加 CAP_DANGEROUS）、
  `/api/v1/admin/api-keys/batch`、`GET/PUT /api/v1/admin/quota`（system_settings
  存储，check_daily_quota 优先读 DB）、`/api/v1/admin/approvals/pending`
  （部署/发布/工具审批三类聚合）+ 前端「审批中心」面板；`/api/v1/health/components`
  依赖级探针（DB/Redis/配置档位/限流降级计数）。限流器 5 个降级路径
  （Redis 不可用走进程内 fallback，多实例会超发）统一计数 + 60s 节流告警。

### Async Sub-Agents

`AsyncSubAgentManager` (`services/agent/native/async_sub_agent.py`) injects 4 tools: `start_async_task`, `check_async_task`, `cancel_async_task`, `list_async_tasks`. Two built-in sub-agents: `code_analyst` (Python/calc/git) and `file_processor` (file read/write/search). Controlled by `ASYNC_SUB_AGENTS_ENABLED` env var.

### PPT SVG pipeline

PPT generation is SVG-first — the agent writes slides as SVG, the backend converts to native .pptx:

- **Agent side** (`prompts.py` PPT_SYSTEM_PROMPT + `tools/ppt_tools.py`): the model must call `save_slide` / `save_slides_batch` (never emit SVG in chat). SVG uses `viewBox="0 0 1280 720"`, colors only via `var(--token)` referencing an injected brand design theme; forbidden constructs: `<style>`, `<foreignObject>`, `<mask>`, `<animate>`, `class`, `rgba()`.
- **Themes**: `services/ppt/theme_token_resolver.py` maps theme names (apple, github, stripe, government_blue…) to CSS token sets generated from `data/design-systems/`; frontend fetches the list via `GET /api/v1/agent/ppt/themes`.
- **Backend pipeline** (`services/ppt/`): XML sanitizing (`ppt_artifact_service.py`) → `svg_finalize` (image embed/crop/repair, `image_backends/` + `image_search.py`) → `svg_quality_checker` + `checkers/` + `anti_slop_checker` / `design_craft` (layout diversity, anti-uniformity rules) → `svg_to_pptx/` (DrawingML conversion, native editable .pptx) → `svg_to_pptx/pptx_cli.py`.
- **pptx_to_svg/**: reverse direction (import an existing .pptx into the editor pipeline, `svg_editor/server.py`).
- **template_import/**: manifest-driven theme/template import.
- The chat-mode default is the tool-driven path above (StateGraph 编排流与
  multi-agent PPT 服务已随 wuwei 退役删除)。

### Sub-tool approval

Per-tool approval supports sub-tool granularity. `TOOL_CATALOG` in `tool_config_service.py` defines `sub_tools` per tool. The admin UI can toggle approval per sub-tool, stored in `approval_sub_tools_json` column. Empty list = all sub-tools require approval (backward compatible).

### HITL approval flow

When an agent invokes a tool that requires approval:
1. `EngineApprovalPolicy.before_execute`（工具包装层）触发 `ApprovalManager.request_approval()`，persists to `agent_approvals` table；事件携带真实 tool_call_id（`ToolRuntime` 注入）
2. Frontend receives `approval_required` SSE event (includes sub-tool info), shows `PendingApprovalPanel`
3. User approves/rejects/responds → `POST /api/v1/agent/approvals/{id}/decision`
4. Future is resolved, agent proceeds or aborts; timeout after `HITL_TIMEOUT_SECONDS` (default 300s)

### Workflow engine（已下线）

workflow 工作流引擎（v1 P0-3）已**整体删除**（2026-11-20 用户决策）：后端
`services/workflow/`、`tools/workflow_tools.py`、`endpoints/workflows.py`、
`WorkflowModel`/`WorkflowRunModel` 表模型、`use_workflows`/`view_workflow_runs`
权限 feature、前端 WorkflowManagement/Canvas/GraphEditor 面板与 e2e 测试。
`workflows`/`workflow_runs` 两张历史表保留在存量库中（无代码引用）；
`DEFAULT_RESTRICTED_FEATURES` 机制保留（列表暂空），未来受限功能直接追加。


### SSE streaming protocol

`POST /api/v1/agent/stream` returns a stream of JSON events (one per line). The frontend dispatcher (`agentService.ts applyAgentEvent`) handles 16 event types:

| Event | Meaning |
|-------|---------|
| `session` | Session metadata on connect |
| `run_status` | Phase changes: `thinking` → `streaming` / `generating_ppt` / `rendering_ppt` → `done` |
| `delta` | LLM text token streaming |
| `reasoning_delta` | LLM reasoning/thinking token streaming |
| `chart` | Chart spec for inline rendering (echarts) |
| `a2ui` | Generative-UI component payload |
| `tool_calls` | Tool call initiated |
| `tool_results` | Tool call completed |
| `tool_error` | Tool call failed |
| `approval_required` | Tool call needs human approval (HITL) |
| `api_approval_required` | External-system API call needs approval |
| `user_input_required` | Missing-arguments form requested by a tool |
| `user_decision` | Decision question with options for the user |
| `artifact_ready` | Finished artifact — payload `type` ∈ `ppt` / `website` / `spreadsheet` / `document` |
| `done` | Normal completion with usage stats |
| `error` | Fatal error with optional usage stats |

Note: `keepalive` SSE events are emitted during long waits (e.g. HITL approval); the frontend resets its 60s idle timeout on every message including keepalive.

### Context compression

When `context_compression_enabled` is true (default), `ContextCompressor` (`services/agent/native/context_compression.py`) is invoked by the engine before each LLM call once the estimated token load crosses the trigger. It uses the LLM itself to summarize conversation history, keeping the most recent `context_keep_recent_turns` (default 6) turns intact and never cutting mid tool-call pair; summary failures cool down 600s.

### Frontend design system

Tailwind 4 + CSS variables in `src/index.css`（shadcn 兼容 token + `@theme inline` 桥接；`theme-palette.css` 把全部默认 oklch 色阶覆写为 v3 hex —— **Chrome 85 硬约束：禁 oklch / color-mix**）。Key conventions:
- **Palette**: zinc（近黑）为主 —— `--primary: #18181b`（浅色主 CTA）/ 深色下反相；indigo 为点缀（`--ring: #6366f1`、focus halo `--ring-halo`、流式光标/进度强调）。语义色 success/error/warning/info 全部带 `dark:` 成对写法。
- **Surfaces**: `--surface-0`(页面底) → `--surface-1`(卡片) → `--surface-2/3`(嵌套/代码块)；边框 `--border-subtle/medium/strong`。**禁止硬编码** `bg-white` / `slate-*` / `zinc-50` 一类浅色类（深色模式会破），一律走 token 或 `dark:` 配对。
- **Border radius**: 控件 8px (`rounded-md`) → 卡片 12px (`rounded-lg`) → 弹层 16px (`rounded-xl`) → 气泡 24px (`rounded-2xl`)；胶囊/头像 `rounded-full`。
- **Animations**: 弹层动画由 `tw-animate-css` 提供（注意：只能用相对路径导入 `../node_modules/tw-animate-css/dist/tw-animate.css`，裸包名会因 exports 的 style-condition 解析失败）。共享 motion variants 在 `src/lib/motion.ts`（统一 easeOutQuint `[0.16,1,0.3,1]`、150-250ms、`staggerContainer`/`listItem`）。**页面根节点必须 `initial={false}`**：整页可见性绝不依赖 motion 入场（AnimatePresence mode="wait" + 懒加载竞态会把页面卡在 opacity:0 白屏），入场动效下沉到内容层（admin 用 CSS `.admin-page-stage`，rAF 无关、reduced-motion 全局开关已接入）。
- **Decoration 克制**: 巨型吉祥物水印（>400px）与 infinite bg-blob 动画已从 Home/AgentStore/登录注册移除；吉祥物只出现在空状态/加载/报错等情绪场景。
- **Font weights**: `font-medium`(500) / `font-semibold`(600) / 标题 `font-bold` 允许。
- **Micro-interactions**: `active:scale-[0.98]`、`transition-all duration-150`、hover 位移 ≤4px；列表/卡片群入场用 stagger（每项 45ms，上限 300ms）。
- **Admin**: 与 chat 同一套 token（`admin-card`/`admin-page-stage`/`admin-nav-item` 等语义类在 index.css）；20 个管理面板全部 `React.lazy` 分包 + `Suspense` 骨架（`TabFallback`），行级动画走 `data-table.tsx` 的 `animate-in`。
- **Auth**: Login/Signup 共用 `components/auth/AuthShell.tsx`（极光 + 水印 + 返回按钮 + 卡片入场）。

### Frontend (React 19 + TypeScript + Tailwind 4 + Vite)

```
frontend/src/
  App.tsx                          # BrowserRouter, lazy-loaded routes
  pages/
    Chat.tsx                       # main chat page, orchestrates hooks and layout
    Home.tsx, AgentStore.tsx, AgentEditor.tsx, Login.tsx, Signup.tsx,
    AdminDashboard.tsx, Gallery.tsx, Wrapped.tsx, PublicAgentChat.tsx
  components/
    chat/                          # ChatMainArea, ChatInput, ChatMessage, ChatTimeline,
                                   # Sidebar, ArtifactPanel, PendingApprovalPanel,
                                   # MessagesList, ChatSearch, ChatSuggestions,
                                   # DecisionPanel, EmailSettingsPanel, EmailPreviewPanel,
                                   # IntegrationMarket
    admin/                         # AdminSidebar, DashboardCharts, DashboardStats,
                                   #   UserManagement, AgentManagement, SkillManagement, …(20 panels)
    ppt/                           # PptArtifactPanel
    office/                        # DocEditor (Univer document editor)
    auth/                          # ProtectedRoute
    settings/                      # Settings panels (incl. EvalPanel)
    website/                       # Website-related components
    ui/                            # Badge, Button, Card, EmptyState, Input, Modal,
                                   # Skeleton, Toast, Tooltip, AnimatedIcons, MascotIcons
  hooks/
    useChatStream.ts               # SSE consumption orchestration (optimistic updates,
                                   #   rAF-batched flush + 350ms 兜底（后台标签页 rAF
                                   #   会饿死，只等 rAF 会把发送卡死在请求前）,
                                   #   approval submissions) — wraps sendMessageStream
                                   #   from agentService
    useChatSessions.ts             # localStorage session cache (max 24 sessions)
    useChatScroll.ts, useChatSearch.ts, useDragAndDrop.ts
    useInputSuggest.ts             # input suggestions
    useTheme.ts                    # theme management
    useConfirm.tsx                 # confirmation dialog
  stores/
    chatStore.ts                   # zustand: chat UI state + session DATA (sessions,
                                   #   currentSessionId, runStatus, pendingDecisions).
                                   #   setters keep the React Dispatch<SetStateAction> contract
                                   #   so the hooks above work unchanged. Components subscribe
                                   #   per-slice via useChatStore(selector) — never call it
                                   #   without a selector (re-renders on every keystroke).
  contexts/
    ChatContext.tsx                # actions + refs + derived flags only (data moved to store;
                                   #   single consumer: ChatMainArea)
  services/
    agentService.ts                # 纯 re-export 门面（拆分见 services/agent/）
    agent/
      shared.ts                    # 类型契约（AgentServiceOptions/StreamState）+ 工具结果
                                   #   映射 helpers + 端点常量
      events.ts                    # applyAgentEvent：16 种 SSE 事件分发（纯函数，回归测试
                                   #   直接喂事件不必拉 fetchEventSource）
      stream.ts                    # sendMessageStream（fetchEventSource + 60s 心跳超时）
      api.ts                       # 审批/决策/制品/会话/PPT 导出等 REST 调用
    authService.ts, agentProfileService.ts, skillService.ts,
    dashboardService.ts, toolConfigService.ts, userService.ts,
    conversationService.ts, configService.ts,
    announcementService.ts, emailService.ts, fileService.ts,
    integrationService.ts, memoryService.ts, websiteService.ts,
    knowledgeService.ts, llmProviderService.ts
  lib/
    utils.ts                       # cn() classname helper (clsx + tailwind-merge)
    safePreview.ts                 # safe HTML preview rendering (chart.js from /vendor)
    datetime.ts                    # date formatting utilities
    sessionMerge.ts                # localStorage ↔ backend session reconciliation
```

Routes: `/` (Home), `/chat` (Chat, protected), `/agents` (AgentStore, protected), `/agents/new` + `/agents/:profileId/edit` (AgentEditor, protected), `/gallery` (作品库, protected), `/wrapped` + `/wrapped/:year` (年度报告, protected), `/app/:slug` (PublicAgentChat — public, no auth), `/login`, `/signup`, `/admin` (AdminDashboard, admin-only).

**Session persistence**: Chat sessions are cached in localStorage via `useChatSessions` hook (max 24 sessions, 80 messages each, with text truncation). This provides instant reload on page refresh while the backend remains the source of truth.

Vite config: `@` path alias resolves to `frontend/src`. Production build splits vendor chunks: `react-core`, `motion-vendor`, `markdown-vendor`, `admin-vendor`.

### Database

Default SQLite at `./data/agenticos.db`. Configurable to MySQL via `DATABASE_URL`. Tables: users, auth_sessions, agent_sessions, agent_messages, agent_usage_events, agent_tool_configs, agent_profiles, agent_profile_tools, skills, agent_profile_skills, user_installed_agents, agent_approvals, ppt_artifacts, video_artifacts (legacy, mode removed), user_email_credentials, announcements, external_systems (+external_apis/params/credentials), memory entries, knowledge base tables (kb_*), system_settings, agent_run_traces, api_keys, email_verification_codes.

Schema evolution is two-stage on startup: `Base.metadata.create_all()` creates missing tables, then `_apply_pending_migrations()` runs alembic (`backend/alembic/versions/`, 25 migrations) — `upgrade head` if `alembic_version` exists, `stamp head` on a fresh DB; migration failure logs but does not block startup. The baseline migration must be kept in sync with `models.py` by hand (see `baseline_20260930.py`). `seed_tool_configs()` and `seed_agent_profiles()` run on every startup (idempotent upserts). The first registered user automatically becomes admin.

### Tests

Backend tests (110+ files in `backend/tests/`) use pytest with `httpx` for async HTTP testing. The pytest config sets `pythonpath = ["."]` so tests can import directly from `app.*`. Run with `uv run pytest`. Current baseline: **~1381 passed / 25 skipped, 0 failed**（workflow 下线后 81 个 workflow 测试随模块删除）.

Tests cover: auth, agent stream, tool config, users, dashboard, skills, agent profiles, agent service, langgraph engine contracts (`test_langgraph_engine.py` — 直答/工具/HITL/拒绝/审批元数据/流式累积 delta 回归), HITL phase 3 (`test_hitl_phase3.py` — 四决策/并发/过期/pub-sub), llm providers (native gateway retry/usage contracts), MCP, website mode defaults, local skill import, health, SVG to PPTX, theme token resolver, KB retrieval (LlamaIndex: hybrid score semantics / Chinese recall top-3 / retriever cache / ACL), artifact slug inference (website artifacts must be session-scoped — never a global "most recent dist" scan), alembic migration chain integrity (含新列登记清单 + 索引级联删除), task queue ops registry (test_task_queue_ops.py), pgvector probe/degrade contract (test_kb_pgvector.py), RAGAS dataset contract (test_eval_ragas_poc.py, fake-module), log request context (test_log_context.py).

## Key environment variables

Essential: `OPENAI_API_KEY` (LLM access), `AUTH_SECRET_KEY` (JWT signing).

Also: `KB_RERANK_BACKEND` (`auto` | `flashrank` | `heuristic`), `KB_RERANK_TOP_K`,
`KB_RERANK_FLASHRANK_WEIGHT`.

Also important:
- `OPENAI_BASE_URL` — custom LLM endpoint (default: OpenAI)
- `OPENAI_MODEL` — model name (default: `gpt-5.4`)
- `DATABASE_URL` — defaults to SQLite; MySQL/PostgreSQL URLs supported (`postgresql+psycopg://...` 为生产推荐)
- `REDIS_URL` — Redis connection (empty = fakeredis fallback)
- `HITL_ENABLED` / `HITL_REQUIRE_APPROVAL_TOOLS` — approval workflow control
- `AGENT_MAX_STEPS` — max tool-calling steps per run (default: 10)
- `AGENT_PARALLEL_TOOL_CALLS` — enable parallel tool execution (default: false)
- `ASYNC_SUB_AGENTS_ENABLED` — enable async sub-agent middleware (default: true)
- `AGENT_BUDGET_MAX_TOKENS` / `AGENT_BUDGET_MAX_COST_USD` / `AGENT_BUDGET_ON_EXHAUSTED` —
  run-level budget circuit breaker（native `check_budget`，非 middleware）.
  Hard cap raises `BudgetExhausted`, surfaced as an SSE `error` event
  (`error_type=BudgetExhausted`); soft cap (80%) logs a warning
- `KNOWLEDGE_VECTOR_ENABLED` / `KNOWLEDGE_EMBEDDING_*` — 向量检索通道与 embedding 模型
- `SANDBOX_BACKEND` (`auto` | `none` | `nsjail` | `bubblewrap`) — 命令沙箱
- `OTEL_ENABLED` — OTel SDK 埋点（默认关，写 otel_spans 表）
- `SOPS_FILE` — sops 加密 dotenv 路径
- `AGENT_STREAM_RATE_LIMIT` / `AGENT_STREAM_RATE_WINDOW_SECONDS` — per-user
  fixed-window rate limit on `POST /agent/stream` (default: 30 runs / 300s,
  admins exempt, `<=0` disables; 429 + `Retry-After` on excess)
- `LDAP_ENABLED` — bootstrap switch for the DB-configured LDAP integration
  (full config managed by admins in System Settings → LDAP; stored in
  `system_settings` under `ldap.*` keys, bind password encrypted)

See `backend/.env.example` for the full list.

## Notes

- **结构化日志上下文**（`app/core/log_context.py`）：HTTP 中间件为每个请求绑定
  `request_id`（响应头 `X-Request-ID` 回传）+ path；业务深处可增量补
  session_id/user_id。root logger 挂 `RequestContextFilter`，所有日志自动携带
  字段 —— 排障时 `grep request_id=<id>` 串联一次请求的全部日志。

- All datetime fields use `AppDateTime` type decorator for timezone-aware handling (default: `APP_TIMEZONE`)
- Backend changes working directory to project root on startup so native file tools resolve paths correctly
- Redis is optional — leave `REDIS_URL` empty for fakeredis fallback during development
- wuwei 已完全退役：依赖已从 pyproject 移除、venv 中无此包、`import wuwei` 失败是预期；上游问题清单 `docs/upstream/wuwei-3.0.2-问题清单.md` 仅作历史存档
