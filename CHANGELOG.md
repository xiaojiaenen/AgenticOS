# Changelog

本文件记录 AgenticOS 的所有显著变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **草稿状态**：`v3.2.0` 一节由仓库巡检（2026-10-07）与既有文档反推生成，**尚未逐条核对 `git log v3.1.0..HEAD`**。
> 标注 `待核对` 的条目表示证据来自文档描述而非逐条提交信息。补齐后请移除本段说明。

---

## [Unreleased]

### Refactor — 聊天状态层迁入 zustand + wuwei 3.4.1（2026-11-12）

- **R3-2 状态层收敛**：会话数据（`sessions` / `currentSessionId` /
  `visibleSessionsCount`）与流式状态（`runStatus` / `pendingDecisions` /
  `streamError`）从 useChatSessions / useChatStream 的 useState 迁入
  `stores/chatStore.ts`。store 的 setter 保持 React
  `Dispatch<SetStateAction<T>>` 契约，两个 hook 内部逻辑（含 1119 行的
  rAF 批处理）零改动。`ChatContext` 从 41 字段瘦身到纯动作 + refs +
  派生标志（唯一消费方 ChatMainArea 的数据读取改为逐字段 selector）。
  同时修复 `useChatStore()` 无参调用（Chat.tsx / ChatMainArea）导致的
  **每个按键都整页重渲染**。验证：tsc / vitest 165 / build + 浏览器真实
  冒烟（登录 → 发消息 → 流式渲染 → 刷新恢复原会话）。
- **wuwei 3.3.3 → 3.4.1**：上游 `_as_llm_error` 升级为 classmethod 并新增
  `provider` 位置参数 —— `RetryingGateway` 覆写已对齐（升级实测 TypeError）。
  R-6 / R-8 已被上游修复（本项目补丁成为空转安全网，按纪律保留）；
  R-7 未修（`BatchSafeMiddlewareProxy` 仍必要）。详见
  `docs/upstream/wuwei-3.0.2-问题清单.md` 的 3.4.1 状态表。
- **构建修复**：根 `.gitignore` 从 GBK/混合编码转 UTF-8 —— hatchling 会把
  所有 `.gitignore` 按 UTF-8 读取，此前 `uv sync` / `uv run` 长期因此失败
  （AGENTS.md 里的变通说明已删除）；删除非 UTF-8 的 `backend/uvicorn.err.log`。

### Refactor — 统一「等人」协调器 + stream_chat 拆分 + artifact 挂载统一（2026-11-12）

三批结构重构，行为兼容（后端 1251 passed / 前端 165 passed / build + lint 全绿）：

- **`app/services/interactions.py`（新增）**：`InteractionBroker` —— 外部 API 审批、
  缺参表单、决策问答三类「等人」交互的统一协调器（per-session 订阅队列 +
  per-interaction Future + Redis pub/sub 跨 worker + 统一超时 + 流结束清理）。
  此前三类各持一份模块级 Future dict：API 审批与表单**没有超时**（用户不响应
  工具永远挂着）、多 worker 部署下 resolve 静默失效、清理纪律各不相同。
  工具审批（ApprovalManager）有 DB 审计与参数改写语义，保持独立不经此层。
- **`coordinators.py` / `decision_tools.py` / `ppt_tools.py`** 改为委托协调器；
  `resolve` 端点契约不变（wire 兼容，前端零改动）。行为增强：API 审批超时按
  拒绝处理、表单超时抛结构化错误（模型可据此说明）、决策/PPT 计划确认支持
  跨 worker 回传。
- **orchestrator 事件泵 4 路 → 3 路**：user_input / api_approval / decision
  共用一条 tagged-event 队列，删除决策轮询（每循环 get_decision_queue）。
- **stream_chat 拆分**（810 → 574 行）：ppt-done / 通用 done / error 收尾
  抽为 `_handle_ppt_done` / `_handle_done_event` / `_note_error_usage`，
  共享可变状态收敛为 `_RunState`；website / document / sheet 三段近乎相同
  的 create+snapshot+yield 合并为 `_finalize_artifact`。
- **前端 artifact 挂载统一**（新增 `lib/artifactSnapshots.ts`）：payload →
  消息快照的映射此前在 useChatStream（流式）与 useChatSessions（回源）各写
  一份，是「实时空白、刷新正常」类漂移 bug 的温床。website 的 previewUrl
  TTL 纪律（流式不落、回源现签）在构建器签名上显式化。
- **测试卫生**：conftest 注入 `REDIS_URL=""` —— 此前测试进程读到 .env 的
  真实 Redis，异步客户端连接绑定首个事件循环，全量跑时跨循环 PUBLISH
  随机 5s 超时背锅（与 DB 隔离同一哲学）。新增 `tests/test_interactions.py`
  （12 用例）与 `lib/__tests__/artifactSnapshots.test.ts`。

### Chore — 死代码清理与仓库卫生（2026-11-12）

全仓审计后的纯减法清理，行为无变化（后端 1240 passed / 前端 150 passed / build + lint 全绿）：

- **删除孤儿模块**：`services/design_system.py`（连同 `/agent/design-systems` 两个端点，
  前端 0 调用，真实主题链路走 `theme_token_resolver`）、
  `services/multi_agent_graph_service.py`（0 引用，连带其 example）。
- **删除废弃实现**：`AuthRateLimitModel` 表模型（早已被 `rate_limiter.py` 取代）、
  `cache_service` 的限流方法区（0 调用方）。
- **删除死产物管线**：`ppt_tailwind_compiled.css` / `ppt_tailwind_content.html` /
  `ppt_tailwind_input.css` / `build:ppt-css` 脚本 —— 旧 Tailwind-PPT 模板系统的最后残留，
  SVG 管线取代后无任何消费方。
- **前端**：删 `dropdown-menu.tsx`（0 引用）、死依赖 `ai`、`@halobiron/dom-to-pptx`
  （连带 `/vendor/dom-to-pptx.js` 与其类型声明）、生产路径 3 处 `[probe]` console.log。
  `rxjs`（Univer 隐式依赖）、`cmdk`（combobox 依赖）、`@ai-sdk/openai-compatible`
  （e2e.config.ts）经核实仍在使用，**保留**。
- **仓库卫生**：清掉根目录 tmp_*.py、backend/g*.txt、uvicorn 日志、截图产物、
  含明文密码的截图脚本；`.gitignore` 补 `*.tsbuildinfo` / `.tmp-shot-*` / 前端根截图。
- **文档校正**：AGENTS.md 与实现对齐（agent/ 包结构、SVG 管线、SSE 16 种事件、
  路由表、alembic 双段式、测试 114 文件）；`docs/issues/wuwei-system-message-duplicate.md`
  加"已修复"状态头；业务领域分析笔记加 2026-11 校准节。

### Security — 工作流接入功能级授权 + 权限审计（2026-11-05）

对近期新增能力做了一次权限审计，发现工作流**完全没有接入授权体系**：
`FEATURE_GRANTS` 里没有任何工作流相关项，端点也没有功能门禁 ——
任何登录用户（只要工作流 enabled）都能运行管理员编排的流程，进而消耗
管理员配置的 LLM 配额、访问内网 HTTP。

**新增两个授权项**（`FEATURE_GRANTS`，管理端「权限」页可直接配置）：

- `use_workflows` — 使用工作流（运行 / 恢复人工输入）
- `view_workflow_runs` — 查看本人触发的工作流运行记录

**接入点**（端点与对话工具**同一口径**，避免「界面能跑、对话被拒」）：

- `POST /workflows/{id}/run`、`POST /workflows/runs/{id}/resume`
  → `require_feature_compatible("read", "use_workflows")`
- `GET /workflows/{id}/runs`、`GET /workflows/runs/{id}`
  → `require_feature_compatible("read", "view_workflow_runs")`
  （归属校验仍在：非管理员只能看自己触发的）
- 智能体工具桥 `run_workflow_*` → `_may_use_workflows()`，
  未授权时返回 `status: denied` 而不是悄悄执行

**默认收紧**（按产品要求）：工作流是管理员编排的平台能力，普通用户
**默认不能运行**，必须由管理员在「权限」页显式授予 `use_workflows`。

实现：启动时写入 `p, admin, *, feature:use_workflows, read` 锚点策略
（`DEFAULT_RESTRICTED_FEATURES`），让该功能处于「已配置」状态，
端点走严格的 `require_feature`（fail-closed）。Casbin 是 allow-override
模型（无 deny 规则），「未配置」与「配置了但谁都没授」在策略表里无法
区分，锚点是表达「默认拒绝」的必要手段。保留 `require_feature_compatible`
（未配置即放行）供未来新功能上线时选用，但工作流**不用**它。

- 无权用户的两种表现：HTTP 端点 403（`Permission denied: feature:use_workflows`），
  对话工具返回 `status: denied` 并提示联系管理员 —— 不会静默消耗 LLM 配额。
- 顺带修掉的测试基础设施缺陷（都是「用户 id 复用 + 关联数据残留」）：
  `test_api_keys` 三条断言依赖全库计数、`test_openai_compat` 安装记录撞
  唯一约束、`test_audit` 知识库 slug 写死、`test_permissions` 依赖新建用户
  落在 catalog 的 500 条窗口内。
- 验证：后端 1094 passed（Redis 在线/离线均绿）；新增
  `tests/test_workflow_permissions.py` 10 个用例（未配置放行 / 配置后拒绝 /
  授权后放行 / 管理员短路 / 工具桥同口径 / 端点 403 / 授权项已登记）。

### Changed — 部署文档与编排对齐「外部 MySQL + 外部 Redis」架构（2026-11-05）

以 `agenticos-runtime` 运行时镜像链路为准统一部署口径：MySQL 与 Redis 都是
外部服务，compose 不再包含任何数据库/缓存容器。

- `docker-compose.yml` / `docker-compose.runtime.yml`：移除内置 `redis`
  （Redis Stack）服务与 `redis-data` 卷，`REDIS_URL` 默认改为空
  （内存 fallback 仅限单机演示），`depends_on` 只剩 frontend → backend。
  `docker-compose.offline.yml` 本就是外部服务版，仅更新头部差异说明。
- `DEPLOY.md` 重写：架构图补上 worker（arq）与外部 Redis；部署方式改为
  「A. runtime 镜像（推荐，代码挂载）+ B. 薄镜像构建」双轨；环境变量表补
  `IMAGE_REGISTRY`、本地嵌入模型等缺失项；Redis 排查改为外部 Redis 验证。
- `OFFLINE-DEPLOY.md`：包内容表对齐 `package-intranet.ps1` 实际产出
  （`images/*.tar` + `MANIFEST.sha256` + `data/hf-cache`），部署步骤接入
  一键脚本 `install.sh`，移除已不存在的 `agenticos-code.tar.gz` /
  `SHA256SUMS` 等旧命名。
- `install.sh`：镜像导入同时接受 `images/*.tar` 与 `images/*.tar.gz`
  （打包脚本导出的是 `.tar`，原 glob 匹配不到任何文件）。
- `package-intranet.ps1`：离线包补齐 `docker-compose.offline.yml`、
  `.env.offline.example`、`OFFLINE-DEPLOY.md`、`add-deps.sh`、`install.sh`、
  `Dockerfile.offline`（原先缺这些，内网按手册操作会找不到文件）。
- 验证：三个 compose 文件 `docker compose config` 全部通过；两个 shell 脚本
  `sh -n` 语法通过。

### Added — 工作流拖拽画布（React Flow）（2026-11-05）

在结构化编辑器之外补上真正的拖拽画布。引入 `@xyflow/react` 12（React Flow）
—— 离线部署是「本地构建 dist 再复制进镜像」，不依赖离线环境跑 npm install，
因此新增依赖不破坏离线链路。

- **画布**（`WorkflowCanvas.tsx`）：拖拽移动节点（React Flow 手柄、缩放平移、
  小地图、网格）；拖拽节点出口圆点到目标节点建立连线；选中节点后 Del 删除；
  condition 的 true/false 连线用绿/红区分；右侧栏同步展示选中节点的参数表单
  与连线列表（可改分支标签、删线）。start 节点固定不可拖动（防误挪整图）。
- **位置持久化**：拖拽结束后把 `position` 写回 `graph.nodes[].position`。
  位置是**纯展示字段** —— 后端校验只认 id/type/params 与 edges，执行语义
  完全不受影响（有单测对比「带/不带 position」的图操作结果一致）。老图没有
   position 时按 BFS 自动布局，打开即整齐。
- **复用数据层**：画布的增删改、级联、去重全部调用结构化编辑器里已被单测
  钉住的纯函数，两种编辑模式的**行为保证一致**。
- **三态切换**：管理面板编辑框可在「画布 / 表单 / JSON」之间切换，JSON 非法
  时禁止切回可视化模式（不丢内容）。
- 修复：`onNodeDragStop` 闭包读到拖拽前的旧 `nodes`（位置写不回去），改用
  ref 读最新值 —— 由 e2e 发现。
- **验证**：真实浏览器 e2e（`tests/workflow-canvas.e2e.ts`，3 用例）——
  画布渲染 6 节点、拖拽后 position 真正落库、从手柄拖线真的建立新边。
  e2e 需要在本地跑（后端 + dev server + 种子脚本
  `scripts/seed_workflow_canvas_e2e.py`）；每个用例开头重置图数据，
  避免用例之间互相污染。单测 +12（位置字段不改变图操作语义）+1 渲染冒烟；
  `tsc --noEmit` 0 errors；vitest 111 passed。

### Docs — 工作流后续路线：循环节点与 ARQ 多 worker（2026-11-05）

新增 `docs/research/工作流后续路线.md`，记录两项**未实现**能力的方案与约束：

- **循环节点**：明确否决「开放回边」（终止条件无法在图里表达、恢复快照
  退化成执行序号、放行后易死循环）；建议对齐 Dify 的 **loop 容器 + 子图**
  形态（`items` / `max_iterations` 必填 / 每轮独立上下文 / 输出为数组 /
  参与 run 级预算）。
- **ARQ 多 worker**：指出进程内 `create_task` 在多副本下的三个缺口（归属不可
  见、无法取消、收尸误伤别的 worker），给出迁 ARQ 的改造清单（任务注册 /
  `worker_id` + 心跳 / 心跳超时收尸 / 取消端点 / ARQ 不可用时降级）。
- 附：当前引擎的已知边界表（无环、屏障语义、快照粒度、http 禁重定向等）。

### Fixed — 切换会话打断正在运行的流 + 人工输入串会话（2026-11-05）

用户反馈：「切换到其他会话，原本正在运行的会话就停了」。排查出两个缺陷，
根因都在前端：**把「切换会话」当成了「停止生成」**。

- **切会话即 abort**（`useChatStream.ts`）：旧的会话切换 effect 无条件
  `abortControllerRef.current.abort()`，后端收到 `CancelledError`，整轮
  LLM 生成作废（`orchestrator` 的 producer 被取消），用户切回来只剩半截
  回复。而且全局只有**一个** `AbortController`，同时跑两路流会互相覆盖。
  现在改为 `Map<sessionId, AbortController>`：切走后台继续读、继续写
  该会话缓存（所有流写入本就按 `targetId` 定位，天然安全），切回即见
  完整结果；只有「停止」按钮（只 abort 当前会话）和组件卸载才断开。
  另外在后端重命名 session_id 时同步 map 的 key，否则按新 id 找不到
  controller。
- **人工输入串会话**（`Chat.tsx` + `useChatStream.ts`）：`userInputReq`
  是全局单例 —— 后台会话 A 触发人工输入时，表单显示在当前所在的 B 会话，
  用户提交时 `submitUserInput(currentSessionId, …)` 把答复发给了 **B**，
  后端 A 的阻塞 Future 永远等不到。现在请求带 `session_id`，面板只在其
  来源会话显示，提交也按来源会话发出。
- 回归测试 `sessionSwitchKeepsStream.test.tsx`（2 用例）：切换会话不
  abort、停止只影响当前会话、卸载才 abort 全部。已**反向验证**：把旧
  行为（切会话 abort 全部）注入回去，两用例均变红；还原后变绿。
- 验证：前端 `tsc --noEmit` 0 errors、vitest 107 passed（19 文件）。

### Fixed — 迁移列守卫 + 工具桥悬空实例（2026-11-05）

自查本轮六片工作流的两个遗漏，都是「测试全绿但生产会炸」的类型：

- **迁移 0019 此前零验证**：`test_alembic.py` 只证明迁移链能跑通 ——
  一个 `add_column` 写成空实现、表名写错、或 guard 写反（表存在却 skip），
  链测试依然全绿，线上升级后第一次读写该列才炸。新增
  `test_incremental_migrations_add_expected_columns`：构造「0018 状态的老库」
  （删列 + 版本钉回）再 upgrade head，断言目标列真实存在且可被 SQL 引用。
  已做**反向验证**：故意把 0019 的 guard 改成「表存在就 return」，测试变红
  （报「迁移可能是空实现或 guard 写反」）；还原后变绿 —— 确认守卫有杀伤力。
- **工具桥 `_load_user` 返回悬空 ORM 实例**：`db.get()` 后立即 `db.close()`
  返回的实例仍绑定已关闭会话；`expire_on_commit=False` 只是让当前属性还在，
  任何懒加载/refresh（下游读 `user.role` 做 ACL）都会抛
  `DetachedInstanceError`。改为 `refresh` + `expunge` 后返回游离态实例，
  并补回归测试（断言 `sa_inspect(user).detached is True` 且各列可读）。
- 顺带修 `workflowGraphEditor.test.ts` 的 import 路径：vitest 靠 Vite 别名
  能解析，`tsc` 用真实路径因此一直红；改为 `@/services/...` 别名后
  `npm run lint` 恢复 0 errors。
- 验证：后端 1084 passed（Redis 在线/离线均绿）、ruff 通过；前端
  `tsc --noEmit` 0 errors、vitest 105 passed。

### Added — 工作流结构化编辑器：分类型表单 + 自动布局预览（P0-3 第五片）（2026-11-05）

拆掉「手写 JSON」这个最大使用门槛。刻意**不引入 React Flow**：节点图 DSL
已被 71 个后端测试钉住，编辑器只是同一份 JSON 的可视化外衣 —— 结构化
表单 + 只读自动布局预览覆盖了画布的核心价值（不再手写 JSON、一眼看清
结构），体积与风险小一个量级；真拖拽画布可作为后续增量。

- **分类型参数表单**（`WorkflowGraphEditor.tsx`）：llm/knowledge/http/
  template/condition/human_input/end 各自的字段定义（select/textarea/
  number/json），逐节点编辑；JSON 类参数（headers/fields）本地草稿态
  —— 合法即写入图，非法只提示不丢内容。
- **纯图操作**（导出给单测）：改名级联（同步所有引用边，重名拒绝）、
  删除级联（节点 + 相关边，start 不可删）、加边去重（自环拒绝）、
  参数空值删键。
- **自动布局预览**：BFS 深度分列的只读 SVG（环收敛不炸；孤立节点沉底），
  深浅主题走 CSS 变量。
- **JSON 直编保留**：对话框内一键切换（非法 JSON 时禁止切回结构化模式，
  不丢内容）；保存仍走后端全量校验兜底。
- 验证：新增 12 个前端测试（纯图操作语义 + 布局）；`tsc --noEmit`
  0 errors；vitest 105 passed（18 文件）。

### Changed — 工作流引擎 v2：并行分支 + 屏障暂停 + 快照恢复（2026-11-05）

对齐 Dify/Coze 的并行分支能力。引擎此前是「单路径流」，本片放开
fan-out/fan-in（调度器的汇聚语义本就按多入边设计，缺的只是校验放行、
并发执行与恢复重建）：

- **校验**：非条件节点允许多条出边（≥1）；end 仍禁止出边；condition
  仍必须恰两条 true/false；有环依旧直接拒绝（循环节点需子流程迭代形态，
  单独立项）。
- **并发执行**：就绪的同批节点 `asyncio.gather` 真并行（墙钟测试钉住：
  两个 0.25s 节点 < 0.45s 完成）。批内某节点失败时**其余节点跑完**
  （步骤轨迹完整）再上抛首个 `WorkflowNodeError` —— 失败定位不再丢兄弟
  分支的执行记录。`on_step`/落库是同步块，协程交错不会撕裂会话。
- **人工输入屏障**：human_input 延迟到**其它全部节点终态**（done/skipped）
  才提问，替换 v1 的「并行就绪即报错」；同图多个人工输入按就绪顺序逐个
  提问（恢复后下一个继续）。
- **快照恢复**：恢复改用「节点状态 + 输出」快照（steps_json/context_json
  天然构成），不再依赖执行顺序 —— 并行完成顺序不稳定也能正确重建。
  done 来源的出边按**子节点终态**决定携带（done→携带、skipped→死边、
  答复节点→携带）；答复节点的出边全携带（其下游此前从未执行，靠这里
  入队 —— 初版实现漏了这步，end 永远不会就绪，已被测试钉住）。
- 验证：引擎测试新增 5 个并行用例（汇合/墙钟并发/屏障等待/顺序无关快照
  恢复/批内失败轨迹完整）；工作流相关 71 个测试全绿；后端全量见下方验证
  小节。

### Added — 工作流人工输入进对话：chat 内提问/答复/就地恢复（P0-3 第四片）（2026-11-05）

上片把 `waiting_input` 返回给模型后，普通用户在对话里**没有任何恢复入口**
（只有管理面板能答复）—— 而路线图原文：「人工输入(Human Input)节点是
HITL 产品的天然差异化」。本片把人工输入接进现有的 chat 内
`user_input_required` 机制，形成完整闭环：

- **工具桥**（`workflow_tools.py`）：流程跑到 `human_input` 节点时，工具
  经 `UserInputBlocker.request_input` 阻塞等待，SSE 推
  `user_input_required` 表单（复用外部系统的前端契约 —— **前端零改动**，
  `UserInputPanel` 直接渲染）；用户在聊天里答复 → Future resolve → 工具
  就地恢复跑完剩余节点 → 模型拿到完整结果，**无需二次调用**。同一流程里
  多个人工输入节点逐个提问（while 循环）；无会话上下文（API 直跑）回退为
  waiting 提示。
- **等待期间不持有 DB 会话**：请求输入前显式关闭连接（等待可达数分钟，
  占着会话会耗尽连接池），恢复时重新取会话。工具级 timeout 刻意不设
  （等待时长无法预估），执行段仍由工作流自身节点/总超时兜底；用户断开
  → agent run 取消 → CancelledError 清理 run 行。
- **fields 契约**：human_input 节点可声明 `fields`（key/label/type/
  required/description），经引擎暂停信息 → `workflow_runs.
  waiting_fields_json`（迁移 0019）→ 工具载荷原样透传；未声明时回退
  单行「答复」字段。引擎过滤非 dict 项；API 直跑（无会话）不依赖该列。
- **恢复竞争**：用户已从管理面板恢复时，本会话的抢占失败返回
  `already_resolved` 提示（模型转达用户查看运行记录）。
- 验证：新增 blocker 接线测试（payload 形状/答复后就地恢复产出最终结果）、
  fields 透传（含非 dict 过滤）、无会话回退；工作流相关 61 个测试全绿。

### Changed — 工作流运行异步化：提交即返回 + 后台执行 + 重启收尸（P0-3 第三片）（2026-11-05）

`POST /workflows/{id}/run` 此前同步等流程跑完（总超时下最长 300s+）——
HTTP 请求被挂死，代理网关超时直接断连，且无法看进度。本片对齐
Dify/Coze 的运行形态：

- **端点异步化**：run/resume 提交即返回 `running` 状态的 run，真实执行
  在后台任务（`asyncio.create_task` + 强引用表防 GC）。工具桥**不走**这条
  路径 —— 模型需要最终结果，`service.start_run` 内联执行保持不变。
- **共享执行路径**（`service._execute_run`）：内联与后台同一份状态迁移
  代码（终态必为 succeeded/failed/waiting_input，任何路径不允许把 run
  永远留在 running）；恢复的抢占式改状态与路径重建提前到提交时同步完成，
  失败仍同步回 409。
- **重启收尸**（`startup_cleanup`）：`workflow_runs` 的 running 行标记为
  failed("restart")；`waiting_input` **不收** —— 暂停点持久化在 DB，
  跨重启照常可恢复。
- **工具桥显式超时**：`timeout_seconds = 总超时 + 60s` —— wuwei 对
  None 是无限等待；必须让引擎的优雅超时（落 failed + 步骤轨迹）先到，
  R-14 的 unknown 断路只作最后防线。
- **前端**：运行对话框对 running 状态每 1.5s 轮询 run 详情，到终态自动停。
- 验证：API 测试改用轮询助手（提交→running→轮询终态）；新增收尸测试
  （running 收、waiting_input 不收）与工具超时断言；后端全量
  1073 passed（在线）/ 离线复跑全绿；`tsc --noEmit` 0 errors。

### Added — 工作流挂载为智能体工具 + 管理端最小界面（P0-3 第二片）（2026-11-05）

上片交付了引擎与 API，本片把工作流接进两条使用路径，形成闭环：

- **智能体工具桥**（`app/tools/workflow_tools.py` + factory 注册）：
  每个**已启用**工作流自动挂载为 `run_workflow_<安全名>_<id>` 工具
  （与 MCP 同为动态注册，不进 TOOL_CATALOG；停用即下线）。触发者身份
  从会话 contextvar 透传（知识检索 ACL / 运行记录归属随触发人走）；
  流程跑到 `human_input` 节点时工具正常返回 waiting 信息（run_id +
  提问），由模型转达用户、用户在界面/API 恢复；agent run 被取消时
  标记 run 为 failed 再上抛，不留僵尸 running 行；`side_effect=True`
  强制串行执行。`_get_agent` 缓存键加入工作流签名（id+updated_at 哈希），
  启停/编辑即失效挂载的工具集。
- **管理端最小界面**（`WorkflowManagement.tsx`，v1 刻意不做画布 ——
  节点图 DSL 已被 56 个测试钉住，画布只是同一份 JSON 的可视化编辑器，
  后补零破坏）：列表 / JSON 编辑（后端校验一次性报全部问题）/ 轻量启停
  （新增 `PUT /workflows/{id}/enabled`，不必回传全量图）/ 同步运行 /
  运行记录 / 等待人工输入的一键答复恢复。
- 验证：工作流相关测试 56 个全绿（工具桥 10 个新增：注册唯一性/成功/
  停用/等待输入/失败轨迹/无上下文/签名变化/工厂真实路径）；前端
  `tsc --noEmit` 0 errors。

### Fixed — 测试套件 GC 时序地雷：openai SDK finalizer 让无关用例随机背锅（2026-11-05）

全量跑测试时 `test_intranet_tools::test_submit_tool_requires_approval`
稳定红（`RuntimeError: Event loop is closed`），单独跑却绿。逐层定位：

- **机制**：openai SDK（本环境基于 httpx2）给 `AsyncHttpxClientWrapper`
  定义了 best-effort `__del__` —— 未被显式关闭的 `AsyncOpenAI` 客户端被
  GC 时，`asyncio.get_running_loop().create_task(self.aclose())` 把清理
  任务调度到「此刻恰好活着的任意事件循环」上。套件里大量网关对象在用例
  结束后才被分代回收：aclose 任务跑在别的用例的循环上，传输绑定的却是
  创建者的**死循环**，`transport.close()` 里 `call_soon` 直接炸；异常由
  anyio runner 的 `_raise_async_exceptions` 抛出，落在一个毫无关系的
  异步用例头上。
- **为什么现在才爆**：新增任何测试文件都会移动分代回收的触发点
  （分配计数决定 GC 时机），本次工作流测试模块恰好把回收点移进了
  intranet 用例。根因是既有隐患，与新增内容无关。
- **修复**（`tests/conftest.py`，仅测试进程）：把该 finalizer 钉成
  no-op —— 泄漏客户端随进程退出回收，不再甩锅给无关用例；生产进程
  循环常驻，finalizer 正常工作不受影响。定位过程用了两支一次性探针
  （`gc.get_objects` 存活扫描 + `httpx2.AsyncClient.__init__` 创建点
  堆栈），均已删除。
- 验证：全量 1061 passed 在 Redis 在线/离线两种环境均稳定全绿。

### Added — 工作流引擎 v1（P0-3，竞品路线图最后一个未落地的 P0）（2026-11-05）

`docs/research/竞品调研与改进路线.md` 里的 P0 只剩「工作流画布」没做 ——
本轮落地它的后端（引擎 + 节点 + API），画布 UI 与「打包成智能体工具」
留作下一片（与既有架构不冲突，路线图原文口径）。

- **引擎**（`app/services/workflow/engine.py`，纯计算无依赖，可独立单测）：
  8 类节点 `start / llm / knowledge / http / template / condition /
  human_input / end`；单路径流 + 条件分叉 + 汇聚（skipped 沿链路传播）；
  保存时校验一次报出**全部**问题（环/缺 start/悬挂边/条件出边未标
  true/false/不可达节点）。变量 `{{inputs.x}}` / `{{nodes.<id>.output}}`
  走受限点路径查找（无 eval，无属性链逃逸）；整串恰为一个变量时保类型
  返回（结构化输出不被 stringify）。
- **节点副作用边界**（`nodes.py`）：llm 走 `llm_factory`（role=fast，不占
  对话主力模型）；http 先过 `intranet_policy.check_url`（CIDRS 未配置
  一律拒绝）、禁跟随重定向、剥 `Authorization`/`Cookie`、响应体限额；
  knowledge 复用检索 ACL（按触发者身份）；输出全部限额防撑爆 run 行。
- **DB 编排**（`service.py`）：每步轨迹 + 上下文快照落 `workflow_runs`；
  人工输入节点暂停（`waiting_input`），恢复从 DB 重建 `resume_path` ——
  **不依赖任何内存态，进程重启后照常可续**；`UPDATE ... WHERE
  status='waiting_input'` 抢占式改状态防双重恢复。
- **API**（`/api/v1/workflows`）：CRUD 仅管理员；运行需登录且工作流
  已启用（管理员可跑草稿）；运行记录触发者/管理员可见；恢复接口对
  非等待状态返回 409。节点/整条流双超时（`WORKFLOW_NODE_TIMEOUT_SECONDS`
  / `WORKFLOW_RUN_TIMEOUT_SECONDS`，默认 60s/300s）。
- 验证：新增 46 个测试（引擎 25 + 节点 12 + API 9），全绿；LLM 节点
  端到端走假网关验证 factory 接线，SSRF 拒绝路径不打真实网络。

### Changed — Harness：run 级预算断路 + 流式端点每用户频控（2026-11-05）

对照 Anthropic《Effective harnesses for long-running agents》与
Dify/LibreChat/OpenHands 等平台 2026 年的桌面级能力盘点，本仓库
harness 层（`services/agent/`）有两个真实缺口：

1. **没有任何 token/成本维度的护栏** —— wuwei 3.3.0 自带的
   `BudgetMiddleware`（软阈值告警 + 硬阈值断路）一直没用上。长任务
   绕圈/重试可能烧掉预估 10-20 倍 token，此前只有 `agent_max_steps`
   步数上限兜底。现在 `_build_middleware_stack` 在**栈最前**装配
   预算中间件（超限时省掉本次 LLM 调用）：硬阈值抛 `BudgetExhausted`
   → 上游 runner 转 SSE `error` 事件（`error_type=BudgetExhausted`），
   已生成内容照常落库；软阈值（80%）记一次 WARNING。默认关闭
   （`AGENT_BUDGET_MAX_TOKENS` / `AGENT_BUDGET_MAX_COST_USD` /
   `AGENT_BUDGET_ON_EXHAUSTED`，均见 `.env.example`），管理员按需开启，
   不改变既有部署行为。刻意不把步数放进 Budget：步数超限由 runner
   优雅收尾，放进预算会把优雅收尾变成错误。
2. **`POST /agent/stream` 没有每用户限流** —— `llm_gate` 是全站并发闸，
   单个用户刷运行能把并发配额刷满饿死别人。新增固定窗口频控
   （`AGENT_STREAM_RATE_LIMIT` / `AGENT_STREAM_RATE_WINDOW_SECONDS`，
   默认 30 次 / 5 分钟，管理员豁免，`limit<=0` 关闭），超限返回
   429 + `Retry-After`。Redis `INCR + EXPIRE NX` 实现（`rate_limiter.
   check_window_quota`），Redis 不可用降级进程内计数。

**Fixed**
- 前端错误文案：HTTP 非 2xx（403/429/500）的 FastAPI `{"detail": "..."}`
  包装此前原样展示给用户（错误气泡里出现整段 JSON）。`normalizeAgentError`
  先解信封再归一化；429 文案「运行过于频繁，请 N 秒后再试」直接可读。
  新增 `agentServiceError.test.ts`（5 用例）。
- `orchestrator.py` 一段被编码损坏成 `?????` 的注释恢复（公开发布
  profile 的解析路径说明）。

**Tests**
- 新增 `backend/tests/test_agent_budget.py`：`_build_run_budget` 映射与
  非法配置降级、中间件栈装配位置、BudgetMiddleware 断路/warn/软阈值/
  usage 缺失断路、窗口频控的计数/滚动/关闭、HTTP 层 429 + 管理员豁免。

### Fixed — 图表通道 Redis/内存脑裂 + 测试上下文泄漏（2026-11-05）

本地 Redis 在线时跑全量后端测试，`test_chart_*`、`test_session_artifacts`
稳定红 7 个 —— 顺藤摸瓜挖出一个**生产级 bug**：

- `chart_events.push_chart` 写的是 `session_artifacts._mem_lists` 的
  **进程内别名**，而读侧 `chart_events()` 走 `session_artifacts.read_all`
  （Redis 在线时读 Redis）—— push 落内存、读走 Redis，**图表被静默吞掉**。
  这正是该模块 docstring 里「依赖内部状态导致静默降级（真发生过）」的同款
  坑，迁移到 Redis 持久化时 push 侧漏改。现在 push 统一走
  `session_artifacts.append`（Redis 在线走 Redis，离线退内存），删除
  `_accumulated`/`_emitted` 死别名（a2ui 通道迁移时已用对，仅 chart 漏网）。
- `tests/test_chart_cross_context.py` 在用例里 `_current_session_id.set()`
  但失败时不归零 —— pytest 用例共享主线程上下文，泄漏的 session_id 会让
  **后续所有用例**（如 `test_chart_push`）的 push 走错通道。conftest 的
  autouse `_reset_global_singletons` 现在在每个用例**前后**都把 contextvar
  归零；cross-context 夹具改为按会话 id 显式 `session_artifacts.clear`
  （Redis 在线时只清进程内 dict 挡不住上次失败运行留下的脏数据）。
- 验证：Redis 在线与离线两种环境下全量后端测试均绿。

### Changed — 吉祥物精修：去模板感 + 有生命感的变化（2026-11-04）

用户要求「不要 AI 味，再加点动态或者变化效果」。旧版是亮色渐变 + 完美
圆角矩形 + 对称大眼/腮红/高光 + 匀速无限循环粒子，模板感很重；
`MascotIcons.tsx` 的基础轮廓在 30 个组件里各抄了一遍，改一处要动 30 处。

- **造型**：抽出 `MascotBase`（不对称软耳、不规则团子身体、微歪面罩、
  一笔呆毛）作为唯一基座，**31 个导出名零变更**；五官改简练笔触，去掉
  腮红、瞳孔高光、心形眼/星星眼等符号贴纸；模式图标由 140×100 横向构图
  改为 100×100 正方形 + 右下角低饱和徽章（12/14px 下不再糊成一团）。
- **主题与缩放**：`MascotCompanion` 硬编码的 `white`/`#0f172a`/`#f9a8d4`
  改走 `--mascot-face` / `--mascot-ink` / `currentColor`，深色主题下与图标
  统一；文字字号与间距随 `size` 缩放。旧版轨道粒子半径写死 70px，32px
  尺寸时点会飞到画面外 —— 轨道整体移除后该问题一并消失。
- **动效**：删掉光晕、轨道粒子、庆祝星点、汗滴、飞行小点和
  `repeat: Infinity` 匀速正弦。改用带 `times` 的「动一下 → 停顿很久」节奏：
  不规律双眨、单侧耳朵抽动、呆毛摆动、视线飘移、完成态只跳一次、
  错误态下沉；全部走 `useReducedMotion`。
- **变化**：`RandomMascot` 从「挂载时随机一次」改为按情绪路径漫游，间隔带
  随机抖动、交叉淡入淡出；`MascotCompanion` 状态切换同样改交叉淡入，
  不再有中间空白。`MascotState` 去掉 `animate-pulse` 与组件内动画叠加的
  双层匀速动效，idle 换成会歪头眨眼的好奇脸。
- **无障碍**：装饰性图标统一 `aria-hidden` + `focusable="false"`，
  仅传 `title` 时给 `role="img"`。
- 验证：`npm run lint` 0 errors（无新增 warning）、`vitest run`
  16 文件 / 88 用例全绿（含 `svgUndefinedAttr` 六相位探针）；
  明暗双主题可在 `frontend/mascot-preview.html` 查看全部表情与相位。

> 注：本条中的「一笔呆毛」与「呆毛摆动」已在同日第三轮精修中移除，见下条。

### Changed — 吉祥物第三轮：移除呆毛并重画整体轮廓（2026-11-04）

用户反馈「呆毛好丑，请继续精修优化整个吉祥物」。放大对比后确认根因：
呆毛是全身唯一一条**悬空的细描边**，夹在两只实心耳朵之间像断掉的天线，
与「纯色剪影」的造型语言冲突；单独改成一体小卷毛又会变成「第三只耳朵」。

- **头顶**：彻底删掉 `PATHS.tuft` 与 `TUFT_SWAY`。头顶的性格改由
  `body` 轮廓顶部极浅的不对称起伏承担，全身只剩「实心剪影 + 简练笔触」。
- **轮廓**：耳朵由尖三角改为圆钝软耳（耳尖用 `Q` 收圆、左右倾斜方向不同），
  垂耳版同步重画；身体改为上窄下圆、底部略鼓的小团子；脸罩收窄并略微
  偏移，露出更明显的身体色边框。`MascotCompanion` 复用 `MascotBase`
  自动继承，无需改动调用方。
- **五官**：眼睛统一由正圆点改为微竖椭圆（含 Companion 的陪伴态）；
  思考加蹙眉与眼位高低差、喜欢去掉爱心贴纸改小 w 嘴并加粗、
  出神放大高光点与横扁嘴以区别惊讶、酷的粗弧由 5 降到 4.2、
  眨眼去掉多余的下巴线。12 张脸在 96px 下互不撞脸。
- **动效**：呆毛摆动换成两只耳朵各自偶发抽动（8.5s / 13s 不同周期与
  相位），比单根呆毛规律摆动自然；模式徽章的旋转幅度收敛到 12°/-5°。
- **预览**：`mascot-preview.html` 增加 280/160/96/32px 造型细节区，
  说明文字同步更新；`31 个导出名仍为零变更`。
- 验证：`tsc --noEmit` 0 error、定点 eslint 0 warning、
  `vitest run` 16 文件 / 88 用例全绿；明暗双主题截图控制台 `errors: none`。

### Changed — 吉祥物第四轮：保留骨架、压掉婴儿图式（2026-11-04）

用户提出「再好看点，有点傻，甚至可以不要现在这个形象」。先做了六个形态方向
（墨滴 / 折纸 / 一笔 / 线稿 / 芽）的明暗双主题对比，用户看后决定**保持现有骨架**，
只做精修。因此不再换形象，专门针对「傻」下手。

诊断：「傻」不是某个部件，而是**婴儿图式**（大圆点眼 + 咧嘴笑弧 + 刺眼纯白
脸罩 + 正面完全对称）叠加高饱和配色共同造成的，和上一轮「去呆毛」是两层问题。

- **五官**：新增 `Eye` 组件，眼睛统一收成细长竖眼、眼位上移、做 -9° 同向
  倾斜，不再是「两个正圆点盯着你」；U 形笑弧换成真正平直的短横痕，不笑。
  12 张脸的眼形 / 嘴形同步收敛，96px 下仍互不撞脸。
- **面斑**：再收一圈成上宽下收的软形；`--mascot-face` 由纯白降为低对比冷灰；
  渲染时用 `color-mix(in srgb, currentColor 20%, var(--mascot-face))` 混入
  一点主色，变成与身体同色系的面斑，不再是「贴了张白面具」。不支持
  `color-mix` 的浏览器会回退到 `fill={FACE}` 属性值，不会整块消失。
- **姿态**：整体恒定 -2.5° 侧倾 + 面斑额外 -2.5°，打破正面呆立。
- **试过又撤回**：耳内一片浅色放大后像破洞/脏块，删除；「几乎平的浅弧」因
  圆头线帽仍被读成微笑，改成纯直横。
- `MascotCompanion` 五官同步（细竖眼倾斜 + 平横嘴），复用 `MascotBase`
  自动继承侧倾与面斑；**31 个导出名零变更，所有页面零改动**。
- 验证：`tsc --noEmit` 0 error、`npm run lint` 0 errors（58 条既有 warning
  无新增）、`vitest run` 16 文件 / 88 用例全绿、明暗截图 `errors: none`。

### Fixed — 网站预览串号 / 版本弹窗遮挡 / SVG 非法属性 / 新建对话 404（2026-11-04）

**Security**
- `POST /website/preview-token` 补归属校验。该接口此前只查 dist 是否存在，
  任何登录用户拿到别人的 slug（`data/websites` 目录名可枚举）就能签出有效
  预览令牌看别人的网站 —— serve_preview 只验签名与 slug，分不清令牌是谁替
  谁签的。现在按目录名归属校验（非管理员仅限本人项目，与部署接口同一套
  规则），且归属校验先于 dist 存在性检查，不给响应码差异探测留口子。
- `POST /decisions/{id}/decision` 补归属校验。decision_id 只有 8 位 hex，
  且端点此前不校验调用者身份 —— 任何登录用户知道 id 就能替别人的会话回答
  `ask_user_decision` 决策（写操作，可劫持生成流程走向）。现在创建决策时
  统一登记归属会话（decision_tools/ppt_tools 两个创建点收口到同一入口），
  端点先 `ensure_session_access` 再 resolve。顺带修复
  `cleanup_session_decisions` 全表遍历的误伤：一个会话的流结束会取消
  **所有会话**正在等待的决策 Future，现在按归属过滤。
- 鉴权审计结论：sessions/messages/artifacts/versions/documents/sheets/
  ppt 系列、approvals、export、user-input、api-approval 均已有归属校验
  （`ensure_session_access` / `_ensure_record_owner`），本轮补齐以上两处。

**Fixed**
- **网站预览推错项目（跨会话串号，含跨用户泄漏）**。SSE `artifact_ready` 的
  slug 此前由 `_infer_project_slug_from_tools` 推断，它**完全不看会话**，
  扫全库 `data/websites/` 取「最近修改的 dist」——该目录所有用户共用，
  别的会话甚至别的用户刚构建完，当前用户的首帧预览就会拿到**那个**项目；
  点「刷新」走 `get_latest_website_artifact`（一直按会话过滤）才变回正确的，
  表现为"预览里显示的不是刚生成的网站"。现在按 `u<uid>_s<session>_v<version>`
  目录名只在本会话内取**版本号最大**的（比 mtime 可靠），并可用 user_id 收窄；
  无 session_id 直接返回 None，不留全局兜底。
- **首页智能体选择被重置回「通用助手」**。`Home.tsx` 每次渲染都调
  `getStoredUser()`，而它内部 `JSON.parse` 返回**新对象引用**；该对象被当作
  `loadAgents` 的 useCallback 依赖 → 每次渲染回调换新 → `useEffect` 重跑 →
  重新拉列表后**无条件** `setSelectedAgentProfileId(general.id)`，把用户刚选的
  智能体覆盖掉。现在用惰性 state 只取一次用户（引用稳定），并用 ref 保证
  默认选中只应用一次。回归测试 `pages/__tests__/homeAgentSelection.test.ts`。
- **产物面板「版本」弹窗被预览内容遮挡**。弹窗原先 `absolute` 挂在面板头部，
  而头部 `backdrop-blur` 形成包含块 + 面板根 `overflow-hidden`，`z-50` 逃不出去。
  改为 `createPortal` 挂到 `body`（fixed 定位，空间不足自动上翻）。
  新增真实浏览器 e2e 护栏（`tests/website-version-bar.e2e.ts`）：断言点历史
  版本条目后弹窗必须真的关闭（用 `aria-expanded` 判定）——遮挡存在时 tap 落在
  遮挡物上、弹窗关不掉，用例必红。已用 HEAD 旧实现反向验证过杀伤力
  （红 → 修复后绿）。种子脚本：`scripts/seed_website_version_bar_e2e.py`。
- **控制台刷 `<circle> attribute cx/cy: Expected length, "undefined"`**。
  motion v12 对 SVG 属性 `animate={{ cx: [...], cy: [...] }}` 会先按静态值写
  属性再解析关键帧，中间态发出 `setAttribute('cx', undefined)`，报错栈落在
  motion-vendor chunk，极难定位。`MascotCompanion` 瞳孔游走改为 `x/y` 位移
  （视觉等价），星点/汗滴/施工点补 `initial`；新增 setAttribute 探针回归测试
  覆盖全部 6 个相位。
- **新建对话首轮 GET /messages 404「会话不存在」刷报错**。前端新建对话先造
  本地会话（`Date.now()-random` id），`loadSessionMessages` 回源跑赢了后端
  落库。现在 404 视为正常竞态静默返回（本地已持有完整消息）。
  注意：**不能**改成"仅对后端已知会话回源"的前置守卫——页面刷新恢复时
  回源与会话列表加载并发，守卫会误跳过，缓存剥离掉的 artifact HTML 补不
  回来，预览面板无法恢复（部署实测踩过）。

### Changed — 升级 wuwei 3.0.2 → 3.2.1（2026-10-28）

上游 3.2.1 把 3.0.2 时代的一批流式缺陷修掉了（详见
`docs/upstream/wuwei-3.0.2-问题清单.md` 顶部的对照表）。本节记录本次升级的适配动作。

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

对接真实企业网关（企业网关 `gw.example.com`）时暴露的五类硬伤与对应抽象。这一批改动
不是「多支持一家厂商」，而是**把「标准 OpenAI 兼容」这个隐含假设拆掉**，让提供商层
在真实内网网关上也成立。

- 新增 `services/llm_providers/presets.py`：`ProviderPreset` / `LoginFlow` /
  `TransportOptions` / `ProbeSpec`，内置 企业网关预设。厂商差异从代码里的
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
  「请求体里要填的模型名」经常不是同一个东西（企业网关 `qwen3.6-35b` vs
  `Qwen3.6-35B-A3B`），手填只能等到 404 `Model Not Exist`。现在能从上游同步清单
  （企业网关的公开注册表 / 标准 `/models`）、可选、可校验。
- **按用途绑定模型**：`extra.roles` 把 chat / reasoner / fast / vision / image 映射到
  具体模型，`llm_factory` 与 `agent/factory` 支持 `role`。缓存键改用「解析后的模型名」
  而不是 `provider.model`，否则改完绑定会一直复用旧 agent。
- **路径前缀由 `base_url` 吸收**：企业网关把接口挂在 `/agents/gateway` 而不是 `/v1`，
  SDK 会自己拼出 `/agents/gateway/chat/completions`（已用真实 SDK 验证）；响应体是
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

### 计划中（见 `docs/plans/development-plan-v2.md`）

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

来自 `docs/reports/测试报告-2026-10-01.md`（48 通过 / 0 阻塞），三轮共修复 12 项：

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
