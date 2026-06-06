---
name: ppt-design-guide
description: PPT 设计规范全集——反 AI-Slop 规则、排版铁律、颜色纪律、SVG 技术约束、图标使用、动画系统、套装风格预设。生成 PPT SVG 前必读。
version: 1.0.0
tags: [ppt, svg, design, presentation]
when_to_use: 生成或编辑 PPT SVG 幻灯片时，必须先加载此技能以获取设计规范
allowed_tools: [save_slide, read_slide, search_icons, calc_chart_positions, check_svg_quality]
required_tools: []
---

# PPT 设计规范全集

生成幻灯片 SVG 时严格遵守以下规范。

---

## 一、SVG 技术黑名单（绝对禁止，否则 PPTX 导出崩溃）

| 禁止 | 正确替代 |
|------|---------|
| `<style>` 标签、`class` 属性 | 内联属性 `fill="..."` `font-size="..."` |
| `<foreignObject>` | `<text>` + `<tspan>`（或 `<span>`）分行 |
| `<mask>` | 渐变叠加 `<rect>`（见下文） |
| `<animate>`, `<set>` | PPTX 原生动画系统自动处理 |
| `rgba(255,255,255,0.1)` | `fill="#FFFFFF" fill-opacity="0.1"` |
| `<g opacity="0.2">` | 每个子元素单独设 `fill-opacity` / `stroke-opacity` |
| `<image opacity="0.3">` | 叠加半透明 `<rect>` |
| 缺少 `viewBox` | `<svg viewBox="0 0 1280 720" ...>` |
| 文本含未转义 `&` | `&amp;`（如 `研发 &amp; 市场`） |
| HTML 命名实体 `&mdash;` `&copy;` `&nbsp;` | 原生 Unicode：`—` `©` ` ` |

### XML 严格性（无例外）

`<svg>` 根元素必须包含 `viewBox="0 0 1280 720"`。所有页面使用相同 viewBox。

XML 保留字符必须转义：`&` → `&amp;`，`<` → `&lt;`，`>` → `&gt;`，`"` → `&quot;`

✅ `fill="var(--text-2)"` ❌ `fill='var(--text-2)'`
✅ `研发 &amp; 市场` ❌ `研发 & 市场`
✅ `—` `©` `→` ❌ `&mdash;` `&copy;` `&rarr;`

### 禁用的 SVG 特性

- `<style>`, `class` 属性 → 用内联属性
- `<foreignObject>` → 用 `<text>` + `<tspan>`
- `<mask>` → 用半透明 `<rect>` 叠加
- `<symbol>` + `<use>` → 直接内联元素
- `<textPath>` → 用 `<text>` 定位
- `@font-face` → 用系统字体栈
- `<animate>`, `<set>`, `<script>`, `<iframe>` → 禁止
- `filter` 属性中的 `feComponentTransfer` → 禁止
- 纯黑阴影 `#000000` 高 opacity → 用 `#0F172A` + 低 opacity

### 条件允许的特性

- `<marker>` → 箭头/端点可用
- `<clipPath>` → 裁剪可用（不嵌套）
- `stroke-dasharray` → 虚线可用：`4,4`=Dash, `2,2`=Dot, `8,4`=长划线
- `text-decoration="underline"` / `"line-through"` → 直接可用
- `transform` → 简单平移/旋转可用，避免嵌套

---

## 二、图标嵌入语法

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

---

## 三、内联文本排版（tspan / span 铁律）

同一个逻辑行的文字（即使混合颜色/粗细/大小）**必须用单个 `<text>` + `<tspan>`（或 `<span>`）子元素**——拆分多个 `<text>` 会导致 PPT 中各行独立无法对齐编辑。

✅ 正确：
```svg
<text x="100" y="200" font-size="24" fill="var(--text-1)">
  实现<tspan fill="var(--accent)" font-weight="bold">10倍</tspan>效率提升
</text>
```

❌ 错误：
```svg
<text x="100" y="200">实现</text>
<text x="160" y="200" fill="var(--accent)">10倍</text>
<text x="240" y="200">效率提升</text>
```

**数值结果（百分比/倍数/金额）和对比词（涨/降）必须加粗高亮。**

---

## 四、阴影与滤镜（克制使用）

阴影用于真正浮动的元素（卡片浮在照片上、CTA 按钮、推荐卡），**同级网格卡片全部用平面无阴影**。每页最多 2-3 个阴影元素。

**标准柔阴影**（flood-opacity 0.06-0.12）：
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

**标题发光**（无 offset 的 `feGaussianBlur`）：
```svg
<filter id="titleGlow" x="-30%" y="-30%" width="160%" height="160%">
  <feGaussianBlur in="SourceAlpha" stdDeviation="6"/>
  <feFlood flood-color="var(--accent)" flood-opacity="0.40"/>
  ...
</filter>
```

不使用 shadow 的场景：背景面板、分割线、同级网格卡片、深色背景页。

---

## 五、图片与渐变叠加

**外部图片引用**（后处理自动内嵌）：
```svg
<image href="../images/photo.jpg" x="0" y="0" width="1280" height="720"
       preserveAspectRatio="xMidYMid slice"/>
```

**图片上叠加渐变**：
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

---

## 六、元素分组与 PPTX 动画

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

### Chrome 分组（跳过动画）

`id` 中包含以下关键词的组被自动识别为**页面装饰**，不参与入场动画：

`background` `bg` `decoration` `decor` `header` `footer` `chrome` `watermark` `pagenumber` `pagenum`

### 入场动画（25 种）

内容组按顺序级联入场（`after-previous`，每个 0.3 秒）。可用效果：

`appear` `fade` `fly` `cut` `zoom` `wipe` `split` `blinds` `checkerboard` `dissolve` `random_bars` `peek` `wheel` `box` `circle` `diamond` `plus` `strips` `wedge` `stretch` `expand` `swivel` `flash_once` `crawl` `float_in`

### 强调动画（20 种）

`pulse` `spin` `grow_shrink` `teeter` `color_pulse` `desaturate` `darken` `lighten` `transparency` `object_color` `complementary_color` `line_color` `fill_color` `brush_color` `font_color` `underline` `bold_flash` `bold_reveal` `wave` `float`

### 退出动画（15 种）

`fade_out` `fly_out` `wipe_out` `zoom_out` `dissolve_out` `shrink_out` `disappear` `fly_out_left` `fly_out_right` `fly_out_up` `fly_out_down` `wipe_out_left` `wipe_out_up` `wipe_out_right` `wipe_out_down`

### 转场（43 种）

**基础：** `fade` `push` `wipe` `split` `strips` `cover` `random`
**方向变体：** `push-left` `push-up` `push-down` `wipe-left` `wipe-up` `wipe-down` `split-vertical` `split-in` `cover-left` `cover-up` `cover-down` `uncover`
**高级：** `dissolve` `pan` `pan-left` `pan-up` `pan-down` `zoom` `zoom-out` `cube` `cube-left` `glitter` `glitter-left` `vortex` `vortex-left` `ripple` `honeycomb` `wind` `wind-left` `ferris` `flash` `gallery` `gallery-left` `doors` `doors-horizontal` `newsflash` `switch` `switch-left` `flythrough` `flythrough-out`

---

## 七、设计工艺铁律（Design Craft Rules）

### 反 AI-Slop 七宗罪（每次创作前自检）

1. **禁止默认 Indigo 强调色**：绝对不写 `#6366f1`、`#4f46e5`、`#8b5cf6` 等 Tailwind indigo/紫罗兰色值。用 `var(--accent)` 引用主题强调色。
2. **禁止「信任感」双色渐变 Hero**：紫色→蓝色、蓝色→青色、indigo→粉色等双色渐变 Hero 背景是第二常见 AI 指纹。纯色背景 + 排版层次感完胜。
3. **禁止 Emoji 作为功能图标**：幻灯片中不使用 ✨🚀🎯 等 emoji 作为装饰或图标。用 search_icons 搜索真实图标。
4. **字体纪律——展示文本用展示字体**：标题/封面/章节分隔页用 `font-family="Playfair Display, Noto Serif SC, serif"`（衬线）或粗重 sans，正文用 `"Inter, Noto Sans SC, sans-serif"`。不要全篇一种字体。
5. **禁止「圆角卡片 + 左侧 accent 竖条」**：这是最典型的 AI dashboard 模式——圆角卡片左边贴一条 `fill="var(--accent)"` 的窄矩形。要么去掉圆角，要么去掉左侧竖条。
6. **禁止捏造数据**："10 倍提升"、"99.9% 可用"、"3 倍效率"——要么用真实数据，要么标注「示意数据」。
7. **禁止 Lorem Ipsum 占位文字**：空白区域是设计问题，用排版解决，不要用假文字填充。

### 排版铁律

| 场景 | 字号 | 字重 | 行距 |
|------|------|------|------|
| 封面主标题 | 48–72px | 700–800 | 1.0–1.2 |
| 页面标题 | 28–40px | 600–700 | 1.2 |
| 正文 | 15–18px | 400 | 1.5–1.6 |
| 辅助/脚注 | 12–14px | 400 | 1.5 |

- 每页最多 3 种字号
- 正文与卡片边缘留白 ≥ 24px，标题与正文间距 ≥ 16px
- 正文行宽控制在 45–75 字符
- **严禁正文两端对齐**

### 颜色纪律

- **每页 accent 色可见使用不超过 2 处**
- **前景背景对比度**：正文文字 ≥ 4.5:1，大号文字 ≥ 3:1
- **暗色背景**：背景不用纯黑 `#000`，用 `var(--bg)`；文字不用纯白，用 `var(--text-1)`
- **中性色占画面 70–90%**，accent 占 5–10%

### 节奏与呼吸

- 连续两页不要视觉密度相同——紧接松、满版接留白、数据页后接 big-quote 或 section-divider
- 装饰元素每页不超过 2 个
- ~80% 验证过的模式 + ~20% 有意的差异化选择

### 排版层级铁律

每页必须满足三个条件：
1. **一个主导入口**：有且仅有一个元素在视觉上胜出
2. **层级间有意图的节奏**：相邻层级至少有一个维度有 >=1.25x 的跳跃
3. **信息流可恢复**：即使层级被颠倒，读者仍能重建内容结构

**五种层级向量**（至少用两种）：Scale、Weight、Spacing、Tracking、Alignment

**三层工作模型**：
| 层级 | 角色 | 典型向量 |
|------|------|---------|
| Primary | 入口点，每页一个 | Scale + Spacing 或 Alignment break |
| Secondary | 结构支撑 | Weight + Scale step |
| Tertiary | 附属：标签、图例、脚注 | Scale reduction + Weight reduction |

### 认知与感知法则

- **邻近律**：组内间距 8-16px，组间间距 32-64px
- **相似律**：同类型卡片/按钮必须共享相同的视觉处理
- **Hick 定律**：每页决策选项不超过 3-5 个
- **认知负荷**：差布局/术语/视觉噪音完全由设计者控制

---

## 八、布局变化 8 条铁律

1. **标题位置变化**：至少 3 种不同位置（左上、居中、右上、底部居中等）
2. **间距变化 ±30%**：不要每页相同间距
3. **列数变化**：单栏、双栏、三栏交替
4. **非对称布局**：至少 3 页使用非对称设计
5. **元素数量变化**：3 个、5 个、7 个交替
6. **装饰位移**：装饰元素不要总在同一位置
7. **视觉密度交替**：密集页后接留白页
8. **字号变化**：同级标题不要每页相同字号

---

## 九、图表绘制规范

SVG 模式下所有图表用原生 SVG 元素绘制：

- **柱状图**：`<rect>` 横向或纵向排列，带数值标签 `<text>`
- **折线图**：`<polyline>` 连接数据点，`<circle>` 标记数据点，可选 `<polygon>` 做面积填充
- **饼图/环形图**：`<path>` 扇形，用 arc 命令；环形图在中心放 `<circle fill="var(--bg)"/>`
- **雷达图**：`<polygon>` 封闭数据区域，`<line>` 做轴线
- **表格**：`<rect>` 画行背景（交替色），`<line>` 画网格线，`<text>` 写内容

图表必须包含：坐标轴/图例、数据标签、有意义的示意数据。

**进阶图表**：漏斗图、桑基图、热力图、矩形树图、瀑布图等，请参考 `ppt-template-library` skill 中的图表模板。

---

## 十、Token 语义速查

所有颜色使用 `var(--token)` 引用，具体色值由主题 CSS 决定。**禁止写死 hex 值。**

### 颜色 Token

| Token | 用途 |
|-------|------|
| `--bg` | 幻灯片背景 |
| `--bg-soft` | 柔化背景 |
| `--surface` | 卡片/面板背景 |
| `--surface-2` | 次级面板背景 |
| `--border` | 边框/分割线 |
| `--border-strong` | 强调边框 |
| `--text-1` | 一级文字（标题） |
| `--text-2` | 二级文字（正文） |
| `--text-3` | 三级文字（弱化信息） |
| `--accent` | 品牌强调色 |
| `--accent-2` | 次要强调色 |
| `--accent-3` | 第三强调色 |
| `--good` | 正向语义色 |
| `--warn` | 警告语义色 |
| `--bad` | 负面语义色 |

### 非颜色 Token（直接写值，不使用 var()）

| Token | SVG 用法 |
|-------|---------|
| `--radius` | `rx="12"` |
| `--radius-sm` | `rx="8"` |
| `--radius-lg` | `rx="20"` |
| `--font-sans` | `font-family="Inter,Noto Sans SC,sans-serif"` |
| `--font-serif` | `font-family="Playfair Display,Noto Serif SC,serif"` |
| `--font-mono` | `font-family="JetBrains Mono,monospace"` |

---

## 十一、套装风格预设（可选）

当用户有明确风格偏好时，从下表选择最匹配的风格并应用其原则。

| 风格 | 关键词 | 展示字体 | 推荐主题 |
|------|--------|---------|---------|
| 编辑墨水 | 投资报告 / 战略提案 | Playfair Display | kami, paper, editorial |
| 现代极简 | 产品发布 / SaaS 汇报 | Inter | github, apple, minimal |
| 大胆宣言 | 品牌发布会 / 创意提案 | Inter | neo-brutalism, nike, spotify |
| 科技暗色 | 开发者大会 / 安全报告 | JetBrains Mono | dracula, tokyo-night, monokai |
| 温暖人文 | 品牌故事 / 用户研究 | Playfair Display | airbnb, pinterest, xiaohongshu |
| 数据驱动 | 季度财报 / 数据分析 | Inter | stripe, corporate, enterprise |
| 创意实验 | 设计作品集 / 艺术展览 | Playfair Display | glassmorphism, vaporwave, bauhaus |
| 瑞士国际 | 商业报告 / AI 提案 | Inter Tight | klein-blue, swiss-grid, minimal |

### 瑞士国际主义特别约束

- **只用直角**：所有 rect 的 rx/ry=0，严禁圆角
- **1px hairline 边框**：`stroke="var(--border)" stroke-width="1"`，严禁阴影/gradient/blur
- **极端字号反差**：封面标题 48-72px，正文 14-16px，标签 11px uppercase
- **16 列隐式网格**：元素对齐到 1280/16=80px 列网格
- **单一饱和 accent**：整份 deck 仅用一个高饱和强调色

---

## 十二、品牌资产协议（借鉴 huashu-design）

当用户提到特定品牌（如"用 Apple 风格"、"参考 Stripe 的设计"）时，必须先确认品牌视觉规范：

### 5 步硬流程

1. **询问资产**：用户是否有品牌 logo/色板/字体文件？
2. **搜索确认**：从注入的主题列表中确认品牌对应的主题
3. **确认规范**：明确以下参数——
   - 主色 / 辅色 / 中性色
   - 字体组合（标题/正文）
   - logo 使用方式（有/无/位置）
   - 图标风格（实心/描边/品牌专属）
4. **写入 spec_lock**：将品牌规范写入 spec_lock 的 colors/typography/icons 节
5. **冻结确认**：告知用户"品牌规范已锁定，后续页面将严格遵循"

### 禁止行为

- 不要凭记忆使用品牌色——必须从主题列表确认
- 不要自行发明品牌字体——必须使用系统中已有的字体
- 不要在品牌 deck 中混用其他品牌的视觉元素
