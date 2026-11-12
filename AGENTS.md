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
npm run lint                               # TypeScript type-check (tsc --noEmit)
```

The Vite dev server proxies `/api` to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8001`). Set `DISABLE_HMR=true` to disable HMR if needed.

**Docker**: `cd deploy && docker compose up -d --build` deploys both services. Backend on :8001, frontend served by nginx on :3001 (proxies `/api` to backend).

## Architecture

### Backend (FastAPI + wuwei >=3.4.1)

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
      security.py                  # password hashing (PBKDF2) + JWT tokens (HS256)
      redis.py                     # Redis connection manager (single/cluster), in-memory fallback
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
        # settings.py: GET/PUT /settings/ldap + POST /settings/ldap/test —
        #   通用 LDAP 集成（协议级 ldap3），服务器/绑定账号/过滤器/属性映射
        #   全部存 system_settings（ldap.* 键），管理员后台配置与连接测试
        # api_keys.py: 用户级 API Key（表 api_keys，供 OpenAI 兼容网关鉴权）
        # gateway_v1.py（挂载 /v1/models、/v1/chat/completions）：本地智能体
        #   的 OpenAI 兼容出口，仅走本地 LLM 配置，无上游透传
    tools/
      email_tools.py               # IMAP/SMTP email tools
    services/
      agent/                       # core orchestrator package (agent_service.py is a 58-line
                                   #   facade re-exporting this package; keep new code here)
        service.py                 # AgentService = AgentFactory + StreamOrchestrator + ArtifactFactory (mixins)
        orchestrator.py            # StreamOrchestrator — SSE event mapping, event pump
                                   #   (approval / user-input / api-approval / decision queues),
                                   #   usage recording, session persistence, keepalive
        factory.py                 # AgentFactory — middleware stack (9 layers), tool registration,
                                   #   LenientHitlMiddleware / ThinkingHistoryCompatibilityMiddleware /
                                   #   SkillInstructionMiddleware / AsyncSubAgentMiddleware assembly
        wuwei_patches.py           # boundary patches for wuwei residual defects (docs/upstream/
                                   #   wuwei-3.0.2-问题清单.md R-list) — minimal-override discipline,
                                   #   degrade-safe, regression-tested in test_wuwei_patches.py
        artifacts.py, compression.py, prompts.py
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
                                   #   (used by both ApprovalManager and InteractionBroker)
      tool_config_service.py       # tool catalog with per-mode defaults, sub-tool approval
      session_storage.py           # DB-backed wuwei storage (sessions, messages)
      ppt_artifact_service.py      # assembles the SVG deck artifact from save_slide /
                                   #   save_slides_batch tool outputs (XML sanitize, finalize hook)
      ppt/                         # PPT SVG pipeline: svg_layouts / svg_quality_checker(+checkers/)
                                   #   svg_position_calculator / theme_token_resolver (brand design
                                   #   themes from data/design-systems) / svg_finalize / svg_to_pptx
                                   #   (native .pptx export) / pptx_to_svg / template_import /
                                   #   svg_editor / image_backends / anti_slop_checker / design_craft
      ppt_pipeline.py              # alternative StateGraph-orchestrated PPT flow
      auth_service.py              # registration, login, session management, rate limiting
      rate_limiter.py              # Redis fixed-window rate limiting (auth + agent stream)
      cache_service.py             # Redis-backed cache (input suggestions, presence, approval queues)
      memory_service.py            # agent memory management
      multi_agent_ppt_service.py   # multi-agent PPT generation
      external_system_service.py   # external system integrations (+ external_systems/ coordinators)
      website_deploy_service.py    # website deployment
      announcement_service.py      # announcement CRUD
      workflow/                    # workflow engine v1 (P0-3): node graph DSL + runner
        engine.py                  # pure computation: graph validation, scheduler,
                                   #   {{inputs.x}} / {{nodes.<id>.output}} variable
                                   #   resolution (restricted dotted-path lookup, no eval)
        nodes.py                   # built-in handlers: llm / knowledge / http (SSRF
                                   #   guarded, redirects off) / template / start
        service.py                 # DB orchestration: per-step persistence,
                                   #   human_input pause/resume (DB is the only
                                   #   source of truth; resume survives restart)
    prompts.py                     # system prompts for agent modes
  examples/
    run_all_examples.py            # combined test for 2 wuwei features
    test_async_sub_agent.py        # AsyncSubAgent background tasks
    test_concurrent_tools.py       # concurrent tool execution
```

The wuwei framework (>=3.4.1) provides `Agent`, `LLMGateway`, `ToolRegistry`, `SkillManager`, and a middleware stack (`HitlMiddleware`, `ContextCompressionMiddleware`, `LoggingMiddleware`, `TracingMiddleware`). The backend wraps these with FastAPI endpoints, custom middlewares, and database persistence. Where wuwei still has residual defects, `services/agent/wuwei_patches.py` and `services/llm_providers/adapter.py` apply boundary patches (never edit `site-packages`); the full defect ledger and patch status live in `docs/upstream/wuwei-3.0.2-问题清单.md`.

### Agent modes & middleware

| Mode | Default tools | Behavior summary |
|------|--------------|-----------------|
| `general` | calc, time, file (approval required) | Daily Q&A, lightweight tool use |
| `ppt` | SVG slide tools (`save_slide` / `save_slides_batch`, quality & theme tools) | Structured presentation generation — agent writes SVG slides, backend pipeline exports native .pptx |
| `website` | calc, time, file, npm | Web/frontend development mode |
| `office` | Univer document/sheet tools | Office document & spreadsheet editing (Univer integration) |
| `email` | calc, time, skill | Email management via IMAP/SMTP |

Custom middlewares in `services/agent/factory.py`:
- `LenientHitlMiddleware` — session-level three-tier approval (`ask`/`auto`/`full`), lenient rejection (rejection becomes a message the LLM can react to, not an exception)
- `ThinkingHistoryCompatibilityMiddleware` — filters synthetic assistant replies for provider thinking-mode
- `SkillInstructionMiddleware` — injects skill instructions into agent context
- `AsyncSubAgentMiddleware` — enables background async sub-agent tasks (code_analyst, file_processor)

Concurrent tool execution: batching is upstream-native — `ToolExecutor.execute(concurrent=True)` runs tools with `is_concurrency_safe=True` concurrently and keeps unsafe tools sequential. Because upstream silently disables batching whenever any `before_tool`/`after_tool` hook exists (R-7), the stack wraps the executor in `BoundedToolExecutor` + `BatchSafeMiddlewareProxy` (`wuwei_patches.py`) so approval hooks coexist with concurrency: bounded by a semaphore, write-like tools forced serial, repeated identical tool calls detected. Still transparent to frontend SSE events, and gated by `AGENT_PARALLEL_TOOL_CALLS`.

### Async Sub-Agents

`AsyncSubAgentMiddleware` in `services/agent/factory.py` injects 4 tools: `start_async_task`, `check_async_task`, `cancel_async_task`, `list_async_tasks`. Two built-in sub-agents: `code_analyst` (Python/calc/git) and `file_processor` (file read/write/search). Controlled by `ASYNC_SUB_AGENTS_ENABLED` env var.

### PPT SVG pipeline

PPT generation is SVG-first — the agent writes slides as SVG, the backend converts to native .pptx:

- **Agent side** (`prompts.py` PPT_SYSTEM_PROMPT + `tools/ppt_tools.py`): the model must call `save_slide` / `save_slides_batch` (never emit SVG in chat). SVG uses `viewBox="0 0 1280 720"`, colors only via `var(--token)` referencing an injected brand design theme; forbidden constructs: `<style>`, `<foreignObject>`, `<mask>`, `<animate>`, `class`, `rgba()`.
- **Themes**: `services/ppt/theme_token_resolver.py` maps theme names (apple, github, stripe, government_blue…) to CSS token sets generated from `data/design-systems/`; frontend fetches the list via `GET /api/v1/agent/ppt/themes`.
- **Backend pipeline** (`services/ppt/`): XML sanitizing (`ppt_artifact_service.py`) → `svg_finalize` (image embed/crop/repair, `image_backends/` + `image_search.py`) → `svg_quality_checker` + `checkers/` + `anti_slop_checker` / `design_craft` (layout diversity, anti-uniformity rules) → `svg_to_pptx/` (DrawingML conversion, native editable .pptx) → `svg_to_pptx/pptx_cli.py`.
- **pptx_to_svg/**: reverse direction (import an existing .pptx into the editor pipeline, `svg_editor/server.py`).
- **template_import/**: manifest-driven theme/template import.
- An alternative fully-orchestrated flow exists in `ppt_pipeline.py` (wuwei StateGraph) and `multi_agent_ppt_service.py`; the chat-mode default is the tool-driven path above.

### Sub-tool approval

Per-tool approval supports sub-tool granularity. `TOOL_CATALOG` in `tool_config_service.py` defines `sub_tools` per tool. The admin UI can toggle approval per sub-tool, stored in `approval_sub_tools_json` column. Empty list = all sub-tools require approval (backward compatible).

### HITL approval flow

When an agent invokes a tool that requires approval:
1. `LenientHitlMiddleware` triggers `ApprovalManager.request_approval()`, persists to `agent_approvals` table
2. Frontend receives `approval_required` SSE event (includes sub-tool info), shows `PendingApprovalPanel`
3. User approves/rejects → `POST /api/v1/agent/approvals/{id}/decision`
4. Future is resolved, agent proceeds or aborts; timeout after `HITL_TIMEOUT_SECONDS` (default 300s)

### Workflow engine v1 (P0-3)

`app/services/workflow/` — admin-defined node workflows (Dify-Workflow style), stored as JSON DSL in `workflows` table, executed by `WorkflowExecutor`:

- **8 node types**: `start / llm / knowledge / http / template / condition / human_input / end`. Condition branching, **parallel fan-out/fan-in** (ready batch runs via `asyncio.gather`; joins wait for all in-edge sources), and a human-input **barrier** (it defers until every other node is terminal). Loops are rejected by validation (cycle check).
- **Variables**: `{{inputs.x}}` and `{{nodes.<id>.output}}` resolved by restricted dotted-path lookup (no eval). A template that is exactly one variable returns the raw value (type-preserving); mixed text substitutes stringified.
- **Endpoints** (`/api/v1/workflows`): CRUD admin-only; run for any logged-in user on **enabled** workflows. **Async**: `POST /{id}/run` and `POST /workflows/runs/{id}/resume` create a `running` row and execute in a background task (poll `GET /workflows/runs/{id}` to terminal); restart reaps `running` rows via `startup_cleanup` (`waiting_input` survives — pause state is DB-persisted). Run records visible to trigger or admin; the `WHERE status='waiting_input'` claim prevents double resume. The **agent tool bridge executes inline** (`service.start_run`) because the model needs the final result; its tool timeout is set above the workflow run timeout so the engine's graceful timeout wins.
- **Security**: http node passes `intranet_policy.check_url` (deny-by-default without `INTRANET_ALLOWED_CIDRS`), no redirects, `Authorization`/`Cookie` headers stripped, response body capped; knowledge node reuses retrieval ACL per trigger user; llm node goes through `llm_factory` with `role="fast"`.
- **Agent tool bridge** (`app/tools/workflow_tools.py`): every **enabled**
  workflow is registered as a `run_workflow_<safe-name>_<id>` tool on the
  agent (dynamic registration like MCP, not in `TOOL_CATALOG`; disabled
  workflow = tool gone). Trigger identity flows from the session contextvar.
  **Chat-native human input**: on a `human_input` node the tool blocks on
  `UserInputBlocker` (same machinery as external systems — SSE pushes
  `user_input_required`, the chat UI renders the form, `POST
  /agent/sessions/{sid}/user-input` resolves it) and resumes the run
  inline, so the model gets the final result without a second call. Fields
  declared on the node flow through `workflow_runs.waiting_fields_json`
  (migration 0019; resume is a **snapshot** — node_status + outputs from
  steps/context JSON, order-independent, works with parallel completion).
  Without a session (direct API runs) it falls back to a `waiting_input`
  result. No tool-level timeout (waiting is unbounded by
  design; execution is bounded by the workflow's own node/run timeouts);
  `asyncio.CancelledError` marks the run failed (no zombie rows);
  `side_effect=True` forces serial execution. The `_get_agent` cache key
  includes a workflows signature (id+updated_at hash) so enable/edit
  invalidates the mounted tool set.
- **Admin UI**: `frontend/src/components/admin/WorkflowManagement.tsx`
  (list / editor / toggle via `PUT /workflows/{id}/enabled` / run /
  runs+resume). The editor has three modes: **canvas** (`WorkflowCanvas.tsx`,
  `@xyflow/react` — drag nodes, drag handles to connect, minimap, pan/zoom;
  node `position` is a display-only field the backend ignores), **form**
  (`WorkflowGraphEditor.tsx` — per-type param forms, cascade rename/delete,
  dedup edge builder, BFS SVG preview), and **JSON**. All three share the same
  pure graph functions, so behaviour is identical across modes.
  Real-browser e2e: `frontend/tests/workflow-canvas.e2e.ts`.
- **Authorization — default deny**: workflows are admin-orchestrated platform
  capability, so regular users **cannot run them until an admin grants
  `use_workflows`** (System Settings → Permissions). Gated features:
  `use_workflows` (run/resume) and `view_workflow_runs` (run records), on both
  the HTTP endpoints and the agent tool bridge (`status: denied`). Startup
  seeds `p, admin, *, feature:<name>, read` anchors
  (`DEFAULT_RESTRICTED_FEATURES`) — Casbin is allow-override, so an anchor is
  how "configured but nobody granted" is expressed. `require_feature` is
  fail-closed; `require_feature_compatible` (unknown feature ⇒ pass) exists for
  future opt-in features but workflows do **not** use it.
- **Not yet implemented** — see `docs/research/工作流后续路线.md` for the
  loop-node (subflow iteration) and ARQ multi-worker designs.

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

Note: wuwei declares `task_start` / `task_end` event types but never emits them (upstream R-17) — clients should not branch on them.

### Context compression

When `context_compression_enabled` is true (default), `ContextCompressionMiddleware` triggers after `context_compress_after_turns` (default 16) turns. It uses the LLM itself to summarize conversation history, keeping the most recent `context_keep_recent_turns` (default 6) turns intact.

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
                                   #   rAF-batched flush, approval submissions) — wraps
                                   #   sendMessageStream from agentService
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
    agentService.ts                # THE SSE client (fetch-event-source + applyAgentEvent
                                   #   event dispatcher) + artifact/email-template APIs
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

Default SQLite at `./data/agenticos.db`. Configurable to MySQL via `DATABASE_URL`. Tables: users, auth_sessions, agent_sessions, agent_messages, agent_usage_events, agent_tool_configs, agent_profiles, agent_profile_tools, skills, agent_profile_skills, user_installed_agents, agent_approvals, ppt_artifacts, video_artifacts (legacy, mode removed), user_email_credentials, announcements, external_systems (+external_apis/params/credentials), memory entries, knowledge base tables (kb_*), workflows, workflow_runs, system_settings, agent_run_traces, api_keys, email_verification_codes.

Schema evolution is two-stage on startup: `Base.metadata.create_all()` creates missing tables, then `_apply_pending_migrations()` runs alembic (`backend/alembic/versions/`, 25 migrations) — `upgrade head` if `alembic_version` exists, `stamp head` on a fresh DB; migration failure logs but does not block startup. The baseline migration must be kept in sync with `models.py` by hand (see `baseline_20260930.py`). `seed_tool_configs()` and `seed_agent_profiles()` run on every startup (idempotent upserts). The first registered user automatically becomes admin.

### Tests

Backend tests (114 files in `backend/tests/`) use pytest with `httpx` for async HTTP testing. The pytest config sets `pythonpath = ["."]` so tests can import directly from `app.*`. Run with `uv run pytest`.

Tests cover: auth, agent stream, tool config, users, dashboard, skills, agent profiles, agent service, wuwei boundary patches (`test_wuwei_patches.py` — one case per upstream residual defect), llm providers (retry/usage contracts), workflow engine, MCP, website mode defaults, local skill import, health, SVG to PPTX, theme token resolver, artifact slug inference (website artifacts must be session-scoped — never a global "most recent dist" scan), alembic migration chain integrity.

## Key environment variables

Essential: `OPENAI_API_KEY` (LLM access), `AUTH_SECRET_KEY` (JWT signing).

Also important:
- `OPENAI_BASE_URL` — custom LLM endpoint (default: OpenAI)
- `OPENAI_MODEL` — model name (default: `gpt-5.4`)
- `DATABASE_URL` — defaults to SQLite, set to MySQL URL for production
- `REDIS_URL` — Redis connection (empty = in-memory fallback)
- `HITL_ENABLED` / `HITL_REQUIRE_APPROVAL_TOOLS` — approval workflow control
- `AGENT_MAX_STEPS` — max tool-calling steps per run (default: 10)
- `AGENT_PARALLEL_TOOL_CALLS` — enable parallel tool execution (default: false)
- `ASYNC_SUB_AGENTS_ENABLED` — enable async sub-agent middleware (default: true)
- `AGENT_BUDGET_MAX_TOKENS` / `AGENT_BUDGET_MAX_COST_USD` / `AGENT_BUDGET_ON_EXHAUSTED` —
  run-level budget circuit breaker via wuwei `BudgetMiddleware` (default: off).
  Hard cap raises `BudgetExhausted`, surfaced as an SSE `error` event
  (`error_type=BudgetExhausted`); soft cap (80%) logs a warning
- `AGENT_STREAM_RATE_LIMIT` / `AGENT_STREAM_RATE_WINDOW_SECONDS` — per-user
  fixed-window rate limit on `POST /agent/stream` (default: 30 runs / 300s,
  admins exempt, `<=0` disables; 429 + `Retry-After` on excess)
- `WORKFLOW_NODE_TIMEOUT_SECONDS` / `WORKFLOW_RUN_TIMEOUT_SECONDS` — workflow
  engine v1 per-node / whole-run execution caps (defaults 60s / 300s)
- `LDAP_ENABLED` — bootstrap switch for the DB-configured LDAP integration
  (full config managed by admins in System Settings → LDAP; stored in
  `system_settings` under `ldap.*` keys, bind password encrypted)

See `backend/.env.example` for the full list.

## Notes

- All datetime fields use `AppDateTime` type decorator for timezone-aware handling (default: `APP_TIMEZONE`)
- Backend changes working directory to project root on startup so wuwei file tools resolve paths correctly
- Redis is optional — leave `REDIS_URL` empty for in-memory fallback during development
