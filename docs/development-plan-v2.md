# AgenticOS 开发计划 v2

> 2026-09-30 定稿 · 取代 `docs/enterprise-upgrade-plan.md` 中与之冲突的部分（该文档保留作为背景调查与证据附录）
> 已确认决策：① 前端组件全量替换为 shadcn/ui，**不保留**现有样式与色板，删除玻璃拟态；② Chrome 85 优雅降级（新浏览器完整样式，85 不残缺）；③ 生产数据库为 MySQL（不引入 PG）；④ 第 3.1 节自研轮子替换全部落地；⑤ agent_service 拆分 / alembic / tsconfig strict 纳入本计划。

---

## 第一部分：前端企业级重构

### 1.1 设计系统（全新，不复用旧色板）

**设计原则**：中性灰阶为骨、单一强调色为魂、内容优先、动效克制。参考 Linear / Vercel / Notion 的企业级审美。

| 维度 | 决策 |
|---|---|
| **色板** | 基础灰阶 `zinc`（比 slate 更中性的企业感）；主色 **indigo-600 `#4f46e5`**（CTA/焦点/选中态），hover indigo-700，浅底 indigo-50；语义色 success `emerald-600` / danger `red-600` / warning `amber-500` / info `sky-600`。全站强调色只允许出现在这三类场景 |
| **暗色模式** | 一等公民，`class` 策略（`.dark`），token 全部走 CSS 变量，shadcn 主题（`--background/--foreground/--primary/...`）双套定义，跟随系统 + 手动切换 |
| **字体** | Inter（拉丁）+ system 中文栈（PingFang SC / Microsoft YaHei）；字号阶梯 12/13/14/16/20/24/30；正文 14px，行高 1.6。仅两档字重（500/600），全局禁用 700+ |
| **圆角/阴影** | 控件 8px、卡片 12px、弹窗 16px；阴影三层（sm/md/lg）各为单层柔和投影，去掉旧的双层堆叠体系 |
| **间距** | 8pt 网格；页面栅格：sidebar 240px + 内容区 max-w 1280px 居中 |
| **边框** | 统一 `1px solid var(--border)`，浅色 `zinc-200` / 暗色 `zinc-800`，层级靠背景色阶（`zinc-50→100→white`）区分而非阴影堆叠 |

### 1.2 技术栈

| 类别 | 选型 | 说明 |
|---|---|---|
| 组件库 | **shadcn/ui（Radix）** | Button/Input/Select/Combobox/Dialog/AlertDialog/Sheet(Drawer)/Tabs/Popover/DropdownMenu/Tooltip/Switch/Checkbox/RadioGroup/Skeleton/Breadcrumb/Pagination/Command(⌘K)/Calendar+DatePicker |
| 表格 | **TanStack Table + shadcn Table 样式** | admin 全部列表：排序/筛选/列显隐/分页 |
| 表单 | **react-hook-form + zod** | zod schema 与后端 Pydantic 对齐；登录/注册/所有 admin 表单 |
| Toast | **sonner** | 替换手写 Toast 单例 |
| 图标 | lucide-react 保留 | |
| 动效 | motion 保留（微交互）/ **背景动画见 1.4** | |
| 图表 | recharts（admin）+ echarts（聊天内代码块）保留 | |
| 状态 | zustand 保留；服务端状态引入 **TanStack Query** | 替代散落的手写 loading/error state，admin 数据页收益最大 |
| 删除 | `@xiaojiaenen/liquid-glass`、`useIsGlassTheme` hook、`MascotIcons` 玻璃分支 | 玻璃拟态全删 |

### 1.3 玻璃拟态删除清单（连带解决旧债）

- 删 `@xiaojiaenen/liquid-glass` 依赖及 vite alias（vite.config.ts）
- 重写 `src/index.css`：1176 行 → 预计 ~300 行（纯 token + 少量语义 class），删除全部 `!important` 覆盖和 `.glass-*`
- 删除所有组件里的 `isGlass ? A : B` 双分支——**ChatMessage 双主题 JSX 合并（~70 行重复）随之自然消失，无需单独重构**，此项从旧计划划掉
- 吉祥物（MascotCompanion/MascotState）：保留品牌形象但重绘为扁平风格（工作量 1~2 天，若设计资源不足可先降级为 lucide 图标 + EmptyState 插画）

### 1.4 背景动画（克制）

- **范围**：仅登录/注册页与 Home 首屏；admin 与 chat 页**纯静态**背景（企业后台不动效）
- **方案**：`ogl` 已在依赖中，做单一极简 shader 背景（低饱和 indigo 渐变网格/aurora，透明度 <8%，速度极慢）；备选纯 CSS：超大径向渐变 + 细点阵（零 JS 成本，Chrome 85 完美支持）
- **约束**：`prefers-reduced-motion` 全部静止；WebGL 不可用（老设备/无 GPU）自动降级为 CSS 渐变；禁止粒子飞舞/视差滚动等花哨效果

### 1.5 Chrome 85 优雅降级策略

原则：**新浏览器完整体验，Chrome 85 渲染同一设计、只少无关紧要的增强**。

1. 所有自定义 token 用 **hex/rgba**（不用 oklch）；Tailwind 4 默认调色板在 `@theme` 中用 hex 全量覆写（构建产物 grep 断言：`oklch(` 与 `color-mix(` 计数为 0，进 CI）
2. `color-mix()` 场景改用预计算好的静态色值
3. `backdrop-filter` 随玻璃拟态删除，不再需要 `@supports` 降级
4. 保留 `@vitejs/plugin-legacy`（targets chrome80）+ regenerator-runtime；统一 browserslist 与 legacy targets 为 `Chrome >= 85`
5. 已知可接受的 85 降级点：`@supports` 内的 `:focus-visible` 细节样式、CSS `scroll-behavior:smooth`、CSS 嵌套（构建期已编译，无影响）——**无视觉残缺**
6. 验收：Chrome 85（可配 Playwright + 旧 chromium）跑通登录→聊天→admin 冒烟截图对比

### 1.6 UX 规范（全站统一）

- 加载：骨架屏（shadcn Skeleton）优先于 spinner；表格用 `TableSkeleton`
- 空态：每页 EmptyState 带下一步动作按钮；错误态带"重试"
- 反馈：所有异步操作有 sonner toast；破坏性操作走 AlertDialog 二次确认（复用现有 useConfirm 语义）
- 键盘：`⌘K` 全局 Command 面板（导航/会话搜索）、表格行可聚焦、Modal 焦点圈（Radix 自带）
- 响应式：admin ≥1280 优化，1024 可用，移动端仅保证聊天与首页

### 1.7 迁移顺序（每步可独立上线）

1. **地基**（1 周）：新 token 体系 + shadcn 初始化 + hex 覆写 + legacy targets 统一 + 删玻璃依赖（页面暂以旧样式跑在新 token 上）
2. **admin 全量**（2~3 周）：7876 行中重复样板最多的区域，收益最大——TanStack Table + shadcn 表单替换全部原生 select/table/手写校验
3. **认证 + Home**（1 周）：新背景动画落地、登录/注册换 shadcn + zod
4. **chat 页**（2 周）：保留消息流/Artifact 核心逻辑，仅换壳；SSE 与状态管理不动
5. **收尾**（0.5 周）：删旧 `components/ui` 中被替代的组件、global lint + Chrome 85 验收

总工期 **6.5~7.5 周**（1 前端全职，设计稿可先用 shadcn 默认主题 + 本设计系统配置直出）。

---

## 第二部分：后端自研轮子替换（原 3.1，全部落地）

| # | 项 | 方案 | 工期 |
|---|---|---|---|
| 1 | 登录限流竞态（auth_service.py:75-137 MySQL 表状态机） | 迁移到 Redis 原子 INCR 固定窗口（复用 cache_service 模式），`auth_rate_limits` 表保留一版兼容后废弃；**注意 MySQL 环境 Redis 为必选依赖，需在部署文档标注** | 2 天 |
| 2 | safePreview 正则 sanitize → **DOMPurify**（前端） | `dompurify` 3KB，替换 sanitizeHtml 正则实现；iframe 沙箱预览架构保留 | 1 天 |
| 3 | svg_editor Flask 旁路 | 迁为 FastAPI APIRouter（保留人工精修流程）；删除 Flask 依赖 | 2 天 |
| 4 | fetch 封装统一 | apiClient.ts 升级（401 统一跳登录/超时/错误归一化），前端全部 service 迁移到统一实例——**与前端重构第 4 步合并做** | 2 天 |
| 5 | 知识库检索（不引 PG） | 中文分词 bigram → **jieba**；BM25 落 **MySQL FULLTEXT `WITH PARSER ngram`**（5.7.6+ 原生支持中文 ngram），淘汰 Python 内存 BM25；SQLite 开发环境保留现有实现作为 fallback（`memory_bm25.py` 的抽象层直接复用） | 4~5 天 |
| 6 | SSE 客户端 → `@microsoft/fetch-event-source` | 与前端 chat 重构合并 | 1 天 |

---

## 第三部分：后端架构重构

### 3.1 agent_service.py 拆分（2312 行 → 5 个模块）

```
app/services/agent/
├── factory.py       # AgentFactory：Agent/中间件栈/工具注册表构建（现 _get_agent/_build_*）
├── orchestrator.py  # StreamOrchestrator：stream_chat SSE 编排、事件泵、keepalive
├── artifacts.py     # ArtifactFactory：PPT/website 工件创建、HTML 内联、PPTX 导出
├── prompts.py       # design/website catalog 注入文案（现 _inject_* 硬编码 prompt）
└── service.py       # AgentService 门面：保持现有公共 API 签名不变，内部委托上述模块
```

约束：
- **公共 API 零变更**（`agent_service.get_agent_service()` 签名保留），endpoints/tests 无感
- monkey-patch `_patched_stream_events` 移入 factory 并加注释标记 tech-debt，等 wuwei 上游支持后删除
- contextvar 六件套收敛为一个 `AgentCallContext` dataclass（dataclass + contextvar 单点定义），approval_manager 改读 context 对象
- `_inject_design_catalog` 的主题文案移到配置文件（`app/resources/prompt_catalogs/*.md`）
- 顺手项：会话创建三段独立事务合并为一个；`_last_quality_errors` 共享实例状态改 per-session

工期：**5~7 天**（含 84 个存量测试全绿 + 新增拆分模块单测）。

### 3.2 Alembic 引入（替代手写迁移）

1. `alembic init` + `env.py` 接 `app.db.session` 的 engine 与 `Base.metadata`
2. **对现有生产库 baseline**：`alembic stamp head`（现库 schema 由 create_all + 兼容层生成，不回填历史迁移）
3. 删除 `_ensure_compatible_schema()`（session.py:104-318），其职责由 alembic 接管
4. 此后所有 schema 变更走 `alembic revision --autogenerate`，CI 里加 `alembic upgrade head` 空库验证 + 与 models 对比 diff 为空的守卫
5. 部署顺序约定：先跑迁移再起新版本容器（compose backend 加 `command` 前置 migrate 或 entrypoint 脚本）

工期：**2~3 天**。

### 3.3 tsconfig strict 渐进开启

一次性全开预计爆出数百个错误（`any` 集中在 markdown 渲染组件与旧 admin 页），采用**渐进门禁**：

1. 开 `"strict": true`，同时用 `tsconfig.strict.json`（extends 主配置）+ `// @ts-nocheck` 暂时圈住存量文件——新文件默认全严格
2. 与前端重构同步逐页"清零"：admin 迁移完一个页面就去掉该页 `@ts-nocheck`
3. 收尾（计划第 5 步）后全仓无 `@ts-nocheck`，主 tsconfig 直接 strict，CI 生效
4. 附带：`noUncheckedIndexedAccess`、`noUnusedLocals` 在 chat/admin 清零后开启

工期：嵌入前端重构各阶段，独立工作量约 **3 天**。

---

## 第四部分：性能 / 微服务 / 权限（沿用 enterprise-upgrade-plan.md，决策补充）

- 微服务策略不变：**阶段 0 单体优化 → 阶段 1 部署单元拆分**，生产库确认 **MySQL**（读写分离也用 MySQL，不引 PG）
- 限流、知识库检索均按第二部分调整为 Redis + MySQL ngram 方案
- Casbin 权限、审计日志、OIDC SSO 工期不变（M3）
- 新增依赖本计划的前置项：**MySQL ngram FULLTEXT 需确认生产实例版本 ≥5.7.6 且 `ngram_token_size` 配置（默认 2，适配中文二元）**

---

## 里程碑总表

| 里程碑 | 内容 | 前置 | 工期 | 验收标准 |
|---|---|---|---|---|
| **M0** | 前端地基（token/shadcn/Chrome 85）+ 轮子替换 #1/#2/#3 | 无 | 2 周 | CI 断言产物无 oklch/color-mix；限流压测原子性通过 |
| **M1** | admin 全量重构（shadcn + TanStack Query/Table）+ tsconfig strict 清零 admin | M0 | 3 周 | admin 无原生 select/table；tsc strict 通过 |
| **M2** | agent_service 拆分 + alembic 引入（后端线，可与 M1 并行） | 无 | 2 周 | 84 测试全绿；alembic upgrade 空库可跑通 |
| **M3** | 认证/Home 重构 + 背景动画 + Chrome 85 截图验收 | M0 | 1.5 周 | Chrome 85 冒烟通过 |
| **M4** | chat 页重构 + fetch 统一 + SSE 换库 + strict 清零全仓 | M1/M3 | 2.5 周 | 全站无 @ts-nocheck；SSE 长跑 1h 无泄漏 |
| **M5** | 知识库 jieba + MySQL ngram 迁移 + 检索效果回归 | M2 | 1.5 周 | 中文召回率对比基准不下降；MySQL 环境检索 <50ms |
| **M6+** | 阶段 0 性能优化 → 压测 → 部署单元拆分 → Casbin 权限（按原方案） | M2 | 6~8 周 | locust 500 并发 P95 达标；权限矩阵评审通过 |

总工期：**M0~M5 约 12 周**（前后端各 1 人并行时），M6 之后按原 enterprise-upgrade-plan 推进。

---

## 风险与依赖

1. **MySQL ngram**：生产 MySQL 版本需确认；若为 5.6 需先升级
2. **Redis 变为必选**：限流迁移后生产不可再走 in-memory fallback（单实例内存限流在多 worker 下不准）——部署文档必须标注
3. **旧 UI 一次性切换的回归面**：以"页面迁移完成才删旧组件"控制，任何时刻主干可发布
4. **吉祥物品牌资产**：重绘或降级需设计资源确认（默认降级为 lucide 图标）
5. **Chrome 85**：mermaid/echarts 新版本对老内核的支持需在 M3 实测，必要时锁定 echarts 5.x / mermaid 10.x 并验证
