---
name: ppt-workflow
description: PPT 创作工作流——8 步流程、spec_lock 执行锁、submit_spec_lock 持久化、内容型计划、修改流程、文件处理。每次 PPT 任务开始时加载。
version: 1.3.0
tags: [ppt, workflow, spec_lock, submit_spec_lock]
when_to_use: 开始 PPT 创作任务时，加载此工作流以获取创作步骤和规范
allowed_tools: [save_slide, read_slide, read_notes, load_skill, load_skill_reference, list_icons, search_icons, submit_spec_lock, submit_slide_plan, file_to_md, convert_pptx_to_svg, search_images, get_image_info, resume_ppt, check_ppt_progress, analyze_template]
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

**图片策略**
- mode: none | unified | per-page
  - none: 纯色/渐变背景，不使用图片（推荐用于数据密集型PPT）
  - unified: 统一风格图片背景（封面+章节页共用同一风格图片）
  - per-page: 每页独立搜索图片（当前行为，风格可能不一致）
- style: (仅 unified 模式) 图片风格描述，如 "商务蓝调抽象科技"、"自然风光绿色"
- sources: (仅 unified 模式) 预搜索的图片 URL 列表（3-5张），在 spec_lock 阶段一次性搜索完成
- background: none 模式的背景策略
  - solid: 纯色背景（使用 var(--bg)）
  - gradient: 渐变背景（使用 linearGradient）
  - pattern: 几何图案背景（使用装饰性 SVG 元素）

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

**⚠️ 规划前必须先读取三个索引（不可跳过）：**

1. **图表索引**：`load_skill_reference("ppt-template-library", "references/charts/charts_index.json")` — 读取全部 71 种图表的选型规则，为数据页匹配最佳图表类型
2. **布局模板列表**：回顾 `ppt-template-library` 技能中的 15 个核心布局，确保每页选择不同的布局结构
3. **图文布局索引**：`load_skill_reference("ppt-template-library", "references/image-layouts-index.json")` — 读取 72 种图文布局模式，为含图片的页面选择最佳布局

为每页指定布局，从 15 个核心布局、71 个图表、72 种图文布局中选择：

- **布局多样性铁律**：同一套 PPT 至少使用 4 种不同布局模式，不允许连续使用同一布局
- section-divider 至少出现 2-3 次
- **数据页必须从图表索引中选型**（如 bar_chart、line_chart、pie_chart 等），禁止所有数据页都用 kpi-grid
- 数据密集页后接 big-quote 或 section-divider
- **breathing 页禁止卡片网格**：必须用 big-quote、stat-highlight 或全出血背景
- **图文布局优先**：封面和章节页必须使用图文布局（01-full-bleed、04-hero-overlay 等）

**图文布局选择规则**：
| 页面类型 | 图片数量 | 推荐布局 |
|---------|---------|---------|
| 封面 | 1 | 01-full-bleed, 04-hero-overlay |
| 章节页 | 1 | 04-hero-overlay, 06-circle-frame |
| 内容页 | 1 | 02-split-horizontal, 08-offset-float |
| 对比页 | 2 | 16-duo-side, 20-before-after |
| 作品集 | 3+ | 31-gallery, 32-masonry |
| 数据页 | 0-1 | 10-corner-accent（小图点缀） |

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

### Step 4：逐页构建（支持批量生成）

**批量生成模式（推荐，减少 40-60% 调用）**：

每 3 页为一批，每批做 5 步：
1. `load_skill_reference` 读取第 1 个模板
2. 生成第 1 个 SVG + `save_slide`
3. `load_skill_reference` 读取第 2 个模板
4. 生成第 2 个 SVG + `save_slide`
5. `load_skill_reference` 读取第 3 个模板
6. 生成第 3 个 SVG + `save_slide`

**单页生成模式（兼容）**：

每页做 3 步：
1. `load_skill_reference` 读取 1 个 SVG 模板
2. 复制骨架 + 替换内容
3. `save_slide(slide_num=N, svg="...", notes="...")` 写入

**⚠️ 每页生成前必须重读 spec_lock（不可跳过）**：
- 重新读取 spec_lock 中的颜色、字体、图标清单
- 禁止凭记忆使用色值、字体、图标名——每次都要查 spec_lock
- 这是防止长 PPT 生成过程中参数漂移的唯一保障

**图片使用规则（根据 spec_lock 的图片策略）**：

| 模式 | 封面 | 章节页 | 内容页 | 数据页 |
|------|------|--------|--------|--------|
| none | 渐变/图案背景 | 渐变/图案背景 | 纯色背景 | 纯色背景 |
| unified | 主图背景 | 辅助图背景 | 纯色/小图点缀 | 纯色背景 |
| per-page | 独立搜索 | 独立搜索 | 独立搜索 | 纯色背景 |

**none 模式背景规范**：
```xml
<!-- 渐变背景 -->
<defs>
  <linearGradient id="bg-grad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="var(--bg)"/>
    <stop offset="100%" stop-color="var(--bg-2)"/>
  </linearGradient>
</defs>
<rect width="1280" height="720" fill="url(#bg-grad)"/>

<!-- 几何图案背景 -->
<rect width="1280" height="720" fill="var(--bg)"/>
<g id="pattern" opacity="0.05">
  <circle cx="100" cy="100" r="50" fill="var(--accent)"/>
  <circle cx="300" cy="200" r="30" fill="var(--accent)"/>
  <!-- 更多装饰元素 -->
</g>
```

**图标使用规则**：
- 严格使用 spec_lock 图标清单中已确认的图标名
- 禁止自创图标名——如果需要新图标，先调用 `search_icons` 确认存在性
- 如果 spec_lock 中 mode 为 "text-only"，所有图标用 `<text>` 元素代替，不要调用 search_icons
- 至少 3 页，推荐 8-14 页

**演讲者备注**：
- 每页必须提供 150-300 字的口语化备注
- 备注包含：开场白、关键数据解释、过渡语、互动提示
- 不要重复页面上已有的文字
- 使用第一人称（"我接下来要讲的是..."）

**备注示例**：
```
save_slide(slide_num=3, svg="...", notes="""
大家好，接下来我们看一下今年的市场数据。

左边这个柱状图显示的是各季度的增长情况，Q3 达到了 42% 的峰值。
这个数字比去年同期增长了 15 个百分点，主要得益于新产品的推出。

右边是市场份额对比，我们的份额从 18% 提升到了 23%。
这里我想特别强调一下，这个增长是在整体市场收缩的背景下实现的。

下一页我会详细介绍增长的驱动因素。
""")
```

### Step 5：自检（带循环保护）

**质量检查循环保护机制**：
- 最大检查次数：3 次
- 最大修复尝试：2 次
- 最低通过率：80%
- **超时或次数用尽：直接完成，不报错，正常渲染**

所有页面完成后，按以下清单逐项核对（每页 save_slide 前必须核对）：

| 检查项 | 标准 | 优先级 |
|--------|------|--------|
| `data-theme` | 每页 SVG 都有 `data-theme="主题名"` | P0 |
| viewBox | 所有页面 viewBox 一致 | P0 |
| var() 颜色 | 所有颜色用 `var(--token)`，无硬编码 hex | P1 |
| accent 预算 | `var(--accent)` 每页 <= 2 处 | P1 |
| 字号预算 | 每页 <= 4 种 font-size | P1 |
| notes | 每页都有 `<!-- notes: ... -->`，150-300 字，口语化 | P1 |
| section-divider | 至少 2-3 个，不连续重复布局 | P1 |
| `<g id>` 分组 | 每页 3-8 个内容组，裸元素不出现在 `<svg>` 根下 | P1 |
| 动画标记 | 关键元素有 `data-animate` 属性（封面标题、图表等） | P2 |
| 图片策略 | 符合 spec_lock 的图片策略 | P1 |

**自检流程（带保护）**：
```
check_count = 0
fix_count = 0

while check_count < 3:
  result = check_quality()
  check_count++
  
  if result.pass_rate >= 0.8:
    break  # 通过
  
  if fix_count >= 2:
    break  # 修复次数用尽
  
  fix_critical_errors(result.errors)
  fix_count++

# 无论结果如何，都正常完成
return "completed"
```

**⚠️ 重要**：
- 检查不通过时**不要报错**，**不要停止**
- 记录警告信息，继续正常完成
- 用户可以在编辑器中手动修复遗留问题

**动画标记规范**：

在 `<g>` 或其他元素上添加 `data-animate` 属性：

```xml
<!-- 基本格式 -->
<g id="title" data-animate="fade-up">
  <text>标题文字</text>
</g>

<!-- 带延迟 -->
<g id="chart" data-animate="zoom-in" data-delay="0.3">
  <!-- 图表内容 -->
</g>

<!-- 带持续时间 -->
<g id="subtitle" data-animate="fade" data-delay="0.5" data-duration="1.0">
  <text>副标题</text>
</g>
```

**推荐动画组合**：
| 元素类型 | 推荐动画 | 延迟 |
|---------|---------|------|
| 封面标题 | fade-up | 0.3s |
| 封面副标题 | fade-up | 0.5s |
| 章节标题 | fade-up | 0.3s |
| 图表 | zoom-in | 0.5s |
| KPI 数字 | zoom-in | 0.2s |
| 列表项 | fade-up | 0.1s 递增 |

**页面转场**：

在 `<svg>` 标签上添加 `data-transition` 属性：

```xml
<svg data-transition="fade" ...>
<svg data-transition="push" data-transition-dir="left" ...>
<svg data-transition="wipe" data-transition-dir="down" ...>
```

可选转场类型：fade, push, wipe, split, strips, cover, random

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

## 四、图片使用规范

### 图片来源

1. **网络搜索**：调用 `search_images` 搜索免费商用图片
2. **用户提供的 URL**：直接使用用户给出的图片链接
3. **避免 AI 生图**：优先使用真实图片，而非 AI 生成的图片

### 搜索图片

```
search_images(query="business meeting", count=3, orientation="landscape")
```

**参数说明**：
- `query`: 搜索关键词（英文效果更好）
- `count`: 返回数量（建议 3-5 张供选择）
- `orientation`: 方向
  - `landscape`: 横版（适合 16:9 PPT，推荐）
  - `portrait`: 竖版
  - `square`: 方形
- `license`: 许可证类型
  - `cc0`: 完全免费，无需署名（推荐）
  - `cc-by`: 需署名

### 在 SVG 中使用图片

```xml
<!-- 方式 1: 网络图片 -->
<image href="https://images.unsplash.com/photo-xxx.jpg"
       x="0" y="0" width="640" height="360"
       preserveAspectRatio="xMidYMid slice"/>

<!-- 方式 2: 带遮罩的背景图 -->
<defs>
  <linearGradient id="overlay" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="var(--bg)" stop-opacity="0.3"/>
    <stop offset="100%" stop-color="var(--bg)" stop-opacity="0.8"/>
  </linearGradient>
</defs>
<image href="{URL}" x="0" y="0" width="1280" height="720"
       preserveAspectRatio="xMidYMid slice"/>
<rect x="0" y="0" width="1280" height="720" fill="url(#overlay)"/>
```

### 图片使用规则

**必须使用图片的页面**：
- 封面：必须有背景图（全出血或分割布局）
- 章节页：必须有图片或大引文
- 产品/人物介绍：必须有配图

**可选使用图片的页面**：
- 数据页：优先用图表，不用图片
- 对比页：可用图片增强对比效果
- 总结页：可用背景图增强氛围

**禁止**：
- 禁止使用 AI 生成的图片（风格不统一）
- 禁止使用低质量/模糊的图片
- 禁止图片拉伸变形（使用 `preserveAspectRatio`）

### 署名处理

如果使用了需要署名的图片（CC BY 等），在 PPT 最后一页添加：

```xml
<text x="40" y="680" font-size="10" fill="var(--text-3)">
  图片来源: Unsplash / Pexels / Wikimedia Commons
</text>
```

---

## 五、文件上传处理

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
