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
          engine.py                # LangGraphAgent：DeepAgents create_deep_agent 编排 + 差异化语义
                                   #   (tool-pair 修复 / thinking 兼容过滤 / HITL / 预算 / max_steps 截断)
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
- **融合**：RRF k=60，**直接复用同一轮 BM25/向量的排名结果**选候选页，
  不引入 LLM、不重复检索（旧实现各跑两遍 = 单次 search 4 次检索，冷启动
  重复建索引；实测首查 854ms→760ms、热查 11–33ms→8–10ms）。
  回归 `test_search_reuses_retrieval_results_no_duplicate_work`。
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
  无结果查询 Top50 + `stages_ms_p50/p95`（bm25/vector/rerank 分阶段）+
  `bm25_cache_hit_rate`，`GET /api/v1/knowledge/metrics/search-quality`。
- **缓存键正确性**：pgvector 探测缓存按「方言+URL」而非 `id(session)`（短生命周期
  session 会漏缓存，每次查询白跑 2 条元数据 SQL）；embedding 查询缓存键含
  model/base_url/dimensions，`reset_knowledge_embedder()` 同步清查询缓存；
  remote embedding 复用 `httpx.Client` 连接池（编译一批切片不再逐次 TLS 握手）。
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

安全边界：DeepAgents 默认注入的 `write_file` / `edit_file` / `delete` 内置工具不经过
我们的 HITL 审批策略，factory 通过 `permissions=[deny write /**]` 将其收敛为只读；
真正落盘走自研 file 工具（会话级 workspace 隔离 + HITL 审批）。`execute` 工具在
`FilesystemBackend`（非 sandbox）下不可用。

**关键安全修复**：backend 必须 `virtual_mode=True`——False 模式下绝对路径会绕过
`root_dir` 直接读取宿主文件系统（已实测可越权读 root 外任意文件）。True 模式下
所有路径是虚拟路径（`/skills/xxx` → `data/skills/xxx`），越界自动拒绝；skills
路径需用 `relative_to(DATA_DIR)` 转成虚拟路径。回归见 `test_factory_binds_virtual_filesystem_backend`。

**精细控制**：通过 `middleware=[FilesystemMiddleware(...)]` 替换默认实例，把模型可见
内置工具收敛为 `ls/read_file/glob/grep`（write/edit/delete/execute 移除，省 token 且
防误调用），并开启 `offload_binary_content` + 20k token evict（大文件不撑爆上下文）。
替换版会继承 permissions，并配中文工具描述（引导写操作走自研 file 工具）。
**可选**：RubricMiddleware（在线自评估达标循环）通过 `DEEPAGENTS_RUBRIC_ENABLED`
开关接入（默认关，开启后 grader 用同一网关评估并可能让 agent 再迭代一轮）。

不接的 DeepAgents 能力（调研结论）：MemoryMiddleware（自研 memory 完全覆盖且更强）、
原生 HITL interrupt_on（破坏自研 tool_call_id/SSE 契约）、AsyncSubAgentMiddleware
（强依赖 LangGraph Platform，已有自研实现）、checkpointer（与自研 session 双写，
且需改 astream 历史传递语义，风险>收益）、CompositeBackend/StoreBackend（当前无
实际消费者：skills 走磁盘、summarization 直接写 backend、自研 memory 不用 DeepAgents
store，强接会变成死代码）、excluded_tools 当安全边界（源码明示非安全机制）。

`AGENT_ENGINE` 兼容开关已移除——langgraph 是唯一引擎（`config.py` 保留
`agent_engine` 字段读取历史 env，但工厂不再分支）。编排链路：
`GatewayChatModel`（自研网关挂接）→ `create_deep_agent` → `ToolNode`（审批策略钩子
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

### Data analysis tools

Two complementary data-analysis tools (both global, default-on):
- `analyze_data` (`app/tools/data_analysis_tools.py`) — 9 preset operations
  (summary/describe/top/group/null/correlation/trend) over a JSON array, no code.
- `analyze_with_pandas` (`app/tools/dataframe_tools.py`) — **code-driven** analysis:
  the model writes Python executed in a restricted namespace with pandas/numpy/scipy
  preinstalled. Security is fail-closed: AST node allowlist, import allowlist
  (pandas/numpy/scipy/math/statistics/json/re/datetime/decimal/fractions only —
  no other installs allowed), forbidden builtins/private attributes, guarded
  `__import__`, `while True` rejected. Results via `print()` are captured; the
  `result`/`df` DataFrame can be exported to the session workspace `outputs/` as
  CSV/Excel/JSON (`export` param), downloadable via
  `GET /api/v1/agent/sessions/{sid}/outputs/{filename}`（该端点原本只放行图片，
  2026-11-26 扩展到 csv/xlsx/json/txt/md；前端 FilesPanel 与工具结果里的
  「下载」按钮都走这条带鉴权路径）。

### 用户实测反馈修复（2026-11-26，五个问题）

1. **html 产物点击报「非法文件名」**：`/outputs/{filename}` 只在 outputs/ 下找、且扩展名白名单不含 html，而模型用 `write_text_file("index.html")` 写在会话工作区**根目录**。修：白名单加 html、端点同时搜索 outputs/ 与工作区根目录（都做 resolve/relative_to 校验）。实测 37786 字节 HTML 下载 200。回归 `test_output_file_download.py` +1。
2. **html 等产物不在对话下方展示**：消息 footer 加图一形态的「查看所有产物 (N) ›」入口（只挂最后一条 assistant），点击打开侧栏产物 tab；新增 `useSessionWorkspaceOutputs` 在 runStatus 跃迁到 done 且产物签名新增时自动弹侧栏；侧栏新增 `output` tab 支持 html 内联预览（srcDoc + sandbox）、图片/csv/json/txt/md/xlsx。纯函数模块 `lib/workspaceArtifacts.ts` + `components/panel/tabs.ts`。
3. **思考结束不自动折叠**：`open={isStreaming || undefined}` 在 React 中从 true→undefined 不会移除 DOM open 属性。修：`ReasoningGroup`/`ToolGroup` 改 ref + useLayoutEffect，按 isStreaming/pending 显式写 `details.open`；4 个新测试锁定 true→false 切换。
4. **「没有自动放行档位」**：auto 档其实就是只读自动放行，只是文案含糊 + 前后台管理员判定不一致（前端 canEnterAdmin 含 operator/auditor，后端 is_admin_like 只认 admin/superadmin → 选 full 静默降级为 ask）。修：菜单文案改「自动放行（只读）」；前端统一用 `isAdmin()` = `hasCapability('user:manage')`；后端非管理员 full 降级目标从 ask 改为 auto（与默认一致）。浏览器已确认三档文案正确渲染。
5. **审批改参越权（Critical）**：改参在 LangChain schema 校验**之后**替换 kwargs，且 file 工具把 `workspace` 暴露为模型可见参数 → 审批人可改成 `workspace="/etc"` 读宿主机任意文件。修：`tools_adapter.py` 新增 `_validate_modified_arguments()`，改参执行前重跑原生 jsonschema + signature.bind，并禁止绝对路径/.. 穿越 workspace；失败按工具错误返回。4 个回归测试 `test_approval_modified_args_guard.py`。审计双留原始/改后参数、敏感参数二次确认仍是已知限制（需 schema 迁移，未做）。

### 附件上传 / 读取 / 数据分析端到端实测（2026-11-26）

HTTP + 工具层实测后发现并修复 4 个真问题：

- **前端上传不带 `session_id`**：`fileService.uploadFile()` 原先只 append `file` →
  后端落 legacy 目录、`rel_path=null` → 图片能看（走 file_path 直读）但**文档读不了**
  （`file_to_md` 以会话工作区为根，绝对 legacy 路径被拒）。已实测复现+修复：
  `uploadFile(file, onProgress, sessionId)` 在 FormData 带 session_id，
  `useChatStream` 用 `targetId`（新会话客户端生成、与 sendMessageStream 一致）透传。
  回归 `tests/fileUploadSession.test.ts` 5 例（fetch/XHR 两条路径）。
- **`analyze_data` 输出裸 `NaN`**（非法 JSON，JS `JSON.parse` 直接失败）：pandas
  `to_dict()` 里的 NaN/±Inf 未清洗。修：`_json_safe()` 递归归一成 null +
  `allow_nan=False`；新增 `test_data_analysis_tools.py`（此前该工具零覆盖）。
- **导出文件无下载端点**：`/outputs/{filename}` 正则只放图片，CSV/XLSX/JSON 全 400。
  修：扩展扩展名白名单 + 正确 media_type + `Content-Disposition`（图片 inline、
  其余 attachment）；前端 FilesPanel 与 `ToolResultPreview` 都加下载按钮。
  回归 `test_output_file_download.py`。
- **上传边界实测结论**：11MB→413、路径穿越文件名净化为 basename、空文件接受、
  无 session_id 落 legacy（修复后前端总会带）、无格式白名单（probe 端点独立于 upload）。
  图片视觉输入只看扩展名不看魔数（fake.png 能上传但视觉网关会失败）——已知限制。

### Permission matrix（统一权限系统）

权限系统是「角色 × 权限点矩阵 + 三层落地」（主流 SaaS 形态），`app/core/roles.py` 的
5 角色 / 14 capability 是粗粒度分组，`app/core/permission_catalog.py` 定义 40 个细粒度
权限点（`资源:动作`，如 `user:create` / `kb:delete` / `ppt:export`）：

- **存储**：`RoleModel.permissions_json`（角色自定义权限点；null = 用内置角色默认展开）+ `UserRoleModel`（用户 ↔ 角色多对多，支持多角色并集；`users.role` 保留为主角色兼容存量）
- **判定**：`app/services/permission_checker.py` 是唯一运行时入口（`permissions_for_user` / `has_permission` / `can_enter_admin_by_permissions`）；`deps.require_perm(point)` 给端点用；Casbin 退守 KB 行级 ACL（各司其职，不再双轨割裂）
- **API**：`/api/v1/permission-matrix/{catalog,roles,roles/{slug},users/{id}/roles,me}`，管理员可勾选角色权限点、给用户分配额外角色、一键恢复角色默认
- **三层落地**：路由（can_enter_admin 后端统一下发）→ 按钮（前端 `usePermission` hook + `<Permission>` 组件）→ 后端（`require_perm` 兜底；前端隐藏只是体验）
- **下发**：登录响应与 `/auth/me` 都带 `permissions[]` + `can_enter_admin`（`UserPublic`），前端不再自己重算口径；旧缓存兜底收紧为按角色的明确能力表
- **迁移**：0029_permission_matrix（permissions_json 列 + user_roles 表，幂等）、0030_drop_kb_team（删除 KB team_id 字段，组织模型下线）
- **全站统一**：所有 API 端点零 `require_admin`，全部改走 `require_perm(权限点)`；team 共享字段已物理删除（scope 仅 org/personal）
- **前端形态**：权限树（分组可折叠 + 组级全选 + 单次批量 PUT）在「权限管理 → 权限矩阵」；角色创作与用户分配分离（用户管理页「多角色分配」用 `UserRoleAssignPanel`）
- **刷新后工具/思考恢复（DeepAgents 迁移回归修复）**：① `_sync_context` 把 LC AIMessage → NativeAIMessage 时漏复制 `additional_kwargs["reasoning_content"]`，导致思考从未落库（实时 SSE 正常掩盖了写入端 bug）——已补；② `_has_visible_body` 漏判 `tool_calls`，导致空正文的纯工具轮 assistant 被 GET /messages 过滤——已补；③ ToolMessage 落库补 `metadata.tool_outcome`，刷新后失败工具不再"变绿"。回归见 `test_langgraph_engine.py`。
- **智能体/知识库排查修复**：AgentEditor 的 audience ACL 只在主动改动时提交（避免清空名单）；编辑加载失败明确报错并禁用保存（避免空值覆盖）；MCP/外部系统绑定端点补资源归属校验（防越权改他人智能体）；全局配置端点权限点从 agent:edit 改为 tool:configure/provider:manage（防提权）；知识库 restricted 可见性收紧、删除后失效检索缓存、成员移除同步撤销 Casbin 策略、列表分页生效、上传 30MB 限制、无向量时 reindex 仍补切片；上传格式白名单三端统一。
- **消息存储结构化（阶段一）**：`agent_messages` 从单一 JSON blob 改为结构化列（message_id / role / content_text / tool_calls_json / reasoning_text / metadata_json / status 等），message_json 灰度保留；迁移 0031 回填全部存量（447 条工具调用 / 259 条思考）。写路径双写、读路径结构化优先 + JSON 回退，解决「json 不合理、扫 blob 查不了」。
- **LangGraph checkpointer（阶段 2A）**：create_deep_agent 接 checkpointer，thread_id=session_id；测试环境（多 event loop）用 InMemorySaver，生产单 loop 用 AsyncSqliteSaver（data/checkpoints.sqlite，sqlite 版不支持 async 会直接报 NotImplementedError，aiosqlite 依赖已加）。图与 checkpointer 按 event loop 惰性构建。2A 保持每轮传全量历史、自研 session 仍是产品历史源，checkpointer 只做执行状态持久化（HITL/恢复/time-travel）。2B（增量历史）评估后**未切换**：2A 已拿到核心收益，切换需重写压缩/工具配对修复为 RemoveMessage/Overwrite，风险 > 收益；实测两轮对话消息无重复（ID 去重正常）。
- **权限矩阵假开关修复**：7 个原本无消费方的权限点全部接入——KB 类通过 `require_kb_access(permission_point=...)` 参与行级判定（全局点放行 + 资源归属并存，不破坏普通用户自管）；`agent:delete` 走 require_perm + 服务层归属校验；`agent:publish` 纳入 user:manage 分组并参与上架校验。
- **知识库编译可恢复**：失败时写 `error_message`（含原因），新增 `POST /bases/{kb_id}/documents/{doc_id}/recompile`（需 kb:upload），前端文档列表显示失败原因 + 一键重试。
- **智能体配置完整性**：MCP 工具提示文案改为真实语义；还原默认补齐 visibility/audience/external_systems；版本回滚恢复 skills 绑定与 approval_sub_tools；slug 并发冲突捕获 IntegrityError 换 slug 重试；Skill 绑定拒绝已停用项；智能体可绑定知识库白名单（agent_profiles.knowledge_base_ids_json，知识库工具按会话 profile 取交集过滤）；公开会话用发布者身份检索知识库。
- **计划模式（先规划后执行）**：`plan_mode` 经前端开关 → service → runtime_profile → orchestrator（追加 PLAN_MODE_PROMPT_SUFFIX）+ factory（工具过滤）全链路打通。修复了两个真 bug：① 工具过滤原先只作用于 builtin 插件，app/tools/*.py（发邮件/部署/生图/写文件）与 MCP 工具仍注册 —— 现在注册表构建后按只读白名单统一过滤（实测计划模式仅剩 4 个只读工具）；② 原先"批准后才动手"是空承诺 —— 现在计划输出后前端显示「批准并执行」按钮，点击后关闭计划模式并把计划文本回灌模型执行。
- **刷新后气泡分裂修复**：后端把 ReAct 每一轮 LLM 步骤各存一条 assistant（先给正文、中间轮发起工具、最后一轮再给正文），实时流式时所有 delta 累积到一条消息所以只显示一个气泡；历史映射此前只合并「空壳」行、最后一条有正文的另起气泡 → 刷新后分裂成两个。`backendMessageMapper` 改为以 user 消息为轮次分界，同一轮后续 assistant 全部并入同一气泡（正文/工具/reasoning/产物/块都追加），测试断言同步更新。
- **Admin tab keep-alive**：24 个面板用 `visitedTabs` + `hidden` 保留挂载，切回不重挂载、筛选/滚动状态不丢、自管 fetch 不重复请求
- **长列表分页（全服务端）**：知识库文档/Wiki 端点用 `X-Total-Count` 响应头 + limit/offset，前端 `apiFetchPaged` 读取并配统一 `<Pagination>`；审批中心 `/admin/approvals/pending?limit&offset` 返回 `pagination` 元信息（每类 total/pages/current）。所有分页按钮统一组件，无手写上一页/下一页。
- **设计语言来源**：数据密集后台参考 [opus-frontend-arena admin-dashboard](https://github.com/Yan-Yu-Lin/opus-frontend-arena) 的模型生成作品（一手 CSS）：14px 卡片圆角 / 20px padding / 1px hairline 边框 + hover 微移；KPI 用等宽大数字（1.875rem，letter-spacing -0.02em）+ 44px 图标 chip + 顶部 hairline 分隔的副信息；动效 150/250/400ms 三档，避免 hover 放大与弹跳等"AI 味"。`usePermission` 用 `useSyncExternalStore` 订阅登录态且 snapshot 引用稳定（避免 Maximum update depth）

### 性能排查结论（2026-11-26，Rust / Go 移植评估）

全量排查 + 真实负载 profile 的结论：**没有值得移植到 Rust 或 Go 的功能**。判定依据：

- **Rust**：`fast-anything` 0.8.6 只支持把热点移植成 Rust crate（PyO3/napi-rs）。历史 profile（`.fast/profile.json`）里的热点全是假象——`score_result` self 0.294ms/96 次、`parse_transform_matrix` / `_parse_points` 是人工基准；真实检索/PPT 转换里这些函数占 <1%，且底层已经是 C/Rust 原生库（ONNX Runtime、numpy、jieba C 扩展、lxml）。
- **Go**：14 个候选组件按 A（网关/SSE）、B（限流/队列）、C（解析/生成）、D（工具/CLI）四类逐一评估——A/B/D 全是 IO 等待（LLM 上游、Redis、用户决策、子进程、IMAP），Go 的调度器优势兑现不了；C 里唯一真纯 Python CPU 热点是 PPT SVG→PPTX 管线（约 20k 行），但它已经在 `asyncio.to_thread` 里、不在首 token 关键路径，重写要复刻 python-pptx + 设计规则体系。小函数（jieba 14μs/次、score_result 3μs/次）的单次本地 IPC 成本（0.1–1ms）比计算本身大 10–100 倍，**完全吞掉收益**。所有候选都与权限/审计/配置深度耦合，进程化必然导致规则跨语言双写。
- **唯一条件性例外**：未来若出现「大规模 PPT 转换 API + 明确 p99 SLA + 高 QPS」的新产品形态，可把 `drawingml_paths.py`（svg path → DrawingML path 纯计算）做成 Go worker，Unix socket + 文件句柄传递。当前三前提（真实 profile 证明占主导 / 接受复刻 python-pptx / 不碰权限审计）一个都不满足。
- **性能优化的正确方向**（已实施）：① 修重复计算（KB 检索 4 次 → 2 次）；② 同步 IO 移出事件循环（配额/限流/借号/图片读/邮件）；③ 修正确性问题（usage 双键名 + 只下发一次，sticky usage 曾造成重复计费）；④ 缓存键正确性（pgvector 按方言+URL、embedding 含端点/维度）。热查询 11–33ms → 8–10ms；剩余首查 ~760ms 是一次性模型/索引加载。

### 功能缺陷排查与修复（2026-11-26）

四路并行只读排查（后端逻辑 / 前端交互 / 数据一致性 / 安全 HITL）发现的问题与修复：

- **Critical（已修）**：
  - **子代理绕过 HITL**：DeepAgents SubAgentMiddleware 用独立 middleware 栈，不共享主 agent 的 `EngineApprovalPolicy`、无前端审批通道。`_native_tools_for()` 原样把 `run_python_script`/`git_add`/`write_text_file` 交给子代理 → 提示注入可借 `task()` 零审批执行任意脚本。修：子代理只暴露 `execution.side_effect=False 且 requires_approval=False` 的只读工具；内置 workspace helper 拒绝绝对路径（`workspace="/"` 越权根）。回归 `test_subagent_readonly_boundary.py`。
  - **`analyze_with_pandas` AST 沙箱越界**（实测）：`pd.read_csv("/etc/hosts")` 只暴露普通属性通过校验；`'{0.__class__...}'.format(1)` 把属性藏在字符串常量绕过私有属性检查。修：禁止 pandas/numpy 的 `read_*/to_*` IO 接口、禁止 format/f-string 中的属性表达式。回归 `test_dataframe_tools.py` 新增向量。
- **High（已修）**：权限矩阵端点缺「不得改自己角色 / 不得提权」约束；`queue_stats` 双重 except 死代码；作品发布 IDOR + `source_ref` 路径穿越；默认图片工具与外部系统 HTTP 缺 SSRF 校验；`dashboard` 等静态 capability 门绕过矩阵收权；`session_storage` 读回时 status 覆盖 `metadata.tool_outcome` 导致失败工具刷新后变绿；MySQL 结构化列 `TEXT` vs `LONGTEXT` 漂移（新增 0033 迁移）；多 skill zip 安装搬错目录；skill 文件系统/DB 双向漂移；website 发布半状态。
- **Medium（已修）**：PDF 预览 SVG 正则净化可绕过（实体编码 / `<use xlink:href>`）→ 改 lxml 元素/属性白名单 + CSP；401 跳转丢重定向目标；`apiFetchPaged` 超时抛裸 AbortError；删除会话失败回滚不恢复选中态；KB 白名单在 create/update/restore/rollback 四处行为不一致。
- **前端 High（已修）**：artifact 恢复 ref 异步分支未赋值导致每帧回源；全局停止按钮停错会话；`pendingDecisions` 流结束后不清空；上一轮流 finally 清掉同会话新流状态；后端会话列表加载重置新建会话 ID；`handleSend` useCallback 缺 `planMode`/`visualStyle` 依赖。

排查结论：SQL 注入、JWT 算法混淆、zip slip、任意文件读写、审批决策伪造、DeepAgents 内置写工具越界均未发现（已有防护）。

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
- **AI 回复渲染（2026-11-26 调研改造）**：借鉴 Claude Desktop 逆向 CSS 的**数值纪律**（字号 14.5/1.65、68ch 度量、字级 ≥1.25×、120–200ms 动效、圆角 8/12/16）而非其品牌色与弹性曲线；参考 ChatGPT 的流式 caret（CSS `steps(2)` 闪烁，跟随 currentColor）、Cursor 的工具调用默认折叠、Perplexity 的层级用亮度差。落地：① `.prose` 全部走 `--surface-*`/`--foreground` token，删掉 `slate-* + .dark 反转` 双轨；② 思考块去 italic/uppercase、改灰阶等宽，流式时 `open` 强制展开 + 剥夺折叠权（避免视口跳动）、完成后收起成一行，grid 0fr↔1fr 平滑展开；③ **连续 ≥3 个同名工具折叠成 `read_file ×23` 一行**（参考 Cursor "Called X 3 times"），展开仍逐条可见——解决 20+ 工具行堆成"工具墙"；④ 代码块/表格圆角统一 12px、去顶部渐变彩条 + 大阴影、去 `active:scale-90`/`whileHover scale:1.05`；⑤ 时间戳 11px tabular-nums，流式光标统一 CSS `.stream-caret`。调研来源存于本次会话报告（Scrim UI / open-claude-ui / Vercel AI Elements / Impeccable slop）。

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

Schema evolution is two-stage on startup: `Base.metadata.create_all()` creates missing tables, then `_apply_pending_migrations()` runs alembic (`backend/alembic/versions/`, 30 migrations) — `upgrade head` if `alembic_version` exists, fresh DB replay via `upgrade head` then fallback `stamp head` (development only; production re-raises and blocks startup); migration failure logs but does not block startup in dev. The baseline migration must be kept in sync with `models.py` by hand (see `baseline_20260930.py`). `seed_tool_configs()` and `seed_agent_profiles()` run on every startup (idempotent upserts). The first registered user automatically becomes admin.

### Tests

Backend tests use pytest with `httpx` for async HTTP testing. The pytest config sets `pythonpath = ["."]` so tests can import directly from `app.*`. Run with `uv run pytest`. Current baseline: **1583 passed / 23 skipped, 0 failed**（workflow 下线后 81 个 workflow 测试随模块删除；2026-11-26 性能 / 功能缺陷 / 附件数据分析 / 产物展示排查累计新增 80+ 回归测试）. CI database matrix honors explicit `DATABASE_URL` so PG/MySQL jobs actually run against those dialects.

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
- `AGENT_MAX_STEPS` — max tool-calling steps per run (default: 30)
- `AGENT_PARALLEL_TOOL_CALLS` — enable parallel tool execution (default: false)
- `ASYNC_SUB_AGENTS_ENABLED` — enable async sub-agent middleware (default: true)
- `AGENT_BUDGET_MAX_TOKENS` / `AGENT_BUDGET_MAX_COST_USD` / `AGENT_BUDGET_ON_EXHAUSTED` —
  run-level budget circuit breaker（native `check_budget`，非 middleware）.
  Hard cap raises `BudgetExhausted`, surfaced as an SSE `error` event
  (`error_type=BudgetExhausted`); soft cap (80%) logs a warning
- `KNOWLEDGE_VECTOR_ENABLED` / `KNOWLEDGE_EMBEDDING_*` — 向量检索通道与 embedding 模型。
  本地开发已启用本地向量：fastembed + `BAAI/bge-small-zh-v1.5`（512 维，ONNX，
  零 API 成本），配 `KNOWLEDGE_EMBEDDING_LOCAL_MODEL` / `..._LOCAL_DIMENSIONS`；
  `local_embedder.py` 优先 fastembed、回退 sentence-transformers。下载需
  `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`（Xet 在本机 SSL 超时）。
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
