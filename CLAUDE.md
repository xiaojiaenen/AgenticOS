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
npm run build:ppt-css                       # compile PPT Tailwind CSS for backend
```

The Vite dev server proxies `/api` to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8001`). Set `DISABLE_HMR=true` to disable HMR if needed.

**Docker**: `docker compose up -d --build` deploys both services. Backend on :8001, frontend served by nginx on :3001 (proxies `/api` to backend).

## Architecture

### Backend (FastAPI + wuwei >=1.0.3)

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
    schemas/                        # Pydantic request/response models for each endpoint group
    tools/
      email_tools.py               # IMAP/SMTP email tools — setup, count, read, search, get, send
      ppt_tools.py                  # save_slide, read_slide — per-page SVG file I/O
      chart_tools.py                # calc_chart_positions — bar, pie, donut, line, radar, grid
      icon_tools.py                 # search_icons — search icon libraries by keyword
      quality_checker_tools.py      # check_svg_quality — run SVG quality checker on slides
      pptx_reverse_tools.py         # convert_pptx_to_svg — reverse-engineer PPTX to SVG
      template_tools.py             # import_pptx_template — import PPTX as design template
    services/
      agent_service.py             # core orchestrator — creates wuwei Agent, manages SSE streaming,
                                   #   approval integration, usage recording, injects design catalog
                                   #   (31 SVG layouts + 149 themes) into PPT-mode messages,
                                   #   ThinkingHistoryCompatibilityHook
      agent_profile_service.py     # profile CRUD, built-in default profiles, runtime resolution
      skill_service.py             # skill CRUD, zip upload, filesystem management
      approval_manager.py          # HITL approval workflow with futures and subscriber broadcast
      tool_config_service.py       # tool catalog (8 tools) with per-mode defaults, sub-tool approval
      session_storage.py           # DB-backed wuwei storage (sessions, messages)
      ppt_artifact_service.py      # collects save_slide SVG files from ppt-sessions/, resolves
                                   #   var(--token) → hex via theme CSS, validates ≥3 slides, persists artifacts
      ppt/                         # SVG-native PPT pipeline
        svg_layouts.py             # 31 complete SVG structural templates injected into LLM context
        theme_token_resolver.py    # parses data/design-themes/*.css, resolves var(--xxx) to hex
        svg_to_pptx/               # SVG → native DrawingML PPTX conversion (pptx_builder, drawingml_*)
        pptx_to_svg/               # reverse: PPTX → SVG conversion (slide_to_svg, shape_walker, etc.)
        svg_finalize/              # SVG post-processing (icon embedding, image alignment, tspan flatten)
        svg_editor/                # Flask-based visual SVG annotation editor
        template_import/           # PPTX template import, extracts theme/layout metadata
        svg_position_calculator.py # chart coordinate generation (bar, pie, radar, line)
        svg_quality_checker.py     # 9-dim SVG validation before PPTX export
      auth_service.py              # registration, login, session management, rate limiting
      local_skill_import_service.py
    prompts.py                     # system prompts for 4 agent modes — PPT prompt is 250+ lines
                                   #   covering SVG constraints, 31 layouts, 149 themes, narrative
                                   #   framework, tspan rules, speaker notes discipline
  scripts/
    convert_design_systems.py      # convert open-design design systems to data/design-themes/*.css
    import_local_skills.py         # import local skill folders into the database
```

The wuwei framework (>=1.0.3) provides `Agent`, `LLMGateway`, `ToolRegistry`, `SkillManager`, `HitlHook`, and `ContextCompressionHook`. The backend wraps these with FastAPI endpoints and database persistence.

### Data directory

```
data/
  design-themes/                   # 149 brand design theme CSS files (apple.css, github.css,
                                   #   spotify.css, etc.) — each defines :root { --bg, --accent,
                                   #   --text-1, ... } color tokens for SVG slide rendering
  ppt-output/                      # generated PPT artifacts (source SVGs + preview HTML)
  ppt-sessions/                    # per-session working dirs — save_slide writes slide_N.svg here
  skills/                          # local skill files (zip uploads extracted here)
```

### Four agent modes

| Mode | Default tools | Behavior summary |
|------|--------------|-----------------|
| `general` | calc, time, file (approval required) | Daily Q&A, lightweight tool use |
| `ppt` | icon, ppt, chart, quality_checker, pptx_reverse, template | SVG-native slide deck generation: LLM calls save_slide tool per page, 149 design themes with CSS token system (var(--bg), var(--accent), ...), 31 SVG layout templates, SVG→native PPTX export via DrawingML conversion |
| `website` | calc, time, file, npm | Web/frontend development mode |
| `email` | calc, time, skill | Email management via IMAP/SMTP — read, search, send with CC |

### PPT generation — SVG-native pipeline

PPT generation uses a **pure SVG → native PPTX pipeline**. No HTML, no Tailwind, no dom-to-pptx.

**Design token system:** 149 brand design themes at `data/design-themes/*.css`, each defining 16 color tokens as CSS custom properties:
```css
:root {
  --bg: #ffffff;        --bg-soft: #f5f5f7;   --surface: #fbfbfd;
  --surface-2: #eeeef0; --border: #d2d2d7;    --border-strong: #e8e8ed;
  --text-1: #1d1d1f;   --text-2: #424245;     --text-3: #86868b;
  --accent: #0071e3;   --accent-2: #0077ed;   --accent-3: #0066cc;
  --good: #16a34a;     --warn: #eab308;       --bad: #dc2626;
}
```

**How design is injected (6 layers):**

1. **`_inject_design_catalog()`** in `agent_service.py` — on every PPT-mode request, appends to the user message: (a) 31 complete SVG layout templates from `svg_layouts.py`, (b) token semantic quick reference, (c) icon rules, (d) SVG forbidden-elements list, (e) 149 theme names + selection guide — so the LLM copy-pastes real SVG structures.

2. **System prompt** (`prompts.py:PPT_SYSTEM_PROMPT`) — 250+ lines constraining the LLM: must use `save_slide` tool (not chat output), all colors via `var(--token)`, `data-theme` must be from the 149 list, no `<style>`/`<foreignObject>`/`<mask>`/`class`/`rgba()`, top-level `<g id="...">` groups for animation anchoring, `<!-- notes: ... -->` speaker notes, 8-14 pages with ≥2 section dividers.

3. **31 SVG layouts** (`svg_layouts.py`) — structural templates across 7 categories (Opening, Data, Text, Comparison, Flow, Time, Image, Ending). LLM copies the SVG, replaces placeholder content with real data, preserves `var(--token)` color refs.

4. **Theme CSS files** (`data/design-themes/*.css`) — the value source for all 16 color tokens. `theme_token_resolver.py` parses them at storage time.

5. **Token resolution** — `PptArtifactService.create_from_slides_dir()` loads the theme CSS for the chosen theme, calls `resolve_token_values()` to replace every `var(--bg)` → `#ffffff` etc., producing self-contained SVGs.

6. **SVG→PPTX export** — `export_pptx()` in agent_service.py runs 4 post-processing steps (embed_icons, align_embed_images, flatten_tspan, fix_rounded), then `svg_to_pptx/pptx_builder.py` converts each SVG element to native DrawingML shapes for a .pptx file.

**Tool-based workflow:** LLM calls `save_slide(slide_num=N, svg="...")` per page, writing to `data/ppt-sessions/<session_id>/slide_N.svg`. On "done", agent_service collects these files and creates the artifact. PPT mode includes 6 tool groups: icon_tools, ppt_tools (save_slide, read_slide), chart_tools, quality_checker_tools, pptx_reverse_tools, template_tools.

### Sub-tool approval

Per-tool approval now supports sub-tool granularity. `TOOL_CATALOG` in `tool_config_service.py` defines `sub_tools` per tool (e.g., `file` has 7 sub-tools like `read_text_file`, `write_text_file`, etc.). The admin UI can toggle approval per sub-tool, stored in `approval_sub_tools_json` column. Empty list = all sub-tools require approval (backward compatible).

### HITL approval flow

When an agent invokes a tool that requires approval:
1. `HitlHook` triggers `ApprovalManager.request_approval()`, persists to `agent_approvals` table
2. Frontend receives `approval_required` SSE event (includes sub-tool info), shows `PendingApprovalPanel`
3. User approves/rejects → `POST /api/v1/agent/approvals/{id}/decision`
4. Future is resolved, agent proceeds or aborts; timeout after `HITL_TIMEOUT_SECONDS` (default 300s)

Approval now supports sub-tool granularity — each tool's `sub_tools` can be individually configured for approval via `approval_sub_tools_json`. Note: approval queues are in-memory and do not survive server restart.

### Email tools

Custom email integration at `app/tools/email_tools.py` — registered as wuwei tools:
- `setup_email` — store IMAP/SMTP credentials per session
- `count_emails` — stats with folder, unread, date range filters
- `read_emails` — paginated inbox/sent/draft with limit/offset
- `search_emails` — keyword search across subject + body
- `get_email` — full email detail by message ID
- `send_email` — send with optional CC

Credentials stored in `user_email_credentials` table, persisted across sessions. Uses `contextvars` to resolve the current session's credentials.

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
    ppt/                           # PptArtifactPanel (renders HTML preview, exports to .pptx via dom-to-pptx)
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

Tests cover: auth, agent stream, tool config, users, dashboard, skills, agent profiles, agent service, website mode defaults, local skill import, health.

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
