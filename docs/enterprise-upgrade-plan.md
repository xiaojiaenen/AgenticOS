# AgenticOS 企业级升级方案

> 2026-09-30 · 基于 9/30 代码审查结论编写
> 范围：UI 库评估与 Chrome 85 兼容 / GenUI 选型 / 自研轮子替换 / 微服务化 / 并发性能 / 企业权限

---

## 一、前端 UI 现状与重构成本

### 1.1 现状结论：纯自研，无任何组件库

- `frontend/src/components/ui/` 共 **22 个组件、约 2568 行**，全部手写（Button/Input/Modal/Toast/Tooltip/Badge/Skeleton/Card/EmptyState 等），package.json 中没有任何 UI 组件库（无 radix/shadcn/antd/MUI）。
- 视觉体系核心是 `src/index.css`（1176 行）：`@theme` 定义约 **110 个自定义 token**（品牌色、语义色、6 档圆角、8 档双层阴影、玻璃体系），加上 `html.theme-liquid-glass` 类切换的多主题机制和大量 `!important` 覆盖。
- 有一个私有依赖 `@xiaojiaenen/liquid-glass`（玻璃拟态）。
- **最大短板不在已有组件，而在缺失的复杂件**：admin 后台（7876 行）里 20+ 处原生 `<select>`、手写 `<table>`、手写表单校验、无 Tabs/Drawer/DatePicker/Combobox。重复样板远多于组件本身。

### 1.2 重构为"好看的 UI 库"的成本

**推荐路线：引入 shadcn/ui（Radix 无头件 + Tailwind），不是"换库"而是"补库"。**

| 方案 | 工作量 | 说明 |
|---|---|---|
| **A. shadcn/ui 增量引入（推荐）** | **3~4 人周** | shadcn 组件直接用现有 Tailwind token 定制主题，自研 22 个组件**全部保留**，只补缺失的 Select/Table/Tabs/Drawer/DatePicker/Form(react-hook-form+zod)。先迁移 admin 后台（收益最大），chat 页不动 |
| B. Ant Design 5 全量替换 | 6~10 人周 | 与现有玻璃拟态视觉体系冲突大，`!important` 覆盖体系会加倍复杂，admin 需全部重写 |
| C. 完全自研扩库 | 不推荐 | 现状已证明维护成本高（22 组件双主题分支、focus trap 手写） |

方案 A 的理由：Radix 是无头组件（只管交互/无障碍，不管样式），现有 `cn()` 工具（clsx + tailwind-merge）就是 shadcn 的标准搭配，视觉零妥协，且 React 19 兼容。

### 1.3 Chrome 85 兼容：真正的拦路虎是 Tailwind 4，不是组件

**关键事实（实测构建产物）**：
- JS 层没问题：legacy 插件 targets Chrome 80 + regenerator-runtime，JS 在 Chrome 85 可跑。
- **CSS 层实际下限是 Chrome 111**：构建产物 `index-*.css`（222KB）中 `oklch(` 出现 112 次、`color-mix(` 487 次——两者均需 Chrome 111+。这些几乎全部来自 **Tailwind 4 的默认调色板**（slate/rose/emerald/amber 等），自研 token 本身都是 hex/rgba 没有问题。
- `@property` 69 次恰好 Chrome 85 支持，backdrop-filter 有 `@supports` 降级。

**修复成本对比**：

| 路线 | 成本 | 风险 |
|---|---|---|
| **A. 覆写 Tailwind 默认调色板为 hex（推荐）** | **2~4 人天 + 回归** | 在 `@theme` 中用 hex 重定义用到的 slate/rose/emerald/amber 等色阶（约 8 个色系 × 11 档），去掉 index.css:497 唯一一处 color-mix，构建后 grep 确认产物无 oklch/color-mix。风险低，视觉可保持一致 |
| B. 降级 Tailwind 3.4 | 1~2 人周 | `@theme`/新特性全要改写，1176 行 index.css 大改，**不推荐** |

补充：chromium 内核老版本（Win7 Chrome 109 及以下）同理受益于路线 A；路线 A 完成后 CSS 下限约到 Chrome 85~90（`@property` 是 85+，`@supports` 用法已兼容）。

---

## 二、GenUI 库选型（搜索结论）

主流开源 GenUI（生成式 UI）方案：

| 库 | 定位 | 与本项目的契合度 |
|---|---|---|
| **Vercel AI SDK** | 底层流式/工具调用协议，多数 GenUI 方案的地基 | 协议层参考价值高；但它绑定自家 useChat 协议，替换现有 SSE 协议成本大 |
| **assistant-ui** | ChatGPT 式对话线程组件库（TS/React） | 可作为 chat 页 UI 参考，深度集成需适配其 runtime |
| **CopilotKit / AG-UI** | 完整 agent 前端集成 + AG-UI 事件协议（含审批/状态同步事件） | **AG-UI 协议与本项目 SSE 协议（approval_required/artifact_ready/run_status）设计高度同源，建议作为协议演进参考**；直接引入需后端适配 AG-UI |
| **Ant Design X** | 蚂蚁的企业级 AI 组件套件 | 中文生态、企业场景契合；若走方案 A 可单独取其部分思路 |

**建议**：现阶段**不引入**任何 GenUI 框架（它们都假设你可改前后端协议，且默认样式栈是现代 Tailwind，与 Chrome 85 目标叠加后集成成本翻倍）。分两步：
1. **短期**：借 AG-UI 协议的事件模型梳理自己的 SSE 协议，保持私有协议但字段命名向 AG-UI 靠拢，保留未来接入的可能。
2. **中期**：若 chat 页要做"生成式卡片"（PPT 大纲卡片、知识库引用卡片等），用自研的 `__ECHART_JSON__` 标记协议扩展即可（已有 ChatMessageSubComponents 这套机制），不需要框架。

Sources: [AI SDK 文档](https://ai-sdk.dev)、[CopilotKit AG-UI](https://whyire.com)、[对比综述](https://cp0x.com)

---

## 三、自研轮子排查：应换 / 应留清单

### 3.1 应换（有更成熟方案的自研，按优先级）

| # | 模块 | 问题 | 替换方案 | 优先级 |
|---|---|---|---|---|
| 1 | **登录限流**（auth_service.py:75-137，MySQL 表状态机） | 先读后写的竞态，并发下限流不准；有 Redis 却用 DB 做限流 | 用现有 cache_service 的 INCR 模式（cache_service.py 场景 2 已是现成实现）或 fastapi-limiter | **P0** |
| 2 | **safePreview 的正则 sanitizeHtml**（lib/safePreview.ts:66-80） | 正则剥 `<script>` 有绕过面 | **DOMPurify**（3KB，标准方案） | **P0** |
| 3 | **svg_editor Flask 旁路**（services/ppt/svg_editor/server.py，674 行） | Flask 应用嵌在 FastAPI 项目里，未 mount、无人引用，含 sys.path hack | 迁 FastAPI Router 或确认废弃后移除 | P1 |
| 4 | **fetch 封装不统一**（apiClient.ts 只有 29 行且 10+ 处绕过） | 50+ 处重复错误处理 | 升级 apiClient（401 统一处理/超时/拦截器）并统一调用点 | P1 |
| 5 | **知识库 BM25**（knowledge/retrieval.py:270-320） | 手写中文 bigram 分词（召回损失）+ `df=1` 的 IDF 近似（评分有偏）+ 全量内存计算 | 数据量大：PostgreSQL tsvector / jieba 分词 + rank_bm25；数据量小：保留但修 IDF | P2（看数据量） |
| 6 | **SSE 客户端解析**（agentService.ts 手写 ~100 行） | 无 `id:`/`retry:` 支持，重连逻辑手造 | `@microsoft/fetch-event-source`（支持 POST+鉴权 header，正是手写的原因） | P2 |

### 3.2 应留（看似轮子、实为正确形态）

- **memory_bm25.py**：不是手写 BM25，是 SQLite FTS5/MySQL FULLTEXT 的薄抽象层——正确。
- **memory_vector_store.py**：用的就是 Redis Stack RediSearch（HNSW+余弦），这层是正确用法而非轮子。
- **cache_service.py**：是 Redis 数据结构运用（ZSet 补全/INCR 限频/Pub-Sub），不是缓存轮子。
- **approval_manager.py**：HITL 与 SSE 会话耦合，无现成替代品。
- **services/upstream/**（Playwright cookie 登录）：领域专用，无通用库；建议抽独立包与 sesame 项目共享。
- **services/ppt/ SVG↔PPTX 转换链（~15000 行）**：无成熟开源方案，是产品核心壁垒，**必须保留**。
- **frontend 会话缓存/datetime.ts/markdown 图表标记协议**：体量小或领域特殊，替换成本 > 收益。
- **wuwei 框架**：已是"用框架 + 薄定制"的正确形态。

---

## 四、微服务化 + 并发性能 + 企业权限方案

### 4.0 先说结论

**几百人并发 ≠ 需要微服务。** 当前架构（FastAPI 单体 + arq worker + Redis + MySQL）经第 0 阶段改造后可支撑 500+ 并发在线。微服务建议只拆两处真正有伸缩差异的部分（agent 运行时、任务执行），其余保持模块化单体。盲目微服务化在当前团队规模下会增加 3~5 倍运维复杂度而没有收益。

### 4.1 阶段 0：单体优化（支撑目标的一步，1~1.5 月）

**目标：500 并发在线、100 并发 SSE 长连接、P95 首字 < 2s。**

1. **无状态化**（水平扩展的前提）
   - 会话/审批/在线用户已走 Redis（cache_service）✅；排查剩余进程内状态：`agent_service` 的 TTLCache（跨实例失效即可接受）、`memory_pipeline._turn_counts`（已加 LRU，改 Redis 计数可选）
   - SQLite 确认仅限开发，生产必须 MySQL/PostgreSQL
2. **SSE 长连接层**
   - uvicorn 部署参数：`--workers N` + 独立连接数压测；nginx 反代层 `proxy_buffering off`、`proxy_read_timeout` 调大
   - SSE 流式期间的 DB 短会话轮询（session_storage）合并/降频——SSE 请求期间应几乎不占连接池
   - 连接池从 `pool_size=5, max_overflow=10` 提到按压测结果配置，并区分"SSE 通道"与"普通请求"
3. **数据库**
   - 补复合索引：`agent_usage_events(user_id, created_at)`、`(session_id, created_at)`（dashboard 核心查询目前会全表扫）
   - 读写分离留到有真实瓶颈再做，先加慢查询日志
4. **缓存**：dashboard 统计接口加 30s Redis 缓存；知识库 wiki 页面 BM25 加载改为启动时缓存 + 失效刷新
5. **LLM 网关**：对 OpenAI 上游做全局并发信号量 + 队列，防止几百人同时触发把上游打挂或费用失控；`memory_pipeline` 的后台 LLM 调用已有信号量（本次已加），跨实例共享计数可选 Redis
6. **前端**：本次已做（chunk 拆分 -2MB、流式渲染解耦）；补 react-virtuoso 长消息列表虚拟化（依赖已装未用）

### 4.2 阶段 1：轻量拆分（2~3 月，与业务并行）

不拆"微服务"，拆"可独立伸缩的部署单元"：

```
┌─ nginx ──────────────────────────────┐
│  /api/chat-stream → agent-service ×2~4   (SSE 长连接，CPU/连接数敏感)
│  /api/*           → core-api ×2          (普通 CRUD，IO 敏感)
│  /admin           → core-api
└──────────────────────────────────────┘
     │ 共享：MySQL(主) + Redis(会话/审批/队列/缓存) + 对象存储(网站产物/PPT)
     └─ arq worker 池 ×N（website build / 邮件 / 记忆蒸馏，按队列名分池）
```

- **agent-runtime**：现在就是独立代码路径（agent_service + wuwei），只是部署上单独起进程组，代码不动
- **worker 池**：arq 已支持按 queue name 分池（website 任务重、通知任务轻），compose 里把 worker 按队列拆 2~3 个服务
- 这一步之后如果某单元真遇到伸缩墙（通常是 agent-runtime 的 LLM 并发或 worker 的 npm build），再考虑把该单元独立成仓库/服务——**演进式微服务，不一步到位**

### 4.3 阶段 2：企业权限管理（1.5~2 月）

现状：只有 `user/admin` 两个角色（`get_current_user`/`require_admin`），已有 LDAP 登录开关（`LDAP_ENABLED`），无资源级权限。

**方案：Casbin(RBAC + 域) + 部门树 + 资源级 ACL**

1. **模型**（Casbin `keymatch + rbac`）：
   - 角色：`admin / dept_admin / user`，可自定义角色
   - 组织架构：LDAP 同步部门树（现有 `ldap_auth_service.py` 扩展），用户-部门多归属
   - 资源权限：知识库（**按部门隔离**——这是企业场景第一刚需）、Agent Profile 发布范围（现有 `allowed_users` 机制扩展为可见性规则）、外部系统（现有凭据体系加角色）
2. **接入点**：FastAPI dependency `require_permission("kb:read", resource_id)` 替代散落的 `require_admin`；数据行级过滤在 service 层统一注入（避免每个端点手写）
3. **SSO**：保留 LDAP 网关之外增加 OIDC（企业微信/飞书/Keycloak），发本系统 JWT 不变
4. **审计日志**：`audit_logs` 表（who/when/what/resource/result），审批决策、管理员操作、知识库读写全部落审计；复用现有 `agent_usage_events` 的写入管道
5. **密钥管理**：环境变量密钥收敛到 Docker secrets / Vault；`external_system_encryption_key` 与 `AUTH_SECRET_KEY` 强制分离（config 已支持，改成必填校验）

### 4.4 里程碑与人力

| 阶段 | 内容 | 工期（1 后端 + 1 前端） |
|---|---|---|
| M0 | P0 轮子替换（限流/DOMPurify）+ Chrome 85 hex 调色板 + shadcn 补 admin 复杂件 | 2 周 + 3 周 |
| M1 | 阶段 0 性能优化 + 压测（locust 脚本：登录/聊天/管理页三场景） | 3~4 周 |
| M2 | 部署单元拆分（agent-runtime / worker 分池）+ 双实例蓝绿验证 | 3 周 |
| M3 | Casbin 权限 + 部门树 + 审计日志 + OIDC | 5~6 周 |
| M4（可选） | GenUI 卡片体系（借 AG-UI 协议）+ SSE 客户端换库 | 3 周 |

---

## 五、附：本次调查的证据基础

- 前端 UI：`components/ui/` 22 组件 2568 行全自研；admin 7876 行含 20+ 原生 select；`index.css` 1176 行 / 110 token；构建产物实测 oklch×112、color-mix×487、@property×69
- 自研轮子：详单见第三节，核心判断"DB 限流、正则 sanitize、Flask 旁路"三处应换，PPT 转换链必须保留
- GenUI：Vercel AI SDK / assistant-ui / CopilotKit(AG-UI) / Ant Design X 四家主流，建议借协议不引框架
