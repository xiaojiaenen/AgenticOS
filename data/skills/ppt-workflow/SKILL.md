---
name: ppt-workflow
description: PPT 创作工作流——7 步流程、spec_lock 执行锁、修改流程、文件处理。每次 PPT 任务开始时加载。
version: 1.0.0
tags: [ppt, workflow, spec_lock]
when_to_use: 开始 PPT 创作任务时，加载此工作流以获取创作步骤和规范
allowed_tools: [save_slide, read_slide, load_skill, load_skill_reference, search_icons, file_to_md, convert_pptx_to_svg]
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

## 〇·五、Showcase-before-Batch 规则（借鉴 huashu-design）

**5 页以上的 deck，必须先生成 2 个 showcase 页，用户确认后再批量生成剩余页。**

### 为什么需要

一次性生成 10+ 页后才发现风格不对，返工成本极高。先做 2 页 showcase：
- 让用户确认视觉语法（配色、字体、布局风格）
- 验证 spec_lock 在实际 SVG 中的效果
- 建立后续页面的视觉基准

### 流程

```
策略师阶段（规划 + spec_lock）
    ↓
生成 2 个 showcase 页：
  - 1 个 anchor 类型（cover 或 section-divider）
  - 1 个 dense 类型（数据页或内容页）
    ↓
用户确认："风格可以" / "换一种"
    ↓
确认后批量生成剩余页
```

### Showcase 页要求

- 严格遵循 spec_lock
- 体现选定的设计哲学风格
- 包含完整的 `<g>` 分组和 `<!-- notes: -->`
- 是后续页面的视觉基准

---

## 一、创作 7 步流程

### Step 0：加载技能

每次对话开始或接到 PPT 任务时，**必须按顺序加载两个技能**：
1. `load_skill("ppt-design-guide")` — 设计规范
2. `load_skill("ppt-template-library")` — 模板库

**懒加载纪律**：加载技能后，不要预读所有模板文件。按需逐页读取——生成第 N 页前只读该页需要的 1 个模板 SVG，读完立即生成。不要在开始生成前读取 3 个以上模板，不要提前批量搜索图标。

### Step 1：确认需求

在写任何 SVG 之前，必须确认三件事（用户已提供足够信息时直接推断并告知，不用追问）：

1. **内容 & 受众**：主题是什么？几页？观众是谁？
2. **主题选择**：从注入的主题列表中推荐 1-2 个最匹配主题：
   - 工程师 → github / vercel / cursor / linear-app
   - 高管/投资人 → apple / stripe / corporate / ibm
   - 设计师/产品 → spotify / nike / framer / glassmorphism
   - 消费者/小红书 → airbnb / xiaohongshu / pinterest / duolingo
3. **画布格式**：默认 16:9 (1280x720)。可选：
   - 4:3 → `viewBox="0 0 1024 768"`
   - 小红书/社交 → `viewBox="0 0 1242 1660"`（3:4 竖版）
   - 朋友圈/Instagram → `viewBox="0 0 1080 1080"`（方形）
   - 竖屏故事 → `viewBox="0 0 1080 1920"`（9:16）

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
- 库: chunk-filled（或 tabler-filled 等）
- 清单: 从 search_icons 确认可用的图标名

**页面节奏**
- 每页标注节奏标签：anchor / dense / breathing

**执行纪律**：
- 每页生成前回顾 spec_lock，确认颜色、字体、图标与锁定值一致
- 绝不从记忆中取色值——每次都要查看 spec_lock
- 需要修改 spec_lock 时，明确告知用户并重新输出完整 spec_lock

### Step 3：规划页面序列

为每页指定布局，从模板库的 15 个核心布局和 71 个图表中选择：

- section-divider 至少出现 2-3 次
- 不允许连续使用同一布局
- 数据页面必须从图表索引中选型（参考图表选型指南）
- 数据密集页后接 big-quote 或 section-divider

### Step 4：逐页构建

每页只做 2 步：
1. `load_skill_reference` 读取 1 个 SVG 模板
2. 复制骨架 + 替换内容 + `save_slide(slide_num=N, svg="...")` 写入

- 每页生成前回顾 spec_lock（但不要因此重新加载技能）
- 需要图标时再调用 `search_icons`，不要提前批量搜索
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

1. **创作前确认**：内容/受众 + 主题推荐 + 画布格式
2. **选择主题**：推荐最佳匹配，告知用户
3. **生成 spec_lock**：锁定颜色/字体/icon/页面节奏
4. **规划叙事线**：确定每页 layout（确保 section-divider >= 2、无连续重复）
5. **逐页构建**：从模板库复制 SVG 结构 -> 替换内容 -> 保留 var(--token) -> 写 notes
6. **自检**：按上方清单逐项核对

**最后**：在所有 `save_slide` 调用完成后，用 2-3 句话总结设计思路。不要提及"SVG"、"code block"等技术术语。
