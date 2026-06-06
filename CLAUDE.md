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

### Backend (FastAPI + wuwei >=3.0.2)

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
          files.py, memory.py, suggest.py, website.py
    tools/
      email_tools.py               # IMAP/SMTP email tools
    services/
      agent_service.py             # core orchestrator — creates wuwei Agent, manages SSE streaming,
                                   #   approval integration, usage recording, PPT artifact extraction,
                                   #   LenientHitlMiddleware, ThinkingHistoryCompatibilityMiddleware,
                                   #   SkillInstructionMiddleware, AsyncSubAgentMiddleware,
                                   #   concurrent tool execution (monkey-patched AgentRunner)
      multi_agent_graph_service.py # MultiAgentGraph leader-worker parallel orchestration
      agent_profile_service.py     # profile CRUD, built-in default profiles, runtime resolution
      skill_service.py             # skill CRUD, zip upload, filesystem management
      approval_manager.py          # HITL approval workflow with futures and subscriber broadcast
      tool_config_service.py       # tool catalog with per-mode defaults, sub-tool approval
      session_storage.py           # DB-backed wuwei storage (sessions, messages)
      ppt_artifact_service.py      # parses pptdeck code blocks, delegates to ppt/ templates for HTML
      ppt/                         # PPT multi-template system
        base_template.py           # BaseTemplate class with Tailwind HTML rendering
        registry.py                # template registry with alias support, 10 allowed slide types
        templates/                 # 5 visual styles: executive, product, minimal, creative, academic
      auth_service.py              # registration, login, session management, rate limiting
      cache_service.py             # Redis-backed cache with history loading from DB
      memory_service.py            # agent memory management
      multi_agent_ppt_service.py   # multi-agent PPT generation
      external_system_service.py   # external system integrations
      website_deploy_service.py    # website deployment
      announcement_service.py      # announcement CRUD
      design_system.py             # design system utilities
    prompts.py                     # system prompts for agent modes
  examples/
    run_all_examples.py            # combined test for all 3 wuwei features
    test_async_sub_agent.py        # AsyncSubAgent background tasks
    test_multi_agent_graph.py      # MultiAgentGraph leader-worker
    test_concurrent_tools.py       # concurrent tool execution
```

The wuwei framework (>=3.0.2) provides `Agent`, `LLMGateway`, `ToolRegistry`, `SkillManager`, and a middleware stack (`HitlMiddleware`, `ContextCompressionMiddleware`, `LoggingMiddleware`, `TracingMiddleware`). The backend wraps these with FastAPI endpoints, custom middlewares, and database persistence.

### Agent modes & middleware

| Mode | Default tools | Behavior summary |
|------|--------------|-----------------|
| `general` | calc, time, file (approval required) | Daily Q&A, lightweight tool use |
| `ppt` | calc only | Structured presentation generation via `pptdeck` code blocks, 5 visual themes, 10 slide types |
| `website` | calc, time, file, npm | Web/frontend development mode |
| `email` | calc, time, skill | Email management via IMAP/SMTP |

Custom middlewares in agent_service.py:
- `LenientHitlMiddleware` — extends wuwei's HitlMiddleware with lenient approval logic
- `ThinkingHistoryCompatibilityMiddleware` — filters synthetic assistant replies for provider thinking-mode
- `SkillInstructionMiddleware` — injects skill instructions into agent context
- `AsyncSubAgentMiddleware` — enables background async sub-agent tasks (code_analyst, file_processor)

Concurrent tool execution: `AgentRunner.stream_events` is monkey-patched to batch safe tools (`is_concurrency_safe=True`) via `asyncio.gather`. Unsafe tools remain sequential. Transparent to frontend SSE events.

### Multi-Agent Graph

`multi_agent_graph_service.py` wraps wuwei's `MultiAgentGraph` for leader-worker parallel orchestration. Leader decomposes tasks, workers (researcher/writer/reviewer) execute in parallel via `asyncio.gather`, leader synthesizes results. Available via `get_multi_agent_graph_service().run(task)`.

### Async Sub-Agents

`AsyncSubAgentMiddleware` in agent_service.py injects 4 tools: `start_async_task`, `check_async_task`, `cancel_async_task`, `list_async_tasks`. Two built-in sub-agents: `code_analyst` (Python/calc/git) and `file_processor` (file read/write/search). Controlled by `ASYNC_SUB_AGENTS_ENABLED` env var.

### PPT multi-template system

PPT generation lives in `services/ppt/` with a template registry pattern:

- **`registry.py`**: Decorator-based `@register("name")` pattern with alias support. `get_or_default(name)` falls back to `executive`.
- **`base_template.py`**: `BaseTemplate` abstract class — each template defines CSS variables, slide type renderers, and a `render_html()` method using Tailwind utility classes.
- **5 templates**: `executive` (corporate), `product` (gradient + glassmorphism), `minimal` (magazine), `creative` (colorful blocks), `academic` (grid + breadcrumbs).
- **10 slide types**: `cover`, `section`, `bullets`, `stats`, `chart`, `comparison`, `timeline`, `quote`, `imageText`, `closing`.

### Sub-tool approval

Per-tool approval supports sub-tool granularity. `TOOL_CATALOG` in `tool_config_service.py` defines `sub_tools` per tool. The admin UI can toggle approval per sub-tool, stored in `approval_sub_tools_json` column. Empty list = all sub-tools require approval (backward compatible).

### HITL approval flow

When an agent invokes a tool that requires approval:
1. `LenientHitlMiddleware` triggers `ApprovalManager.request_approval()`, persists to `agent_approvals` table
2. Frontend receives `approval_required` SSE event (includes sub-tool info), shows `PendingApprovalPanel`
3. User approves/rejects → `POST /api/v1/agent/approvals/{id}/decision`
4. Future is resolved, agent proceeds or aborts; timeout after `HITL_TIMEOUT_SECONDS` (default 300s)

### SSE streaming protocol

`POST /api/v1/agent/stream` returns a stream of JSON events (one per line). Event types:

| Event | Meaning |
|-------|---------|
| `session` | Session metadata on connect |
| `run_status` | Phase changes: `thinking` → `streaming` / `generating_ppt` / `rendering_ppt` → `done` |
| `delta` | LLM text token streaming |
| `reasoning_delta` | LLM reasoning/thinking token streaming |
| `tool_calls` | Tool call initiated |
| `tool_results` | Tool call completed |
| `approval_required` | Tool call needs human approval |
| `artifact_ready` | PPT mode only: deck JSON with rendered HTML |
| `done` | Normal completion with usage stats |
| `error` | Fatal error with optional usage stats |

### Context compression

When `context_compression_enabled` is true (default), `ContextCompressionMiddleware` triggers after `context_compress_after_turns` (default 16) turns. It uses the LLM itself to summarize conversation history, keeping the most recent `context_keep_recent_turns` (default 6) turns intact.

### Frontend design system

Tailwind 4 + custom `@theme` tokens in `src/index.css`. Key conventions:
- **Brand color** `#2b87c2` (desaturated sky) — used sparingly: primary CTA and focus states only. Secondary interactions use slate.
- **Font weights**: `font-medium`(500) / `font-semibold`(600). No `font-bold`(700) or `font-black`(900).
- **Border radius**: `rounded-md`(8px) for buttons/inputs, `rounded-lg`(12px) for cards, `rounded-xl`(16px) for modals.
- **Shadows**: Dual-layer system (`shadow-sm` through `shadow-xl`). Each level uses two stacked box-shadows for realistic depth.
- **Surfaces**: `--surface-0: #f4f6f8` (page bg) → `--surface-1: #ffffff` (cards/panels). Cards use `border-slate-200/80` + `shadow-sm`, with `hover:border-slate-300 hover:shadow-md`.
- **Glass**: `backdrop-blur` only on sidebar and modal overlays. Not on cards, inputs, or scrolling content.
- **Micro-interactions**: `active:scale-[0.98]` on buttons, `transition-all duration-150` on interactive elements.
- **Admin**: Unified style with chat (same tokens). No separate admin color scheme.

### Frontend (React 19 + TypeScript + Tailwind 4 + Vite)

```
frontend/src/
  App.tsx                          # BrowserRouter, lazy-loaded routes
  pages/
    Chat.tsx                       # main chat page, orchestrates hooks and layout
    Home.tsx, AgentStore.tsx, Login.tsx, Signup.tsx, AdminDashboard.tsx
  components/
    chat/                          # ChatMainArea, ChatInput, ChatMessage, ChatTimeline,
                                   # Sidebar, ArtifactPanel, PendingApprovalPanel,
                                   # MessagesList, ChatSearch, ChatSuggestions,
                                   # DecisionPanel, EmailSettingsPanel, IntegrationMarket
    admin/                         # AdminSidebar, DashboardCharts, DashboardStats,
                                   #   UserManagement, AgentManagement, SkillManagement
    ppt/                           # PptArtifactPanel
    auth/                          # ProtectedRoute
    settings/                      # Settings panels
    website/                       # Website-related components
    ui/                            # Badge, Button, Card, EmptyState, Input, Modal,
                                   # Skeleton, Toast, Tooltip, AnimatedIcons, MascotIcons
  hooks/
    useChatStream.ts               # SSE client + approval decisions
    useChatSessions.ts             # localStorage session cache (max 24 sessions)
    useChatScroll.ts, useChatSearch.ts, useDragAndDrop.ts
    useInputSuggest.ts             # input suggestions
    useTheme.ts                    # theme management
    useConfirm.tsx                 # confirmation dialog
  services/
    agentService.ts                # SSE client + approval decisions
    authService.ts, agentProfileService.ts, skillService.ts,
    dashboardService.ts, toolConfigService.ts, userService.ts,
    conversationService.ts, configService.ts,
    announcementService.ts, emailService.ts, fileService.ts,
    integrationService.ts, memoryService.ts, websiteService.ts
  lib/
    utils.ts                       # cn() classname helper (clsx + tailwind-merge)
    safePreview.ts                 # safe HTML preview rendering
    datetime.ts                    # date formatting utilities
```

Routes: `/` (Home), `/chat` (Chat, protected), `/agents` (AgentStore, protected), `/login`, `/signup`, `/admin` (AdminDashboard, admin-only).

**Session persistence**: Chat sessions are cached in localStorage via `useChatSessions` hook (max 24 sessions, 80 messages each, with text truncation). This provides instant reload on page refresh while the backend remains the source of truth.

Vite config: `@` path alias resolves to `frontend/src`. Production build splits vendor chunks: `react-core`, `motion-vendor`, `markdown-vendor`, `admin-vendor`.

### Database

Default SQLite at `./data/agenticos.db`. Configurable to MySQL via `DATABASE_URL`. Tables: users, auth_sessions, auth_rate_limits, agent_sessions, agent_messages, agent_usage_events, agent_tool_configs, agent_profiles, agent_profile_tools, skills, agent_profile_skills, user_installed_agents, approvals, ppt_artifacts, user_email_credentials, announcements, external_systems, memory entries.

Schema is auto-created via `Base.metadata.create_all()` on startup. A compat layer (`_ensure_compatible_schema()`) adds missing columns with ALTER TABLE for forward-compatibility. `seed_tool_configs()` and `seed_agent_profiles()` run on every startup (idempotent upserts). The first registered user automatically becomes admin.

### Tests

Backend tests (14+ files in `backend/tests/`) use pytest with `httpx` for async HTTP testing. The pytest config sets `pythonpath = ["."]` so tests can import directly from `app.*`.

Tests cover: auth, agent stream, tool config, users, dashboard, skills, agent profiles, agent service, website mode defaults, local skill import, health, SVG to PPTX, theme token resolver, new modules.

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

See `backend/.env.example` for the full list.

## Notes

- All datetime fields use `AppDateTime` type decorator for timezone-aware handling (default: `APP_TIMEZONE`)
- Backend changes working directory to project root on startup so wuwei file tools resolve paths correctly
- Redis is optional — leave `REDIS_URL` empty for in-memory fallback during development
