# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AgenticOS is a general-purpose AI agent platform with a FastAPI backend and React+Vite frontend. It supports multi-mode AI chat, configurable agent profiles, local skill storage, human-in-the-loop (HITL) approval workflows, and an admin dashboard.

## Development commands

**Backend** (requires Python >=3.13, managed with `uv`):

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

**Docker**: `docker compose up -d --build` deploys both services. Backend on :8001, frontend served by nginx on :3001 (proxies `/api` to backend).

## Architecture

### Backend (FastAPI + wuwei >=0.2.1)

```
backend/
  main.py                          # uvicorn launcher
  app/
    main.py                        # FastAPI app factory, CORS, lifespan (init_db),
                                   #   exception handlers, 32MB request size limit
    db/
      models.py                    # all SQLAlchemy ORM models (14 tables)
      session.py                   # engine, session factory, init_db
    core/
      config.py                    # Pydantic Settings — reads all env vars from .env
      security.py                  # password hashing (PBKDF2) + JWT tokens (HS256)
    api/
      router.py                    # top-level router, mounts v1 sub-router
      deps.py                      # dependency injection: get_db, get_current_user, require_admin
      v1/
        router.py                  # mounts all endpoint routers
        endpoints/
          auth.py, agent.py, agent_profiles.py, skills.py,
          dashboard.py, health.py, tool_config.py, users.py
    services/
      agent_service.py             # core orchestrator — creates wuwei Agent, manages SSE streaming,
                                   #   approval integration, usage recording, PPT artifact extraction,
                                   #   ThinkingHistoryCompatibilityHook
      agent_profile_service.py     # profile CRUD, built-in default profiles, runtime resolution
      skill_service.py             # skill CRUD, zip upload, filesystem management
      approval_manager.py          # HITL approval workflow with futures and subscriber broadcast
      tool_config_service.py       # tool catalog (7 tools) with per-mode defaults
      session_storage.py           # DB-backed wuwei storage (sessions, messages)
      ppt_artifact_service.py      # parses pptdeck code blocks, renders HTML previews
      auth_service.py              # registration, login, session management, rate limiting
      local_skill_import_service.py
    prompts.py                     # system prompts for 3 agent modes
```

The wuwei framework (>=0.2.1) provides `Agent`, `LLMGateway`, `ToolRegistry`, `SkillManager`, `HitlHook`, and `ContextCompressionHook`. The backend wraps these with FastAPI endpoints and database persistence.

### Three agent modes

| Mode | Default tools | Behavior summary |
|------|--------------|-----------------|
| `general` | calc, time, file (approval required) | Daily Q&A, lightweight tool use |
| `ppt` | calc only | Structured presentation generation via `pptdeck` code blocks |
| `website` | calc, time, file, npm | Web/frontend development mode |

### HITL approval flow

When an agent invokes a tool that requires approval:
1. `HitlHook` triggers `ApprovalManager.request_approval()`, persists to `agent_approvals` table
2. Frontend receives `approval_required` SSE event, shows `PendingApprovalPanel`
3. User approves/rejects → `POST /api/v1/agent/approvals/{id}/decision`
4. Future is resolved, agent proceeds or aborts; timeout after `HITL_TIMEOUT_SECONDS` (default 300s)

Note: approval queues are in-memory and do not survive server restart.

### SSE streaming protocol

`POST /api/v1/agent/stream` returns a stream of JSON events (one per line). Event types:

| Event | Meaning |
|-------|---------|
| `session` | Session metadata on connect (id, summary, context_compressed, last_usage, etc.) |
| `run_status` | Phase changes: `thinking` → `streaming` / `generating_ppt` / `rendering_ppt` → `done` |
| `delta` | LLM text token streaming |
| `reasoning_delta` | LLM reasoning/thinking token streaming |
| `tool_calls` | Tool call initiated (name, arguments) |
| `tool_results` | Tool call completed (status: success/error) |
| `approval_required` | Tool call needs human approval before executing |
| `artifact_ready` | PPT mode only: deck JSON with rendered HTML preview |
| `done` | Normal completion with usage stats (tokens, latency_ms, llm_calls) |
| `error` | Fatal error with optional usage stats |

### Context compression

When `context_compression_enabled` is true (default), `ContextCompressionHook` triggers after `context_compress_after_turns` (default 16) turns. It uses the LLM itself to summarize conversation history, keeping the most recent `context_keep_recent_turns` (default 6) turns intact. A `ThinkingHistoryCompatibilityHook` filters out synthetic assistant replies (like the max-steps-limit message) to keep the provider's thinking-mode history clean.

### Frontend (React 19 + TypeScript + Tailwind 4 + Vite)

```
frontend/src/
  App.tsx                          # BrowserRouter, lazy-loaded routes
  pages/
    Chat.tsx                       # main chat page, orchestrates hooks and layout
    Home.tsx, AgentStore.tsx, Login.tsx, Signup.tsx, AdminDashboard.tsx
  components/
    chat/                          # ChatMainArea, ChatArtifactArea, ChatInput, ChatMessage,
                                   # ChatTimeline, Sidebar, ArtifactPanel, PendingApprovalPanel,
                                   # MessagesList, ChatSearch, DragOverlay, ChatSuggestions
    admin/                         # AdminSidebar, DashboardCharts, DashboardStats,
                                   #   UserManagement, AgentManagement, SkillManagement, ChatHistory
    ppt/                           # PptArtifactPanel
    auth/                          # ProtectedRoute
    ui/                            # Badge, Button, Card, EmptyState, Input, MascotState,
                                   # Modal, Skeleton, Toast, Tooltip, AnimatedIcons, MascotIcons
  hooks/                           # useChatStream (SSE + approval), useChatSessions (localStorage),
                                   # useChatScroll, useDragAndDrop, useChatSearch
  services/                        # API clients for each endpoint group
    agentService.ts                # SSE client + approval decisions
    authService.ts, agentProfileService.ts, skillService.ts,
    dashboardService.ts, toolConfigService.ts, userService.ts,
    conversationService.ts, configService.ts
  constants/modePrompts.ts         # frontend-side mode-specific prompt templates
  lib/
    utils.ts                       # cn() classname helper (clsx + tailwind-merge)
    safePreview.ts                 # safe HTML preview rendering
    datetime.ts                    # date formatting utilities
```

Routes: `/` (Home), `/chat` (Chat, protected), `/agents` (AgentStore, protected), `/login`, `/signup`, `/admin` (AdminDashboard, admin-only).

**Session persistence**: Chat sessions are cached in localStorage via `useChatSessions` hook (max 24 sessions, 80 messages each, with text truncation). This provides instant reload on page refresh while the backend remains the source of truth.

Vite config: `@` path alias resolves to `frontend/`. Production build splits vendor chunks: `react-core`, `motion-vendor`, `markdown-vendor`, `admin-vendor`, `ppt-vendor`.

### Database

Default SQLite at `./data/agenticos.db`. Configurable to MySQL via `DATABASE_URL`. Tables: users, auth_sessions, auth_rate_limits, agent_sessions, agent_messages, agent_usage_events, agent_tool_configs, agent_profiles, agent_profile_tools, skills, agent_profile_skills, user_installed_agents, approvals, ppt_artifacts.

Schema is auto-created via `Base.metadata.create_all()` on startup. A compat layer (`_ensure_compatible_schema()`) adds missing columns with ALTER TABLE for forward-compatibility. `seed_tool_configs()` and `seed_agent_profiles()` run on every startup (idempotent upserts). The first registered user automatically becomes admin.

### Tests

Backend tests (11 files in `backend/tests/`) use pytest with `httpx` for async HTTP testing. The pytest config sets `pythonpath = ["."]` so tests can import directly from `app.*`.

```bash
uv run pytest                              # run all tests
uv run pytest tests/test_auth.py           # run a single test file
uv run pytest -k "test_name"               # run tests matching a pattern
```

## Key environment variables

Essential: `OPENAI_API_KEY` (LLM access), `AUTH_SECRET_KEY` (JWT signing).

Also important for configuration:
- `OPENAI_BASE_URL` — custom LLM endpoint (default: OpenAI)
- `OPENAI_MODEL` — model name (default: `gpt-5.4`)
- `DATABASE_URL` — defaults to SQLite, set to MySQL URL for production
- `HITL_ENABLED` / `HITL_REQUIRE_APPROVAL_TOOLS` — approval workflow control
- `AGENT_MAX_STEPS` — max tool-calling steps per run (default: 10)
- `AGENT_PARALLEL_TOOL_CALLS` — enable parallel tool execution (default: false)
- `AUTH_RATE_LIMIT_MAX_ATTEMPTS` / `AUTH_RATE_LIMIT_WINDOW_SECONDS` / `AUTH_RATE_LIMIT_BLOCK_SECONDS` — rate limiting

See `backend/.env.example` for the full list (21 vars).
