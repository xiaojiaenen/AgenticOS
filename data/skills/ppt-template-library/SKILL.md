---
name: ppt-template-library
description: PPT 模板库——15 个核心页面布局 + 71 个数据图表模板（均为 var(--token) 格式）。生成 PPT SVG 时从这里选取结构骨架。
version: 1.0.0
tags: [ppt, svg, template, layout, chart]
when_to_use: 生成 PPT SVG 时，从此模板库选取结构骨架，复制后替换为真实内容
allowed_tools: [save_slide, read_slide, read_text_file]
required_tools: []
---

# PPT 模板库

生成幻灯片 SVG 时，从以下模板中选取结构骨架，复制后替换为真实内容，保持 `var(--token)` 引用。

---

## 一、核心布局（15 个）

通用页面结构模板，适用于非数据密集型页面。

| 分类 | 布局名 | 文件 | 用途 |
|------|--------|------|------|
| 开场 | `cover` | `references/core-layouts/cover.svg` | 封面页——居中大标题 + 副标题 + 标签 |
| 开场 | `toc` | `references/core-layouts/toc.svg` | 目录页——2×3 网格目录 |
| 开场 | `section-divider` | `references/core-layouts/section-divider.svg` | 章节分隔——大号编号 + 章节标题 |
| 数据 | `stat-highlight` | `references/core-layouts/stat-highlight.svg` | 数据突出——超大数字 + 说明 |
| 数据 | `kpi-grid` | `references/core-layouts/kpi-grid.svg` | KPI 面板——2×2 指标卡片带涨跌 |
| 文字 | `bullets` | `references/core-layouts/bullets.svg` | 要点列表——图标 + 标题 + 描述 |
| 文字 | `two-column` | `references/core-layouts/two-column.svg` | 双栏对比——左概念右示例 |
| 文字 | `three-column` | `references/core-layouts/three-column.svg` | 三栏展示——图标 + 标题 + 描述 |
| 文字 | `big-quote` | `references/core-layouts/big-quote.svg` | 引用金句——居中大字引用 |
| 对比 | `comparison` | `references/core-layouts/comparison.svg` | 对比——左右对比 + 中间 VS |
| 对比 | `pros-cons` | `references/core-layouts/pros-cons.svg` | 优缺点——绿色优点 + 红色缺点 |
| 代码 | `code` | `references/core-layouts/code.svg` | 代码块——语法高亮代码展示 |
| 代码 | `terminal` | `references/core-layouts/terminal.svg` | 终端窗口——命令行录屏 |
| 结尾 | `cta` | `references/core-layouts/cta.svg` | 行动号召——居中大字 CTA + 按钮 |
| 结尾 | `thanks` | `references/core-layouts/thanks.svg` | 致谢——居中感谢 + 联系方式 |

### 使用流程（⚠️ 重要：不要照搬坐标）

1. 根据页面内容类型选择布局
2. 用 `read_file` 读取对应 SVG 文件，**理解其结构模式**（居中/左对齐/网格等）
3. **不要复制精确坐标**——参考结构后，自行决定具体参数：
   - 左边距：60-120px 范围内选择（不要每页都用 60）
   - 标题位置：居中/左对齐/偏上/偏下（不要每页都用 80,110）
   - 卡片圆角：0/8/12/16/20/24（不要每页都用 16）
   - 卡片间距：20-60px（不要每页都用 40）
   - 卡片尺寸：根据内容量调整（不要每页都用固定尺寸）
4. 保持所有 `var(--token)` 引用不变
5. 将 `data-theme="theme-name"` 替换为选定的主题名

**核心原则：模板是参考骨架，不是精确坐标。每页至少 2 个空间参数与上一页不同。**

---

## 二、数据图表（71 个）

数据可视化图表模板，适用于数据密集型页面。所有图表已转换为 `var(--token)` 色彩体系。

### 图表选型索引

从 `references/charts/charts_index.json` 读取完整的 71 条选型摘要。每条摘要遵循 "Pick for ... Skip if ..." 格式，帮助快速匹配合适的图表。

### 图表分类

| 分类 | 图表 | 文件 |
|------|------|------|
| **柱状图** | bar_chart, horizontal_bar_chart, grouped_bar_chart, stacked_bar_chart | `references/charts/*.svg` |
| **折线图** | line_chart, dual_axis_line_chart, area_chart, stacked_area_chart | `references/charts/*.svg` |
| **饼图/环形** | pie_chart, donut_chart | `references/charts/*.svg` |
| **散点/气泡** | scatter_chart, bubble_chart, quadrant_bubble_scatter | `references/charts/*.svg` |
| **雷达/仪表** | radar_chart, gauge_chart | `references/charts/*.svg` |
| **流程/漏斗** | funnel_chart, process_flow, pipeline_with_stages, chevron_process, chevron_chain_with_tail | `references/charts/*.svg` |
| **层级/树图** | treemap_chart, top_down_tree, mind_map, hub_spoke, hub_inward_arrows | `references/charts/*.svg` |
| **时间/进度** | timeline, gantt_chart, roadmap_vertical, progress_bar_chart | `references/charts/*.svg` |
| **对比/矩阵** | comparison_columns, comparison_table, matrix_2x2, butterfly_chart, dumbbell_chart, pros_cons_chart | `references/charts/*.svg` |
| **表格** | basic_table, consulting_table, project_schedule_table, financial_statement_table, feature_matrix_table, harvey_balls_table, team_roster | `references/charts/*.svg` |
| **统计** | box_plot_chart, pareto_chart, heatmap_chart, bullet_chart, waterfall_chart | `references/charts/*.svg` |
| **金字塔/漏斗** | pyramid_chart, pyramid_isometric, funnel_chart | `references/charts/*.svg` |
| **关系/网络** | sankey_chart, venn_diagram, fishbone_diagram, concentric_circles | `references/charts/*.svg` |
| **列表/卡片** | vertical_list, vertical_pillars, arc_anchored_list, labeled_card, kpi_cards, agenda_list, numbered_steps, icon_grid | `references/charts/*.svg` |
| **架构/组成** | layered_architecture, module_composition, circular_stages, segmented_wheel, client_server_flow | `references/charts/*.svg` |
| **其他** | word_cloud, snake_flow, journey_map, isometric_stairs, quadrant_text_bullets | `references/charts/*.svg` |

### 使用流程

1. 规划页面时，从图表索引中为数据页面选择合适的图表类型
2. 用 `read_file` 读取 `references/charts/{key}.svg`
3. 复制 SVG 骨架，替换占位数据为真实数据
4. 保持所有 `var(--token)` 引用不变
5. 如需精确坐标，可调用 `calc_chart_positions` 工具

---

## 三、布局选择指南

### 页面类型 → 模板映射

| 页面类型 | 推荐模板 |
|---------|---------|
| 封面 | cover |
| 目录 | toc |
| 章节过渡 | section-divider |
| 关键数据展示 | stat-highlight, kpi-grid, kpi_cards |
| 数据对比分析 | bar_chart, grouped_bar_chart, comparison_columns |
| 趋势展示 | line_chart, area_chart, stacked_area_chart |
| 占比分析 | pie_chart, donut_chart, treemap_chart |
| 流程说明 | process_flow, pipeline_with_stages, chevron_process |
| 优缺点 | pros-cons, pros_cons_chart |
| 时间线 | timeline, gantt_chart, roadmap_vertical |
| 组织架构 | top_down_tree, layered_architecture, hub_spoke |
| 要点罗列 | bullets, vertical_list, numbered_steps |
| 双栏对比 | two-column, comparison, comparison_columns |
| 三栏展示 | three-column, icon_grid |
| 引用/金句 | big-quote |
| 代码展示 | code, terminal |
| 行动号召 | cta |
| 致谢 | thanks |

### 布局多样性强制规则

- section-divider 至少出现 2-3 次
- 不允许连续使用同一布局
- 同一视觉模式最多出现 2 次
- 数据密集页后接 big-quote 或 section-divider
- 标题位置至少 3 种不同位置
- 至少 3 页使用非对称布局
