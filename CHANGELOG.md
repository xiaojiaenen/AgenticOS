# Changelog

本文件记录 AgenticOS 的所有显著变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **草稿状态**：`v3.2.0` 一节由仓库巡检（2026-10-07）与既有文档反推生成，**尚未逐条核对 `git log v3.1.0..HEAD`**。
> 标注 `待核对` 的条目表示证据来自文档描述而非逐条提交信息。补齐后请移除本段说明。

---

## [Unreleased]

### Changed — 升级 wuwei 3.0.2 → 3.2.1（2026-10-28）

上游 3.2.1 把 3.0.2 时代的一批流式缺陷修掉了（详见
`docs/wuwei-3.0.2-问题清单.md` 顶部的对照表）。本节记录本次升级的适配动作。

**依赖**
- `wuwei>=3.2.1`；连带 `openai` 2.32.0 → 3.40.0（wuwei 3.2.1 要求 `openai>=3.23.0`）。
- `httpx` 与 `openai` 改为**显式生产依赖**。openai 3.x 起不再自动安装 httpx
  （改用 httpx2），而 app/ 下 14 个文件直接 `import httpx`、2 个直接 `import openai`，
  只靠传递依赖是定时炸弹。

**Fixed**
- Cookie 适配器改走父类 `__init__`（用 3.2.1 新增的 `client=` 注入点）。
  之前手写 `self.client = ...` 跳过了父类初始化，漏掉 `supports_reasoning_content`
  等字段 —— 3.0.2 不读这些字段所以一直没暴露，3.2.1 下第一行就 `AttributeError`，
  **所有 Cookie 认证的企业网关不可用**。顺带修掉隐藏 bug：手写 init 时
  `max_tokens` 没进请求体，上游按自身默认上限截断，长回答会被切。
- OpenAI 兼容端点的 usage 透传：流式与非流式的 `usage` 之前都**硬编码成 0**，
  而 agent 侧的 `done` 事件明明带着真实 token 数。对外是 OpenAI 兼容端点，
  客户端据此计费，报 0 等于所有接入方的账单全错。现在收尾帧带真实
  `prompt_tokens` / `completion_tokens` / `total_tokens`。

**Removed**
- 删除 230 行的 `AgentRunner.stream_events` monkey-patch（并发工具执行）。
  wuwei 3.2.1 的 `ToolExecutor.execute(concurrent=True)` 已原生实现同样的
  按 `is_concurrency_safe` 分批并发（实测补丁版 0.504s vs 原生 0.505s，事件序列
  完全一致）。那个补丁整段复制了上游执行循环，上游一改就静默落后 ——
  本次升级上游新增的 `side_effect` / `requires_approval` 事件字段它就拿不到。

**Added**
- `app/services/approval_types.py`：自持 `ApprovalRequest` / `ApprovalDecision`。
  wuwei 3.2.1 删除了这两个类（审批重构为 `InterruptSignal` + checkpointer +
  `Agent.resume()`）。它们本来就没有行为，只是传参容器；而我们的审批流程
  （Redis pub/sub + DB + SSE）完全是自研的，走 `approval_provider` 回调模式，
  该模式 3.2.1 未变。
- `ProviderSpec.extra` 支持 `output_token_parameter`：o1 / o3 / gpt-5 这类推理模型
  只认 `max_completion_tokens`，给 `max_tokens` 会被上游直接 400。

### Added — 用量记账的审计维度（2026-10-27）

在此之前，`agent_usage_events` 只能回答「谁用了多少」，回答不了「走的哪条路由」：
模型名兜底成 `.env` 的 `openai_model`，企业网关凭据只在网关上挂了个
`_agenticos_credential_id`，全仓没有一个消费者。结果是切换提供商后用量图里的模型名
一直是旧值，某个共享账号撞 401 也定位不到影响面。

**口径（不要改反）**：token 归属仍然是 `user_id`（发起请求的人）。企业网关的账号是
系统级共享池，一个号被多人共用，按账号聚合出来的数字对任何个体都不成立。新增列全部
是**审计标签**，不参与统计。

- 迁移 `0014_usage_route_audit`：`agent_usage_events` 增加 `provider_id` /
  `provider_slug` / `provider_name` / `credential_id` / `account_label` /
  `tokens_estimated`。`credential_id` **不加外键** —— 凭据会因换号或泄露轮换被删除，
  而用量是历史事实，不能因为删了个账号就让历史统计悬挂或级联消失。
- `services/llm_providers/route.py`：`RouteSnapshot` + `attach_route()` /
  `describe_route()` / `resolve_model_name()`。路由信息在**构建网关时**挂到对象上，
  记账时读对象而不是重新解析配置 —— 管理员切换提供商的瞬间，重新解析拿到的是新配置，
  而那次请求发出时用的是旧配置，会张冠李戴。
- `model_name` 改为取网关实际发出的模型，不再兜底 `settings.openai_model`。开发库里
  93 条历史行全部记成 `deepseek-flash` 就是旧实现留下的痕迹。
- 上游没回流 usage 时按字符数估算的行打 `tokens_estimated=True`，让「实际计费」和
  「估算值」在统计口径上可区分（此前混在一起，谁也不敢用这个数）。
- `GET /dashboard/my-usage`：用户看自己的用量，只按 `user_id` 聚合，不暴露提供商/凭据。
- `GET /dashboard/usage-routes`（管理员）：按提供商 / 账号 / 模型聚合的排障视图，
  单独给出 `legacy_runs`（迁移前的历史行，无路由信息）与 `env_fallback_runs`
  （走了 `.env` 兜底，说明配置没生效）—— 这两项是「配置没生效」的显式信号，不是噪音。
- 管理端看板新增「用量路由审计」面板，与主看板共用时间范围但独立请求：它是排障视图，
  取数失败不该让整个看板变成错误页。
- 顺带修掉 `AgentUsageEventModel` 里写了两份 `__table_args__` 的问题（后一份直接覆盖
  前一份，改第一份索引永远不生效），并清掉一对字段完全重复的复合索引。

### Fixed — wuwei 网关补强（2026-10-27）

通读 `wuwei` 的 `llm/gateway.py` 与 `adapters/` 后发现：**非流式路径做得比较完整
（分类重试 / 超时 / fallback），流式路径基本只有「能跑」**，而界面走的恰恰是流式。
新增 `services/llm_providers/adapter.py` 在公开方法上补强，不改 site-packages：

- **流式重试**：`RetryingGateway` 覆盖 `generate`。wuwei 的 `_generate_stream` 不读
  `retry_policy`、不读 `_fallback_adapter`（实测配了 3 次重试 + fallback，实际只调
  1 次、fallback 0 次）。补丁的约束是**只在尚未输出任何内容时重试** —— 已经吐字再
  重来会出现重复文本，工具还可能执行两次。开关 `LLM_STREAM_RETRY_ATTEMPTS`（默认 2）。
- **工具调用不再静默丢失**：网关只在 `finish_reason == "tool_calls"` 时组装完整调用，
  有些网关收尾只给 `stop`，模型「说要调工具」就会被当成普通回答结束。适配器记住
  本轮出现过工具增量并纠正语义。
- **非流式不再因缺 `usage` 崩**：上游直接取 `raw_response.usage.prompt_tokens`，
  兼容网关省略 usage 时抛 `AttributeError`，把一次正常请求变成 500。同时把 Literal
  之外的 `finish_reason`（如 vLLM 的 `insufficient_system_resource`）归一化为 `stop`。
- **SDK 重试显式关闭**：`AsyncOpenAI(max_retries)` 默认 2，与网关自身的重试叠加会让
  实际次数不可预期；现在统一由网关控制。注意 `max_retries` 不能经 `**kwargs` 传给
  `OpenAIAdapter` —— 它会进 `default_params` 并展开成上游请求字段，实测直接
  `TypeError`，已用测试钉住。

新增 9 个后端用例（工具调用纠正、缺 usage 解析、未知 finish_reason、三种重试语义、
SDK 参数不泄漏进请求体）。

### Added — 企业网关实战适配（2026-10-27）

对接真实企业网关（格力百通 `agents.gree.com`）时暴露的五类硬伤与对应抽象。这一批改动
不是「多支持一家厂商」，而是**把「标准 OpenAI 兼容」这个隐含假设拆掉**，让提供商层
在真实内网网关上也成立。

- 新增 `services/llm_providers/presets.py`：`ProviderPreset` / `LoginFlow` /
  `TransportOptions` / `ProbeSpec`，内置 `gree_baitong` 预设。厂商差异从代码里的
  if 分支收敛为一份数据，接第二家网关只加数据不改逻辑。
- **自动登录参数化**（`auto_login.py`）。此前硬编码的动作在内网 SPA 上必然失败：
  `wait_until="networkidle"` 在常驻轮询页永远不静默；提交按钮文案是「授权并登录」
  且不是 `<button>`；会话 `SESSION` 由登录后的前端脚本异步写入，只 `sleep(1)` 取一次
  拿不到；未设置 `ignore_https_errors` 导致自签证书直接握手失败；未按域过滤会把
  多域 SSO 的无关 Cookie 一并发给上游。现在这些全部由 `LoginFlow` 描述，且
  **基线取自预设而非默认值** —— 只改一行按钮文案时不会把 `required_cookies` 一起丢掉。
- **分阶段连通性诊断**：`network → auth → chat → tools`，`?deep=true` 才真实发对话
  与 function calling 请求。关键修正是**只有认证阶段 401/403 才标记账号失效** ——
  旧实现拿 `/models` 的 403 当认证失败，而企业网关的 403 常常只是「该接口要 admin」，
  等于点一次「测试」就把一份有效 Cookie 判死。
- **`extra` 白名单 + `extra_body` 通道**：openai SDK 2.x 的 `create()` 没有 `**kwargs`，
  把 `enable_thinking` 平铺进请求会抛 `TypeError`（已实测）。现在顶层只接受已知键，
  非标字段必须放进 `transport.extra_body`，在保存时就拒绝而不是对话时崩。
- **多账号池**（迁移 `0013`）：`llm_provider_credentials` 去掉 `provider_id` 唯一约束，
  新增 `label` / `priority` / `last_used_at` / `failure_count` / `disabled`。选号策略是
  「最久未用优先，priority 只在都没用过时决定首次挑谁」—— 让 priority 一路压过
  `last_used_at` 的话，备用号永远不会被用到，也就谈不上分摊配额。连续失败 3 次自动
  退出轮换，重新启用即复位。续期粒度也从「提供商」下沉到「账号」。
- **模型目录**（新表 `llm_provider_chat_models` + `discovery.py`）：上游的「模型 ID」与
  「请求体里要填的模型名」经常不是同一个东西（百通 `qwen3.6-35b` vs
  `Qwen3.6-35B-A3B`），手填只能等到 404 `Model Not Exist`。现在能从上游同步清单
  （百通公开注册表 / 标准 `/models`）、可选、可校验。
- **按用途绑定模型**：`extra.roles` 把 chat / reasoner / fast / vision / image 映射到
  具体模型，`llm_factory` 与 `agent/factory` 支持 `role`。缓存键改用「解析后的模型名」
  而不是 `provider.model`，否则改完绑定会一直复用旧 agent。
- **路径前缀由 `base_url` 吸收**：百通把接口挂在 `/agents/baitong` 而不是 `/v1`，
  SDK 会自己拼出 `/agents/baitong/chat/completions`（已用真实 SDK 验证）；响应体是
  标准 OpenAI 形态（`reasoning_content` / `tool_calls` / `usage`），解析层无需适配。
- 传输层补齐：浏览器 UA（站点有 UA 级防护）、显式 `timeout` 与 `max_retries`
  （SDK 默认 2 次重试对 Cookie 认证是纯浪费）、Cookie 路径补上 `temperature` 等采样
  参数（此前自建适配器漏传，同样的配置换个认证方式生成风格就变了）。
- 深度探测新增 `stream` 阶段（`network → auth → chat → stream → tools`）：界面走的是
  流式，只测非流式会漏掉「SSE 被 SPA 兜底成 HTML」和「上游不认 `stream_options`」。
- **修复流式 usage 恒为 0**（影响所有提供商，不只企业网关）：适配器自己加了
  `stream_options.include_usage`，上游按规范回一帧 `choices: []` + `usage`，但 wuwei
  的流式循环先 `parse_stream_chunk`、拿到 `None` 就 `continue`，那一帧的 usage 读不到。
  结果是 `agent_usage_events` 里的 token 统计一直是 0。修法是把该帧伪装成「空内容帧」
  让循环走完，而不是抄一遍上游循环（升级即失效）。
- 新增 36 个后端用例（`tests/test_llm_provider_presets.py` 及 `test_llm_providers.py`
  的端点与流式部分），覆盖预设补全、extra 拒绝、选号轮换、坏号退出、目录幂等、
  「500 不误杀凭据 / 401 才标记」、流式 usage 透传、SSE 探测等易回归点。

### Added — AI 提供商层（2026-10-27）

把「用哪个大模型后端」从环境变量变成可运营的配置，并恢复曾于 `0009` 移除的
企业网关（Cookie 认证）接入。

- 新增 `llm_providers` / `llm_provider_credentials` 两张表（迁移 `0012`）。
  `provider_type` 描述的是**认证方式**而非厂商：`openai_compatible`（API Key）
  与 `enterprise_cookie`（浏览器登录态）。换厂商只改配置，不改代码。
- 新增 `backend/app/services/llm_providers/`：
  - `spec.py` 解析优先级：**DB 默认 → DB 首个启用 → 环境变量兜底**。第 3 级是
    升级通道，存量部署不建提供商也不会开不了机。
  - `runtime.py` 构建网关。Cookie 方式通过**继承** `OpenAIAdapter` 实现（旧实现
    是构造后替换 `adapter.client` 私有属性，wuwei 一改名就静默退化成空 Key 请求）。
  - `auto_login.py` 用 Playwright 填表取 Cookie；`_infer_expire_at` 只认认证类
    Cookie 的最早过期时间并排除 `_ga` 这类长有效期追踪 Cookie。
  - `credentials.py` 密码与 Cookie **只以密文落库**；过期判定不看 `status`，
    必须同时校验 `expire_at`（旧实现只查 status，Cookie 过期后仍当可用，
    每次请求撞 401 再重登）。
- 新增管理端点 `POST/GET/PATCH/DELETE /settings/llm-providers` 及
  `/{id}/default`、`/{id}/test`、`/{id}/login`、`/{id}/credential`、
  `/{id}/credential/cookie`、`/import-env`。全部写审计（已加入
  `test_audit._AUDITED_MODULES`），`detail` 只记字段名与开关状态。
- 新增 arq cron `refresh_llm_provider_cookies_task`（每 20 分钟检查一次，
  仅在「即将过期」时登录，避免无脑起浏览器）。
- 前端管理端新增「AI 提供商」页：生效来源条（含「正在用环境变量兜底」显式提示）、
  列表与默认切换、连通性测试、企业网关登录态面板（账号密码 / 自动登录 /
  手贴 Cookie / 过期时间 / 自动续期）。

### Changed — LLM 构建改为按提供商

- `llm_factory.build_llm_for_user` 改为薄壳转发到提供商解析；`model` 传 `None`
  表示用提供商自身模型（旧实现用全局 `OPENAI_MODEL` 覆盖，导致「换了网关但
  模型没换」）。
- `agent/factory.py`：`_ensure_openai_key` 换成 `_ensure_llm_configured`
  （API Key 或 Cookie 登录态任一可用即通过）；agent 缓存键加入
  `provider.slug` + `provider.model`，否则切换提供商后旧 agent 会被一直复用。
- 清理 `prefer_cookie=True` 死参数与 `agent/service.py` 的旧校验调用。
- 移除 `backend/app/services/upstream/` 残留（源文件早删，只剩 `__pycache__`，
  Python 会把它当命名空间包继续 `import` 成功）；`.env` 与 `conftest.py` 里的
  `UPSTREAM_AUTO_LOGIN_ENABLED` 一并清理。

### Added — 知识库冲突定期巡检（2026-10-27）

- 新增 `backend/app/services/knowledge/conflict_scanner.py`：全库**跨页面配对扫描**，
  补齐编译期冲突检测「只比新页 vs 旧页」的盲区（历史导入、分次上传的两页之间的矛盾
  永远不会被发现）。流程：标题 bigram 倒排筛候选 → 正文 bigram Jaccard 确认同主题 →
  规则**双向**判定 → 幂等写入 `kb_review_items`。**只写复核队列，不改任何正文。**
- 新增 `POST /knowledge/bases/{id}/conflicts/scan`（手动触发；`use_llm=true` 才追加 LLM 复核）。
- 新增 arq cron `scan_knowledge_conflicts_task`，**每周一 04:23** 全库执行。
- 前端「待复核」Tab 增加「运行冲突巡检」按钮，并把「只写队列不改正文」写在提示语里。

### Fixed

- `WikiCompiler._jaccard_similarity` 用 `str.split()` 分词，中文标题没有空格，
  相似度恒为 0 或 1 → 编译期「同主题页面」发现形同虚设。改为
  `tokenizer.jaccard_bigrams`（字符 bigram），「Redis 缓存雪崩」与「Redis 缓存穿透」
  这才真能判为同主题。
- 统一版本号：新增根目录 `VERSION`（`3.2.0`）作为唯一来源，
  `backend/pyproject.toml`、`backend/uv.lock`、`frontend/package.json` 三处同步
  （`uv.lock` 不同步会让 CI 的 `uv sync --frozen` 直接失败）。
- CI 前端 job 补 `npm run verify:css`（Chrome 85 兼容门禁），
  兑现 `development-plan-v2` 的 M0 验收标准。

### 待办

- 部署文档确认两处必选依赖：**Redis**（限流迁移后不可回落 in-memory）与 **MySQL ≥ 5.7.6 + `ngram_token_size`**（知识库检索）。
- 压测：`backend/loadtest/locustfile.py` 已就绪，尚无 500 并发 P95 实测记录（需在部署环境跑，本机 CPU 会先成为瓶颈）。
- 知识库向量召回**当前显式关闭**（`.env` 里 `KNOWLEDGE_VECTOR_ENABLED=false`）。
  接入 embedding 服务后改回 `true` 并跑一次 `force=true` 重建索引即可。
- 企业网关（Cookie）提供商需要 Playwright 浏览器：部署镜像里要执行
  `playwright install chromium`（或设 `PLAYWRIGHT_CHROMIUM_PATH` 指向已有的 Chromium），
  否则「立即登录」会返回「未安装 Playwright，无法自动登录」。手贴 Cookie 不受影响。

### Other

- 补根目录 `LICENSE`（MIT，2026-10-27）。

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
