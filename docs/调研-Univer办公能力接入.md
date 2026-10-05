# 调研报告：Univer 接入 AgenticOS

> 2026-10-05 · 调研对象 [dream-num/univer](https://github.com/dream-num/univer) v1.0.3
> 结论摘要：**可以接，但只能接一半，而且必须在 Chrome 88 以上才成立。**
> 建议路径见 §7，AgenticOS 侧改动清单见 §6。

---

## 一、TL;DR（先看这五条）

1. **Univer 是 Apache-2.0 的表格/文档引擎，不是完整办公套件。** 图表、透视表、xlsx 导入导出、打印、协同、版本历史**全部是商业版 Univer Pro**，不在开源仓库里。开源仓库 60 个包，grep `chart|pivot|xlsx|print|collabor|license` 结果为空。
2. **Chrome 85 是硬伤。** Univer 官方支持线是 **Chrome 88+**，我们项目的硬约束是 Chrome 85（Win7 内网）。实测产物：`Intl.Segmenter`（Chrome 87）被强依赖；CSS 里 `:where()` 用了 213 次，其中 **176 次是暗色模式规则**——Chrome 85 全部失效，深色模式下编辑器会花掉。
3. **前端包体约 1.7 MB gzip**，且默认不代码分割。对比现有最大 chunk：`echarts-vendor` 1.1 MB。
4. **Agent 侧 100% 开源可用，而且很便宜。** Node 无头运行时能读写单元格、跑公式，不需要任何 DOM shim。官方给的 agent 交互面（inspect / execute / screenshot / api 检索）全部是 OSS。
5. **和现有 PPT 体系不冲突也不互相替代。** Univer 的幻灯片导出是 Pro，我们已有的 SVG→PPTX 转换链（`python-pptx` + 自研 DrawingML，约 27000 行）是产品壁垒，不要动。

**一句话建议**：接**表格（Sheet）**这一个能力，做成新的 agent 产物类型；图表继续用现有的 ECharts 管线渲染后贴进表格；xlsx 导出自己写；**Chrome 85 上直接不提供这个功能**，前端做能力探测优雅降级。

---

## 二、Univer 是什么

| 项 | 值 |
| --- | --- |
| 仓库 | `dream-num/univer`，TypeScript，22.3k star，1.8k fork |
| 许可 | **Apache-2.0**（Pro 部分另行商业授权） |
| 最新版 | **v1.0.3**（2026-09-29 发布，已到 1.0） |
| 活跃度 | 最后提交 2026-10-05（当天） |
| 自我定位 | "The Office Harness for AI Agents" |
| 官方支持浏览器 | **Chrome/Edge ≥88、Firefox ≥90、Safari ≥14.1、Electron ≥12** |
| Node 要求 | ≥18.17（官方 AI CLI 要求 Node 22.12+） |

它的差异化叙事是"**同构（isomorphic）**"：同一套 Facade API 既能在浏览器里渲染编辑，也能在 Node 里无头跑公式和数据处理，专门为 agent 场景设计。

能力覆盖：Spreadsheets / Documents / Presentations / Bases / Boards / PDF。

---

## 三、OSS 与 Pro 的边界（决定能不能做的关键）

### 开源（Apache-2.0，可用）

- Core SDK、插件体系、渲染引擎（Canvas）、**公式引擎**、Facade API、主题、i18n、React/Vue/WebComponent 适配
- Sheets：核心编辑、公式、数字格式、筛选/排序、数据验证、条件格式、批注、表格对象、超链接、查找替换、Drawing
- Docs：文档模型 + 编辑器 UI、列表、超链接、评论、快速插入
- Slides：**只有**基础 model 和 UI 包（`@univerjs/slides` 179 KB / `@univerjs/slides-ui` 552 KB）
- **Node 无头运行时**（`@univerjs/preset-sheets-node-core`）
- 水印（watermark）

### 商业版 Univer Pro（`@univerjs-pro/*`，独立仓库）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| **图表** | Pro | npm 无 `@univerjs/sheets-chart`；Pro 有 `@univerjs-pro/sheets-chart` |
| **透视表** | Pro | npm 无 `@univerjs/sheets-pivot`；Pro 有 `@univerjs-pro/sheets-pivot` |
| **xlsx 导入导出** | Pro | `@univerjs-pro/exchange-client` / `exchange-node`（**原生绑定 + license 校验**） |
| **打印 / PDF** | Pro | `@univerjs-pro/print` / `sheets-print` |
| **实时协同** | Pro | 无任何开源 OT/CRDT 层，全部在 `@univerjs-pro/collaboration-*` |
| **版本历史 / 语义 diff** | Pro | `@univerjs-pro/edit-history-*` |
| **迷你图 / 形状 / 大纲** | Pro | `@univerjs-pro/sheets-sparkline` / `-shape` / `-outline` |
| **Worktree 协作** | Pro | `@univerjs-pro/collaboration-worktree-*` |
| **服务端计算** | Pro | `@univerjs-pro/server-calc`（但见 §5 备注） |

**安全核查**：开源包里没有 license key 强制、没有遥测上报。我扫过全部 `@univerjs/*/lib/es/*.js`，唯一的网络代码在 `@univerjs/network`，是一个**通用传输抽象**（Fetch/XHR/WebSocket），只有你给了 URL 才会发请求；没有默认端点。硬编码的 `http(s)://` 字符串只有 Apache 协议头、`w3.org/2000/svg` 和公式文档里的 `support.microsoft.com` 链接。

> Pro 包在 npm 上**可以匿名下载**，但 tarball 里 `"license": null`——没有 OSI 许可即默认保留所有权利。这不是"免费试用"，是商业授权物。

---

## 四、AgenticOS 侧的硬约束

### 4.1 Chrome 85 —— 最硬的墙

`frontend/vite.config.ts:13-19`：
```ts
legacy({ targets: ['Chrome >= 85', 'Edge >= 85', ...], cssTarget: 'chrome85' })
```
`npm run verify:css` 会在构建后**强制拦截**未加 `@supports` 保护的 `oklch(` / `oklab(` / `lab(`（`frontend/scripts/verify-css.mjs:17-22`）。

**我实测了 Univer 1.0.3 的发布产物**（`npm pack` 下来 grep，不是看文档）：

| 项 | 实测结果 | Chrome 85 影响 |
| --- | --- | --- |
| `oklch()` | **0** | ✅ 无影响 |
| `color-mix()` | **0** | ✅ 无影响 |
| `:where()` | **213 处** | ⚠️ Chrome 88 才支持 |
| `Intl.Segmenter` | 8 处 | ❌ Chrome 87 才支持 |

`:where()` 的 213 处里，**176 处是 `.univer-dark` 暗色模式规则**，37 处是 RTL。Chrome 85 上 `:where()` 整条选择器失效 → **深色模式下编辑器样式大面积错乱**（浅底浅字）。浅色 + LTR 场景影响是纯装饰性的。

`Intl.Segmenter` 被 Univer 官方 README 明确要求 polyfill（`@formatjs/intl-segmenter`）。它在 `@univerjs/core` 的 UMD 构建里出现在 `o=new Intl.Segmenter(a,{granularity:'grapheme'})` 这样成对出现的形式，缺失时会在首次使用分词能力时报 `TypeError` 而非优雅降级。

**结论**：Chrome 85 上不是"渲染难看一点"，是**编辑器部分功能直接报错** + **深色模式坏掉**。这不是打两个 polyfill 能干净解决的——你会变成一个官方从未测试过的支持组合的维护者。

### 4.2 包体

实测 `preset-sheets-core` + `presets` 的 Vite 生产构建：**单 chunk 6.6 MB / gzip 1.70 MB**，1756 个模块，**默认不代码分割**。Univer 没有提供 manualChunks 配方（`docs.univer.ai/guides/sheets/advanced/lazy-load` 和 `.../recipes/architecture/lazy-load` 都 404）。

对比现有最大 chunk：`echarts-vendor` 1.1 MB、`markdown-vendor` 1.0 MB。Univer 比现有最大的依赖还大 55%。

唯一验证过的减负手段：`UniverSheetsCorePreset({ workerURL })` 把公式计算挪到 Worker（worker 包反而大 2.8 倍）。

### 4.3 现有的懒加载惯例可以照抄

```tsx
// frontend/src/components/chat/ChatMessageSubComponents.tsx:178
import('mermaid').then((mod) => { ... })
// ChatMessageSubComponents.tsx:236
import('echarts').then(...)
// frontend/src/App.tsx:20
const Chat = lazy(() => import('./pages/Chat').then(m => ({ default: m.Chat })))
```
`cytoscape`（436 KB）、`wardley`（488 KB）已经是这么懒加载的，说明这条路在本项目可行。

⚠️ **陷阱**：`ChatArtifactArea.tsx:3-6` 是**静态 import 全部四个面板**的。照抄这个写法会把 Univer 打进 `Chat` chunk，所有用户的首屏都变慢。必须 `React.lazy` + 动态 `import()` 两层。

### 4.4 设计体系

`index.css:51` 的注释写死了约束："所有色值必须是 hex / rgba（Chrome 85），禁止 oklch / color-mix"。强调色只允许出现在 `--ring`（焦点环）。

Univer 自带一整套自己的主题命名空间（`--color-*` + `.univer-dark`）和工具栏/公式栏 chrome。**逐 token 对齐不现实**。可行的做法是把它当作"编辑器表面"隔离出去——这和现有架构一致：website / PPT / email 面板本来就都是 iframe srcdoc 或独立渲染，不走 token 体系。

---

## 五、Agent 侧集成：全部开源，而且便宜

### 官方 AI 集成的形态是 CLI，不是 MCP

`docs.univer.ai/ai` 明确写着 AI SDK 是 "a TypeScript SDK for building Office CLIs"。**没有任何 model-native tool schema、tool router 或 MCP server**。25 个 `@univer-cli/*` 包里没有一个叫 mcp/agent/server。

Agent 的编辑循环是**跑 Facade JavaScript**，不是结构化工具调用：
```
load → pull → inspect → execute({mode:'read'|'write', code}) → runtime.commit()
```
`execute` 官方明确警告："runs trusted JavaScript and is **not a sandbox** for untrusted code"。

### 三个验证原语（全部 OSS，这是最值钱的部分）

| 原语 | 包 | 作用 |
| --- | --- | --- |
| 结构化回读 | `@univer-cli/content-inspection` | `inspectContent()` → 读回单元格/区域，供断言 |
| 视觉截图 | `@univer-cli/unit-screenshot` | **按 sheet / 区域 / 缩放截 PNG**，回传给多模态模型自检 |
| 版式诊断 | `@univer-cli/unit-layout-lint` | 检测溢出页外、文本重叠 |

外加一个我认为**最该抄**的设计：`@univer-cli/api-reference` 提供**离线、版本匹配的 API 检索**——
```
api find "setValues conditional formatting" --unit sheet
api show FRange FRange.setValues
```
让 LLM 去查装好的 SDK 到底有哪些方法，而不是凭记忆编一个不存在的 `setCellValue()`。这解决 LLM 幻觉 API 名的问题，成本极低。

配套的 `univer skills get core` / `get sheet` 机制：**把与当前 SDK 版本严格匹配的 Skill 随构建产物一起发出去**，保证 LLM 的指令不会随 SDK 升级漂移。他们的 SKILL.md 里有一句话值得直接抄：

> "**Command success is not correctness evidence.** Read back the target model, verify task-specific assertions, and inspect rendered output when appearance matters."

### Node 无头运行时：不需要 DOM shim

实测在 Node 22 上 `typeof window === 'undefined'` 直接跑，不需要 jsdom：

```ts
import { UniverSheetsNodeCorePreset } from '@univerjs/preset-sheets-node-core'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'

const { univer, univerAPI } = createUniver({
  locale: LocaleType.EN_US,
  locales: { [LocaleType.EN_US]: mergeLocales(enUS) },
  presets: [UniverSheetsNodeCorePreset()],
})
const wb = univerAPI.createWorkbook({ id: 'wb-01', name: '报表' })
const ws = wb.getActiveSheet()
ws.getRange('A1:C1').setValues([[10, 20, 30]])
ws.getRange('D1').setFormula('=SUM(A1:C1)')

// ⚠️ 公式计算是异步的，必须显式驱动 —— 这是唯一的大坑
const formula = univerAPI.getFormula()   // 注意：不是 getFormulaEngine()
formula.executeCalculation()
await formula.onCalculationResultApplied()
console.log(ws.getRange('D1').getValue())   // 60

univer.dispose()
```

> `setFormula()` 之后立刻读会拿到 `null`。这是接入第一天就会踩的坑。

### 持久化：`IWorkbookData` 纯 JSON 快照

```ts
const snapshot = wb.save()   // { id, sheetOrder, name, appVersion, locale, styles, sheets, resources }
```
序列化后存进现有 SQLAlchemy 表即可。**整体存，别挑字段**——`appVersion` / `rev` / 内部化的 `styles` 引用表手改会坏。

> 备注：README 把"服务端计算"列为 Pro，但实测 Node 无头运行时**确实能算公式**。我的理解是：基础公式计算是 OSS；把重计算卸载到专用计算服务才是 Pro。这一点在对外宣传"服务端计算"之前应该找 DreamNum 确认。

---

## 六、AgenticOS 侧要改什么

### 6.1 必须新建

| # | 位置 | 内容 |
| --- | --- | --- |
| 1 | `backend/app/tools/sheet_tools.py` | `register_sheet_tools(registry)`：`create_workbook` / `set_range` / `set_formula` / `add_worksheet` / `inspect` / `build_sheet` |
| 2 | `backend/app/services/sheet_service.py` | 无头 Univer 运行时封装 + 进程池（启动很贵，必须复用） |
| 3 | `backend/app/db/models.py` | `SpreadsheetArtifactModel`（照抄 `PptArtifactModel:267`）或复用 website 的快照文件方案（**零迁移**） |
| 4 | `frontend/src/components/sheet/SpreadsheetArtifactPanel.tsx` | `React.lazy` + 内部再 `import('@univerjs/preset-sheets-core')` |

### 6.2 模式注册要改 4 个地方

1. `tool_config_service.py:12-39` — `AGENT_MODES["sheet"]`
2. `tool_config_service.py:45-58` — `_MODE_TOOL_REGISTRARS["sheet"]`（加一个元组，工具目录和默认值自动生成）
3. `schemas/agent_profiles.py:41` 和 `:80` — **两处正则** `^(general|ppt|website|email|bigdata)$`（注意现在已经有 `bigdata` 这个模式）
4. `agent_profile_service.py:36-42,52-84` — 提示词 + 内置 profile
5. `factory.py:792` — `if profile.response_mode == "sheet":` 注册分支
6. `frontend/src/stores/chatStore.ts:11` — `ChatMode` 联合类型；再同步 `useChatStream.ts:51`、`ChatInput.tsx:22,264`、`constants/modePrompts.ts:9`

### 6.3 产物管线

照抄 website 模式（**这是最该参考的样板**，它就是"agent 产出一个真实可构建产物"）：

```
copy_template → check_website_project → build_website(npm run build) → deploy_website
```

对应表格就是：

```
create_workbook → set_range/set_formula → build_sheet(无头运行时产出快照) → artifact_ready
```

关键在于 `build_sheet` 是**确定性步骤**（对应 `build_website` 跑 `npm run build`），产物是**从文件系统读出来的**而不是从模型输出里解析的——这正是让 website 产物可信、而不是"模型编出来的一坨 HTML"的原因。

- `orchestrator.py:779` 加 `sheet_mode` 分支 yield `artifact_ready`
- `artifact_version_service.py:118-155` 加第三种 `kind`（现有 `ppt` / `website`）
- `frontend/src/types.ts:141` 联合类型加一支
- `ChatArtifactArea.tsx` 加分支（**必须 lazy**）

### 6.4 可以直接复用的

| 能力 | 位置 |
| --- | --- |
| 版本化工作目录 `u{u}_s{s}_v{n}` | `core/data_path.py:51-57` |
| 工作区文件工具（contextvar 重定向） | `tools/website_file_tools.py:24-27` |
| 进程沙箱 | `services/sandbox.py:116` |
| 快照版本化，**零 DB 迁移** | `artifact_version_service.py:60-81` |
| HITL 审批（导出 xlsx 需要 DLP 卡点） | `models.py:249-262`、`factory.py:314-363` |
| 工具自动发现 | `tool_config_service.py:45-79` |
| `analyze_data` 算数字 | `tools/data_analysis_tools.py:13` |
| `render_chart` 出 ECharts | `tools/chart_render_tools.py:16` |
| MCP 自动注册 | `factory.py:793-803` |
| 懒加载重依赖 | `vite.config.ts:73-77` |

---

## 七、建议路径

### Phase 1 — 表格产物（后端为主，2~3 周）

**做**：
1. 无头 Univer 运行时封装成 service + 进程池
2. `sheet` 模式 + 6 个工具（create / set_range / set_formula / add_worksheet / inspect / build）
3. `SpreadsheetArtifactPanel`（只读 + 可编辑保存回后端），`React.lazy` 双层懒加载
4. **图表用现有 ECharts 管线渲染成 PNG 贴进单元格区域**——这是绕过 Pro 图表的正解，且我们已有这套管线
5. 快照存 `IWorkbookData` JSON，配 `revision` 整数字段做乐观并发（冲突返 409）
6. 审批流：复用现有 `PendingApprovalPanel`，抄 Worktree 状态机 `ready → 人工审 → merge | reopen`（`ready` 不动主干这条不变量要保留）

**不做**：xlsx 导出、协同、透视表。

**Chrome 85 策略**：面板入口做能力探测——`CSS.supports('selector(:where(*))')` 或直接检测 `Intl.Segmenter`，不满足就不渲染编辑器，改提示"当前浏览器不支持表格编辑器，请使用 Chrome 88 以上"。**不要为了 85 去 polyfill 硬扛**。

### Phase 2 — xlsx 导出（1 周）

Pro 的 `@univerjs-pro/exchange-node` 是原生绑定 + license 校验，不能用。开源侧只有社区方案 `@mertdeveci55/univer-import-export`（MIT，底层是 ExcelJS 分支 `@zwight/luckyexcel`），但它 peer 依赖写的是 `@univerjs/core >=0.6.0`，而 SDK 已经 1.0.3，数据结构大概率对不上，要花一天移植并验证。

**建议自己写一个薄导出器**（`IWorkbookData → ExcelJS`），覆盖值/公式/数字格式/字体/填充/边框/对齐/合并/列宽/冻结/多表。这个工作量不大（3~5 天），换来一个自己掌控、可审计、能进内网仓库的依赖——对企业内网部署这比省事重要。可以拿 `@zwight/luckyexcel` 做格式映射的参考。

> 官方 issue 里搜 "xlsx export" 只有 2 条，都不是关于开源可用性的；搜 "exchange pro license" **0 条**。维护者没有给出开源转换方案，这是个空白。

### Phase 3 — 评估是否买 Pro

只有当"企业用户打开表格发现没有图表、不能导出 xlsx、不能多人同时编辑"导致留存问题时再谈。届时 Pro 报价要走商务。

### 明确不做

- **不要动现有 PPT 管线。** Univer 的幻灯片导出是 Pro；我们已有的 SVG→PPTX（`ppt/svg_to_pptx/`，`python-pptx` + 自研 DrawingML emitter，约 27000 行，产出**形状可编辑**的原生 PPTX）是产品壁垒，Univer 替代不了。
- **不要走 `mcp.univer.ai`。** `dream-num/univer-mcp` 仓库**只有 README 没有源码**，且 2025-09-06 后停更，指向的是需要 API key 的托管服务，工具列表未公开。README 里所有截图（图表、条件格式、协同）都是 Pro。

---

## 八、成本估算

| 阶段 | 工作量 | 风险 |
| --- | --- | --- |
| Phase 1 表格产物 | 2~3 周 | 中：Chrome 85 降级策略、Univer 版本锁死（`@univerjs/*` 必须同一精确版本） |
| Phase 2 xlsx 导出 | 1 周 | 中：格式保真度、社区包需从 0.6 移植到 1.0 |
| 截图自检（可选） | 3~5 天 | 中：服务端需要 Chrome/Chromium + **中文字体**，容器体积和字体是坑；必须实现像素数上限和超时（抄 dsh 的 `screenshotMaxPixels: 16777216` / 120s） |
| 协同 | 不可做 | Pro |

**Agent 侧集成是真便宜的**——比我们已经有的 PPT/HTML 管线便宜，而且背后有真实数据模型。便宜的是 agent 面，贵的是"人看得见、并且愿意用"的界面，而后者的一半是 Pro。

---

## 九、可以抄的三个设计（与用不用 Univer 无关）

1. **离线 API 检索**。让 LLM 查"当前装的这个版本里到底有哪些 Facade 方法"，而不是凭训练记忆编 API 名。任何第三方 SDK 集成都该这么做。
2. **随构建发版匹配的 Skill**。把指导 LLM 的文档和 SDK 版本绑定发布，杜绝版本漂移。我们已经在 e2e 上用过这个思路（`.agents/skills/e2e/`）。
3. **验证三件套**：结构化回读 + 按区域截图 + 版式 lint，全部做成 agent 工具。以及那句原则——"**命令返回成功不等于结果正确**"，必须回读目标模型做断言。

---

## 十、未决问题

1. "服务端计算"的 OSS/Pro 界线到底在哪（README 把基础公式计算和"计算卸载服务"混在一起描述）
2. 有没有官方认可的代码分割配方（lazy-load 文档页 404）
3. Pro 的报价与授权范围（内网多实例部署怎么算）
4. `@mertdeveci55/univer-import-export` 对 1.0.x 的实际兼容性（需实测）
