---
name: ppt-svg-reference
description: PPT SVG 技术规范参考——SVG 黑名单、图标嵌入、tspan 排版、阴影滤镜、图片渐变、图表绘制。当 AI 生成 PPT SVG 时需要查阅这些技术细节。
---

PPT SVG 生成的技术规范参考。生成幻灯片 SVG 时严格遵守以下规范。

## SVG 技术黑名单（绝对禁止，否则 PPTX 导出崩溃）

| 禁止 | 正确替代 |
|------|---------|
| `<style>` 标签、`class` 属性 | 内联属性 `fill="..."` `font-size="..."` |
| `<foreignObject>` | `<text>` + `<tspan>` 分行 |
| `<mask>` | 渐变叠加 `<rect>`（见下文） |
| `<animate>`, `<set>` | PPTX 原生动画系统自动处理 |
| `rgba(255,255,255,0.1)` | `fill="#FFFFFF" fill-opacity="0.1"` |
| `<g opacity="0.2">` | 每个子元素单独设 `fill-opacity` / `stroke-opacity` |
| `<image opacity="0.3">` | 叠加半透明 `<rect>` |

## 图标嵌入语法

支持的图标放在 `<g id="...">` 内部，用 `<use>` 占位，后处理管线自动内嵌：

| 图标库 | 前缀 | viewBox | 风格 |
|--------|------|---------|------|
| `chunk-filled` | `chunk-filled/name` | 16×16 | 实心填充 |
| `tabler-filled` | `tabler-filled/name` | 24×24 | 实心填充 |
| `tabler-outline` | `tabler-outline/name` | 24×24 | 描边风格（可选 `stroke-width`） |
| `phosphor-duotone` | `phosphor-duotone/name` | 256×256 | 双色调 |
| `simple-icons` | `simple-icons/name` | 24×24 | 品牌 logo |

```svg
<g id="feature-icon">
  <use data-icon="chunk-filled/rocket" x="100" y="200" width="48" height="48" fill="var(--accent)"/>
</g>
```

**一页用一种图标库，不要混用。** 先用 `search_icons` 工具搜索需要的图标名，图标名严格从搜索结果中复制，禁止自创图标名。

## 内联文本排版（tspan 铁律）

同一个逻辑行的文字（即使混合颜色/粗细/大小）**必须用单个 `<text>` + `<tspan>` 子元素**——拆分多个 `<text>` 会导致 PPT 中各行独立无法对齐编辑。

✅ 正确——一个 `<text>`，三个 run：
```svg
<text x="100" y="200" font-size="24" fill="var(--text-1)">
  实现<tspan fill="var(--accent)" font-weight="bold">10倍</tspan>效率提升
</text>
```

❌ 错误——三个独立 `<text>`，PPT 中变成三个文本框：
```svg
<text x="100" y="200">实现</text>
<text x="160" y="200" fill="var(--accent)">10倍</text>
<text x="240" y="200">效率提升</text>
```

**数值结果（百分比/倍数/金额）和对比词（涨/降）必须加粗高亮。**

## 阴影与滤镜（克制使用）

阴影用于真正浮动的元素（卡片浮在照片上、CTA 按钮、推荐卡），**同级网格卡片全部用平面无阴影**。每页最多 2-3 个阴影元素。

**标准柔阴影**（flood-opacity 0.06-0.12）——PPTX 自动转换为原生 `<a:outerShdw>`：
```svg
<defs>
  <filter id="softShadow" x="-15%" y="-15%" width="140%" height="140%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="8"/>
    <feOffset dx="0" dy="4"/>
    <feFlood flood-color="#000000" flood-opacity="0.08"/>
    <feComposite in="..." in2="..." operator="in"/>
    <feMerge>
      <feMergeNode in="..."/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
</defs>
```

**标题发光**（无 offset 的 `feGaussianBlur` → PPTX 原生 `<a:glow>`）：
```svg
<filter id="titleGlow" x="-30%" y="-30%" width="160%" height="160%">
  <feGaussianBlur in="SourceAlpha" stdDeviation="6"/>
  <feFlood flood-color="var(--accent)" flood-opacity="0.40"/>
  ...
</filter>
```

不使用 shadow 的场景：背景面板、分割线、同级网格卡片、深色背景页。

## 图片与渐变叠加

**外部图片引用**（后处理自动内嵌）：
```svg
<image href="../images/photo.jpg" x="0" y="0" width="1280" height="720"
       preserveAspectRatio="xMidYMid slice"/>
```

**图片上叠加渐变**（文字放在图片上方时必备）：
```svg
<defs>
  <linearGradient id="imgOverlay" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="var(--bg)" stop-opacity="0.85"/>
    <stop offset="55%" stop-color="var(--bg)" stop-opacity="0.30"/>
    <stop offset="100%" stop-color="var(--bg)" stop-opacity="0"/>
  </linearGradient>
</defs>
<image href="../images/bg.jpg" x="0" y="0" width="1280" height="720" preserveAspectRatio="xMidYMid slice"/>
<rect x="0" y="0" width="1280" height="720" fill="url(#imgOverlay)"/>
```

**`stroke-dasharray`（虚线）**：`4,4`=Dash, `2,2`=Dot, `8,4`=长划线
**`text-decoration="underline"` / `"line-through"`** 直接可用

## 图表绘制规范

SVG 模式下不使用 Chart.js，所有图表用原生 SVG 元素绘制：

- **柱状图**：`<rect>` 横向或纵向排列，带数值标签 `<text>`
- **折线图**：`<polyline>` 连接数据点，`<circle>` 标记数据点，可选 `<polygon>` 做面积填充
- **饼图/环形图**：`<path>` 扇形，用 arc 命令；环形图在中心放 `<circle fill="var(--bg)"/>`
- **雷达图**：`<polygon>` 封闭数据区域，`<line>` 做轴线
- **表格**：`<rect>` 画行背景（交替色），`<line>` 画网格线，`<text>` 写内容

图表必须包含：坐标轴/图例、数据标签、有意义的示意数据。

## 元素分组与 PPTX 动画

### 分组原则

每页 SVG 的顶层 `<g id="...">` 语义分组是 PPTX 导出正确工作的前提：

- 每个 `<g id>` 在 PowerPoint 中变成一个可编辑的组合
- 动画系统将每个 `<g id>` 作为一个入场组来播放
- **每页 3-8 个内容组**（页面装饰不算在内）

```svg
<g id="card-1">
  <rect x="60" y="400" width="565" height="260" rx="20" fill="var(--surface)"/>
  <use data-icon="chunk-filled/chart" x="105" y="430" width="28" height="28" fill="var(--accent)"/>
  <text x="105" y="470" font-size="32" font-weight="bold" fill="var(--text-1)">关键指标</text>
</g>
```

分组粒度参考：

| 分组单元 | 包含内容 |
|----------|---------|
| 卡片/面板 | 背景 rect + 阴影（仅浮动时） + 图标 + 标题 + 正文 |
| 流程步骤 | 数字圈 + 图标 + 标签 + 描述 |
| 列表项 | 项目符号 + 图标 + 标题 + 描述 |
| 页面标题 | 标题 + 副标题 + 装饰线 |
| 页脚 | 页码 + 品牌标识 |

### Chrome 分组（跳过动画）

`id` 中包含以下关键词的组被自动识别为**页面装饰**，不参与入场动画，随幻灯片一起出现：

`background` `bg` `decoration` `decor` `header` `footer` `chrome` `watermark` `pagenumber` `pagenum`

```svg
<!-- bg-layer 自动跳过动画 → 背景直接出现 -->
<g id="bg-layer">
  <rect width="1280" height="720" fill="var(--bg)"/>
</g>

<!-- 正常的内容组 → 参与入场动画 -->
<g id="card-1">
  <rect x="60" y="400" width="565" height="260" rx="20" fill="var(--surface)"/>
</g>
```

### 入场动画（21 种）

内容组按顺序级联入场（`after-previous`，每个 0.3 秒）。可用效果：

`appear` `fade` `fly` `cut` `zoom` `wipe` `split` `blinds` `checkerboard` `dissolve` `random_bars` `peek` `wheel` `box` `circle` `diamond` `plus` `strips` `wedge` `stretch` `expand` `swivel`

默认行为：首个 fade，其余效果由动画引擎按 `mixed` 模式循环分配。可在导出时指定具体效果或 `random` 随机分配。

### 转场（7 种）

页面之间的切换效果（默认 `fade`，0.5 秒）：

`fade` `push` `wipe` `split` `strips` `cover` `random`
