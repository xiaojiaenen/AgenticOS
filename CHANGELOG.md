# Changelog

本文件记录 AgenticOS 的所有显著变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **草稿状态**：`v3.2.0` 一节由仓库巡检（2026-10-07）与既有文档反推生成，**尚未逐条核对 `git log v3.1.0..HEAD`**。
> 标注 `待核对` 的条目表示证据来自文档描述而非逐条提交信息。补齐后请移除本段说明。

---

## [Unreleased]

### 待办

- 统一版本号来源：`refs/tags` 为 `v3.1.0`，`backend/pyproject.toml` 为 `0.1.0`，`frontend/package.json` 为 `0.0.0`，三处不一致。
- 补根目录 `LICENSE`；评估是否需要单一 `VERSION` 文件。
- 部署文档确认两处必选依赖：**Redis**（限流迁移后不可回落 in-memory）与 **MySQL ≥ 5.7.6 + `ngram_token_size`**（知识库检索）。

### 计划中（见 `docs/development-plan-v2.md`）

- M4：chat 页重构 + fetch 封装统一 + SSE 换库 + `tsconfig.strict` 全仓清零。
- M5：知识库 jieba + MySQL ngram 迁移 + 中文检索效果回归。
- M6+：阶段 0 性能优化 → 压测 → 部署单元拆分 → Casbin 权限。

---

## [3.2.0] - 2026-10-07

> 对应本地 `main` = `d9731da`（领先 `origin/main` = `7d51e19` 共 **30 个提交**，尚未推送）。
> 上一版本 tag：`v3.1.0`（`7097f6c`）。

### Added — 办公模式（Office）：文档与表格产物

- 新增基于 **Univer 1.0.3**（`@univerjs/presets` / `preset-docs-core` / `preset-sheets-core`）的文档与表格编辑器：
  `frontend/src/components/office/DocEditor.tsx`、`SheetEditor`，后端运行时 `backend/office-runtime/server.mjs`。
- 文档产物支持**标题层级视觉样式**：写入 `paragraphStyle.namedStyleType`（`HEADING_1..4` 枚举实为 **4/5/6/7**）并配合
  `body.textRuns[].ts.{fs,bl}` 给出字号（32/24/18/16px + 加粗）；旧快照通过 `withHeadingStyles()` 自动升级，**历史产物无需重新生成**。
- 表格产物支持**多工作表**与版本条（`ArtifactVersionBar`）。
- 新增 `ArtifactKind` 联合类型，版本条徽标由二元三元表达式改为 `KIND_BADGE` 映射，接入 `sheet_artifact` 分支。

### Added — 前端企业级重构（shadcn/ui 体系）

- 组件体系切换为 **shadcn/ui（Radix UI）**：`radix-ui`、`class-variance-authority`、`cmdk`（⌘K Command 面板）、`sonner`（Toast）。
- 表格统一为 **TanStack Table**，服务端状态引入 **TanStack Query**。
- 表单统一为 **react-hook-form + zod**。
- 新设计系统：`zinc` 中性灰阶为骨 + 单一强调色 **indigo-600 `#4f46e5`**；暗色模式为一等公民（CSS 变量 + `.dark` class）。
- 深色模式**全量 token 化**：批量替换 **1010 处**硬编码色值（`bg-white` / `text-slate-800` → `bg-[var(--surface-1)]` / `text-[var(--foreground)]`），
  新增 `.admin-card` / `.admin-inset` / `.admin-heading` / `.admin-muted` 语义类。
- 登录 / 注册页与 Home 首屏新增克制背景动画（`ogl` shader 或纯 CSS 径向渐变降级），admin 与 chat 页保持纯静态背景。
- 侧栏「智能体商店 / 集成市场 / 邮箱设置」收进一行 3 个等宽图标按钮，省下约 90px 纵向空间。

### Removed

- **删除玻璃拟态**：移除 `@xiaojiaenen/liquid-glass` 依赖、vite alias、`useIsGlassTheme` hook、`MascotIcons` 玻璃分支及全部 `.glass-*` 样式；
  `src/index.css` 从 1176 行重写为 token + 语义 class（约 300 行），移除全部 `!important` 覆盖。
- 移除 `svg_editor` 的 **Flask 旁路**，迁为 FastAPI `APIRouter`（保留人工精修流程），Flask 依赖下线。
- 后端 `agent_service.py`（2312 行）拆分为 `app/services/agent/{factory,orchestrator,artifacts,prompts,service}.py`，**公共 API 零变更**。
- 删除手写 `_ensure_compatible_schema()`，schema 变更改由 Alembic 接管。

### Changed — 后端

- 引入 **Alembic** 迁移；对现有生产库以 `alembic stamp head` 建立 baseline，CI 增加 `alembic upgrade head` 空库验证与 models diff 守卫。
- 登录限流由 MySQL 表状态机迁移为 **Redis 原子 INCR 固定窗口**（复用 `cache_service` 模式）；**Redis 成为生产必选依赖**。
- 知识库检索：中文分词改为 **jieba**，BM25 落 **MySQL FULLTEXT `WITH PARSER ngram`**，淘汰 Python 内存 BM25（SQLite 开发环境保留 fallback）。
- 前端 `sanitizeHtml` 正则实现替换为 **DOMPurify**；iframe 沙箱预览架构保留。
- SSE 客户端迁移至 **`@microsoft/fetch-event-source`**；`apiClient.ts` 统一 401 跳登录 / 超时 / 错误归一化。
- `contextvar` 六件套收敛为单个 `AgentCallContext` dataclass；`_inject_design_catalog` 主题文案迁至 `app/resources/prompt_catalogs/*.md`。
- 渲染与构建兼容 **Chrome 85**：自定义 token 一律 hex/rgba（禁用 `oklch` / `color-mix`），`@vitejs/plugin-legacy` + `browserslist` targets 统一为 `Chrome >= 85`，
  CI 断言构建产物中 `oklch(` 与 `color-mix(` 计数为 0（`npm run verify:css`）。

### Fixed

来自 `docs/测试报告-2026-10-01.md`（48 通过 / 0 阻塞），三轮共修复 12 项：

| # | 问题 | 修复要点 |
|---|---|---|
| 1 | 首页选智能体发起对话时 **profile 丢失**（请求退回通用助手，PPT 模式表现为「文件探索循环」） | Chat 页增加 `agentProfilesLoaded` 门控，等智能体列表加载完成后再发首条消息 |
| 2 | 网站预览空白 / 显示「请使用最新版 Chrome」（实为预览刷新跨域异常打崩 React 应用，落到崩溃兜底页） | 刷新改为重建 blob URL（`refreshNonce`），不触碰 iframe 内部；预览改用 `srcDoc` |
| 3 | PPT 纯文字回答后误报「PPT 预览生成失败：幻灯片目录不存在」 | 整轮无幻灯片时静默收尾，不再注入错误文本 |
| 4 | 仪表盘卡片风格割裂、高低不齐 | 抽出共享 `STATIC_CARD`，副信息行占位保证等高，图表卡片 `flex h-full` 对齐 |
| 5 | 已部署站点目录 URL 404（dev 后端 StaticFiles 未开 html） | `/sites`、`/preview` 挂载加 `html=True`（生产 nginx 不受影响） |
| 6 | 停止生成后审批面板悬挂 | 停止时将悬挂审批标记为已拒绝并附取消原因 |
| 7 | 会话删除按钮触屏不可见（仅 hover 显形） | `md` 以下常驻显示，指针设备保持 hover 显形 |
| 8 | 集成市场空态「管理员尚未发布任何集成」文案误导（后端有意按已安装智能体关联过滤） | 文案改为「你安装的智能体暂未关联第三方集成」并给出管理入口 |
| 9 | 刷新后左侧会话列表标题退化成「通用助手」 | 后端新增 `title` 字段（`metadata.title` → summary → 首条用户消息摘录），前端标题以后端为准 |
| 10 | 网站 / PPT 产物刷新后消失 | ①补 `get_latest_website_artifact`（此前 `website_artifact` 恒为 null）②持久化 `currentSessionId` ③预览改 `srcDoc` + key 重挂载 |
| 11 | 左侧三个入口按钮占满整行 | 收进一行 3 个等宽图标按钮 |
| 12 | 深色模式有黑有白 | 1010 处色值 token 化 + 语义 class，`verify:css` 通过 |

办公模式专项修复（见 `.workbuddy/memory/2026-10-06.md`、`2026-10-07.md`）：

- **文档产物正文全空白**：Univer 要求 `dataStream` 末尾必须补收尾 `\n`（只写 `\r` 会被判为空文档，只渲染占位提示）；
  修 `composeBlocks()` 并在 `DocEditor.withDocumentTerminator()` 兼容历史快照；字数统计同步剔除 `\r` 与 `\n`。
- **表格模式整体不可用**：`server.mjs` 在 sheet → office 重命名时误删 `recalculate` / `requireWorkbook` / `resolveSheet` / `parseRange` 四个函数
  （`node --check` 查不出，只在运行时炸）；已恢复，`test_office.py` 5 个用例转绿。
- **产物切换时编辑器不重建**：`DocEditor` / `SheetEditor` 仅在挂载时读快照，而分支 key 为固定字符串 → 标题与字数更新、画布停留旧版；
  改为 `key={artifact.artifactId}`，并让 Univer 挂载到自建宿主节点以避开 React 节点簿记冲突（原会白屏 `Failed to execute 'removeChild'`）。
- **表格版本不落盘 / 不显示**（最后一次提交 `fix(sheet)`）：① `orchestrator` 仍取旧的驼峰键 `artifactId`（产物字段已统一为 `artifact_id`）→ `snapshot_sheet_version` 提前返回；
  ② 版本条 effect 依赖缺 `currentReference`，同会话出新版本不刷新；③ `useChatStream` 构造 `Artifact` 漏 `version`。
  已新增断言测试 `test_sheet_artifact_keys_match_orchestrator_reader` 盯住字段与读取键一致性。

### Security

- 前端 HTML 清洗改由 DOMPurify 承担（替换手写正则 sanitize）。
- 越权校验回归通过：普通用户访问 `/users` → 403；访问他人私有 KB 文档 → 403；公开 KB → 200；owner 访问私有库 → 200。

### Tests

| 门禁 | 结果 |
|---|---|
| 后端 `pytest` | **318 passed**（`test_office.py` 12 passed） |
| 前端 `npm test`（vitest） | **60 tests** |
| `npm run lint`（tsc + eslint） | 0 error |
| `npm run verify:css` | 通过（产物无 `oklch(` / `color-mix(`） |
| `ruff` | 全过 |

### 未覆盖（本轮已知）

- 企业上游（Cookie 自动登录、上游凭据）按要求跳过。
- 邮件模式实际收发（需真实 IMAP/SMTP 凭据）。
- PPT 导出 `.pptx`（依赖先产出 deck）。
- UI 注册依赖邮箱验证码，未配 `NOTIFY_SMTP_*` 时不可用（**按要求保留**，建议 `APP_ENV=test` 增加 dev 旁路）。
- WebSocket / 多实例并发、压测。

---

## 版本历史（自 tag 反推）

| 版本 | Tag 指向 | 日期 |
|---|---|---|
| 3.1.0 | `7097f6c`（peel `3e1646e`） | 待核对 |
| 3.0.0 | `393a432` | 待核对 |
| 2.0.0 | `5c698ce` | 待核对 |
| 1.0.0 | `5aab73b` | 待核对 |
| icons-v1.0.0 | `bf73853` | 待核对 |
