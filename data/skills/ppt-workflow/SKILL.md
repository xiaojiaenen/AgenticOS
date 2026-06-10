---
name: ppt-workflow
description: PPT 创作工作流——8 步流程、spec_lock 执行锁、submit_spec_lock 持久化、内容型计划、修改流程、文件处理。每次 PPT 任务开始时加载。
version: 1.1.0
tags: [ppt, workflow, spec_lock, submit_spec_lock]
when_to_use: 开始 PPT 创作任务时，加载此工作流以获取创作步骤和规范
allowed_tools: [save_slide, read_slide, load_skill, load_skill_reference, list_icons, search_icons, submit_spec_lock, submit_slide_plan, file_to_md, convert_pptx_to_svg]
required_tools: []
---

# PPT 创作工作流

PPT 创作的完整流程、执行纪律和操作规范。

---

## 〇、角色切换协议（借鉴 ppt-master）

PPT 创作分为两个角色，**绝不在同一个回复中混合两个角色的职责**：

### 角色 1：策略师（Strategist）

**触发条件**：用户提出 PPT 需求时

**职责**：
- 分析用户需求（内容、受众、用途、时长）
- 从注入的主题列表中推荐最佳匹配
- 输出 spec_lock（设计参数锁定表）
- 规划页面序列（每页的 layout + 节奏标签）
- 与用户确认八项参数后，切换到执行者

**参考技能**：ppt-workflow

### 角色 2：执行者（Executor）

**触发条件**：spec_lock 确认后

**职责**：
- 逐页生成 SVG 幻灯片
- 每页生成前重读 spec_lock
- 调用 `save_slide` 写入文件
- 不主动修改 spec_lock 中的参数

**参考技能**：ppt-design-guide + ppt-template-library

### 切换规则

| 场景 | 操作 |
|------|------|
| 首次创作 | 策略师 → 输出 spec_lock → 用户确认 → 执行者 |
| 用户要求修改 | 执行者 → 读取当前 spec_lock → 策略师评估影响 → 执行者修改 |
| 用户要求新增章节 | 执行者 → 策略师规划新页 → 执行者生成 |

**禁止**：在一个回复中同时做规划和生成 SVG。先规划完，再生成。

---

## 一、创作 7 步流程

### Step 0：加载技能

每次对话开始或接到 PPT 任务时，**必须按顺序加载两个技能**：
1. `load_skill("ppt-design-guide")` — 设计规范
2. `load_skill("ppt-template-library")` — 模板库

**懒加载纪律**：加载技能后，不要预读所有模板文件。按需逐页读取——生成第 N 页前只读该页需要的 1 个模板 SVG，读完立即生成。不要在开始生成前读取 3 个以上模板。

### Step 1：确认需求（最多 2 轮）

**第 1 轮：用户提出需求时，直接给出完整方案（不要逐项追问）**

根据用户描述推断所有参数，输出一个完整方案让用户一次性确认：

> 我为这个 PPT 推荐以下方案：
> - 主题：AI Agent · 面向非技术人员 · 8 页
> - 风格：agentic 主题
> - 页面：封面 → 概念介绍 → 工作原理 → 对比 → 应用场景 → 案例 → 展望 → 总结
>
> 直接开始生成，或告诉我需要调整的地方。

**第 2 轮（仅在用户有修改时）**：根据反馈调整方案，再次确认。用户说"开始"或"可以"即进入 Step 2。

**主题选择参考**：
- 工程师 → github / vercel / cursor / linear-app
- 高管/投资人 → apple / stripe / corporate / ibm
- 设计师/产品 → spotify / nike / framer / glassmorphism
- 消费者/小红书 → airbnb / xiaohongshu / pinterest / duolingo

**画布格式**：默认 16:9 (1280x720)。可选：
- 4:3 → `viewBox="0 0 1024 768"`
- 小红书/社交 → `viewBox="0 0 1242 1660"`（3:4 竖版）
- 朋友圈/Instagram → `viewBox="0 0 1080 1080"`（方形）
- 竖屏故事 → `viewBox="0 0 1080 1920"`（9:16）

**禁止**：不要分 5 轮分别问主题、受众、页数、风格、最终确认。一次性给出方案。

### Step 2：生成 spec_lock（执行锁）

在规划页面序列后、开始生成 SVG 前，必须先输出 spec_lock 块，锁定本 deck 的所有设计参数。

用表格形式输出（不用代码块）：

**画布**
- viewBox: 0 0 1280 720
- 格式: PPT 16:9

**颜色**（用 var(--token) 表示）
- bg / primary / accent / secondary / surface / border

**字体**
- title: 字体族 · 字号 · 字重
- body: 字体族 · 字号 · 字重
- mono: 字体族 · 字号 · 字重

**图标**
- 库: 先调 `list_icons` 确认可用图标库，再从中选一个（每套 PPT 只选一个，禁止混用）
- 清单: 在 spec_lock 阶段一次性批量搜索所有需要的图标（用逗号分隔多个关键词），结果写入此处。后续页面直接引用，不再重复搜索
- 降级: 如果 search_icons 返回"未初始化"或连续 2 次返回 0 结果，立即停止搜索，mode 改为 "text-only"，用 `<text>` 元素代替所有图标

**页面节奏（防千篇一律的核心机制）**

每页标注节奏标签：anchor / dense / breathing

**节奏规则**：
- 8 页至少 2 个 anchor + 1 个 breathing
- 不允许连续 3 页同节奏
- dense 页后必须接 breathing 或 anchor
- section-divider 固定为 anchor

**⚠️ breathing 页的硬约束（借鉴 ppt-master）**：

breathing 页**禁止**多卡片网格布局。具体禁止：
- 禁止 2×2 KPI 卡片网格
- 禁止 3 列并排卡片
- 禁止任何"多个圆角容器并排"的结构

breathing 页**应该**使用：
- 大号引文（big-quote 布局）
- 单个超大数字（stat-highlight 布局）
- 全出血背景 + 浮动文字
- 大量留白 + 单个核心信息
- 分割线 + 过渡文字

**没有节奏变化，每页都会默认变成卡片网格（"AI 生成感"的根源）。breathing 是打破这种默认行为的唯一武器。**

**执行纪律**：
- 每页生成前回顾 spec_lock，确认颜色、字体、图标与锁定值一致
- 绝不从记忆中取色值——每次都要查看 spec_lock
- 需要修改 spec_lock 时，明确告知用户并重新输出完整 spec_lock

**⚠️ 输出 spec_lock 后，必须立即调用 `submit_spec_lock` 持久化设计参数**：
```
submit_spec_lock(colors="bg:#fff, primary:#1a1a2e, accent:#e94560", fonts="title:Playfair Display 48px bold, body:Inter 16px", icon_library="chunk-filled")
```
这确保后续页面即使上下文被压缩，仍能获取正确的设计参数。

### Step 3：规划页面序列并提交计划

为每页指定布局，从模板库的 15 个核心布局和 71 个图表中选择：

- section-divider 至少出现 2-3 次
- 不允许连续使用同一布局
- 数据页面必须从图表索引中选型（参考图表选型指南）
- 数据密集页后接 big-quote 或 section-divider

**提交计划**：调用 `submit_slide_plan(slides='[...]')`，每页必须包含 `content` 字段：

```json
[
  {"slide_num":1, "layout":"cover", "title":"2025年AI市场分析", "content":"副标题: 基于行业调研 | 日期: 2025年6月"},
  {"slide_num":2, "layout":"bullets", "title":"市场背景", "content":"• 全球AI市场规模5500亿美元(来源: 报告P3)\n• 年增长率42%\n• 中国占全球28%"},
  {"slide_num":3, "layout":"kpi-grid", "title":"关键数据", "content":"KPI1: 5500亿 | 全球市场规模\nKPI2: 42% | 年增长率\nKPI3: 3x | 推理速度提升"}
]
```

- `content` 是从参考文档提取的该页具体数据，**禁止编造**
- 无参考文档时，`content` 为该页核心信息摘要
- 生成该页时，`save_slide` 返回值会自动注入下一页的计划数据

### Step 4：逐页构建

每页只做 2 步：
1. `load_skill_reference` 读取 1 个 SVG 模板
2. 复制骨架 + 替换内容 + `save_slide(slide_num=N, svg="...")` 写入

**⚠️ 每页生成前必须重读 spec_lock（不可跳过）**：
- 重新读取 spec_lock 中的颜色、字体、图标清单
- 禁止凭记忆使用色值、字体、图标名——每次都要查 spec_lock
- 这是防止长 PPT 生成过程中参数漂移的唯一保障

**图标使用规则**：
- 严格使用 spec_lock 图标清单中已确认的图标名
- 禁止自创图标名——如果需要新图标，先调用 `search_icons` 确认存在性
- 如果 spec_lock 中 mode 为 "text-only"，所有图标用 `<text>` 元素代替，不要调用 search_icons
- 至少 3 页，推荐 8-14 页

### Step 5：自检

所有页面完成后，按以下清单逐项核对（每页 save_slide 前必须核对）：

| 检查项 | 标准 |
|--------|------|
| `data-theme` | 每页 SVG 都有 `data-theme="主题名"` |
| viewBox | 所有页面 viewBox 一致 |
| var() 颜色 | 所有颜色用 `var(--token)`，无硬编码 hex |
| accent 预算 | `var(--accent)` 每页 <= 2 处 |
| 字号预算 | 每页 <= 4 种 font-size |
| notes | 每页都有 `<!-- notes: ... -->`，150-300 字，口语化 |
| section-divider | 至少 2-3 个，不连续重复布局 |
| `<g id>` 分组 | 每页 3-8 个内容组，裸元素不出现在 `<svg>` 根下 |

---

## 二、spec_lock 格式详解

spec_lock 是本 deck 的设计参数锁定表，作用是防止逐页创作过程中参数漂移。

**必须包含的字段**：
1. 画布：viewBox + 格式
2. 颜色：bg / primary / accent / secondary / surface / border
3. 字体：title / body / mono（含字体族、字号、字重）
4. 图标：库名 + 图标清单
5. 页面节奏：每页的节奏标签（anchor / dense / breathing）

**执行纪律**：
- 开始逐页构建前输出一次
- 每页生成前回顾一次（只看，不重新加载技能）
- 如需调整（如发现某页 accent 超预算），重新输出完整 spec_lock 并告知用户

---

## 三、修改已有 PPT

当对话中已经生成过 PPT，用户要求修改时：

1. 用 `read_slide(slide_num=N)` 读取需要修改的页
2. 在读取的 SVG 基础上修改
3. 用 `save_slide(slide_num=N, svg="...")` 只覆盖修改的页

**修改分级**：

| 改动级别 | 示例 | 操作 |
|---------|------|------|
| 小改 | 标题、数据、文字 | `save_slide` 覆盖对应页 |
| 中改 | 替换某页、调整页序 | `save_slide` 覆盖涉及页 |
| 大改 | 新增章节、重新规划 | 对新页和改动的页调用 `save_slide` |

**注意**：
- "加一页"、"删掉第X页"、"调整顺序"、"换个主题"、"改个数字"——这些都是在已有 PPT 上修改，不是重新做
- 修改后回复"第 X 页已更新"即可，不要重复输出所有 SVG
- 不要把所有 SVG 放在一个 code block 里——每页一个独立的 `save_slide` 调用

---

## 四、文件上传处理

### 文档类（.docx / .pdf / .txt / .md / .csv / .xlsx / .html）

1. 调用 `file_to_md(path="{文件路径}")` 将文件转为 Markdown 文本
2. 根据提取的内容创作 PPT slides，用 `save_slide` 逐页写入

### PPTX 文件（.pptx）

1. 调用 `convert_pptx_to_svg(file_path="{文件路径}")` 将 PPTX 转为可编辑的 SVG
2. 转换后的 SVG 自动写入当前会话工作目录
3. 用 `read_slide(N)` 读取需要修改的页面
4. 用 `save_slide` 覆盖修改的页面

**注意**：
- `file_path` 来自用户消息开头的上传文件提示，直接复制使用即可
- 不要用 `file_to_md` 处理 .pptx 文件

---

## 五、输出规范

1. **创作前确认**：内容/受众 + 主题推荐 + 画布格式（一次性确认，最多 2 轮）
2. **选择主题**：推荐最佳匹配，告知用户
3. **生成 spec_lock**：锁定颜色/字体/icon/页面节奏
4. **锁定设计参数**：调用 `submit_spec_lock` 持久化核心参数
5. **规划叙事线**：确定每页 layout + content（确保 section-divider >= 2、无连续重复）
6. **提交计划**：调用 `submit_slide_plan` 提交含 content 字段的页面计划
7. **逐页构建**：从模板库复制 SVG 结构 -> 替换内容 -> 保留 var(--token) -> 写 notes
8. **自检**：按上方清单逐项核对

**最后**：在所有 `save_slide` 调用完成后，用 2-3 句话总结设计思路。不要提及"SVG"、"code block"等技术术语。

---

## 六、执行纪律（严格遵守）

### 禁止元叙事

- 禁止在输出中解释"我需要做什么"、"让我来分析"、"首先我需要确认"等元推理
- 直接执行动作（调用工具、生成内容），不要自言自语
- 用户不需要看到你的思考过程，只需要看到结果

### 工具失败处理

- 工具连续失败 2 次后，**立即停止重试**
- 向用户报告问题并提供替代方案（如：图标不可用时用纯文字排版）
- 不要在思考中反复分析失败原因——直接切换到降级方案

### 确认轮次

- 所有参数一次性确认（主题 + 受众 + 页数 + 风格），不要逐项追问
- 用户一句话就能确认，不需要分 5 轮对话

### 懒加载纪律

- 加载技能后，不要预读所有模板文件
- 生成第 N 页前只读该页需要的 1 个模板 SVG
- 不要在开始生成前读取 3 个以上模板
