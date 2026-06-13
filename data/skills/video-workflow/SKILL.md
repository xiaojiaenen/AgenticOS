---
name: video-workflow
description: 视频创作工作流——单帧/多帧视频生成流程、content-graph 规范、模板选择指南、HTML 动画最佳实践。每次视频任务开始时加载。
version: 1.0.0
tags: [video, workflow, content-graph, animation, html]
when_to_use: 开始视频创作任务时，加载此工作流以获取创作步骤和规范
allowed_tools: [video_search_templates, video_list_templates, video_get_template, video_create_project, video_set_template, video_set_variables, video_write_content_graph, video_write_frame_html, video_write_preview_html, video_export_mp4, video_list_projects]
required_tools: []
---

# 视频创作工作流

视频创作的完整流程、执行纪律和操作规范。

---

## 一、视频类型

### 单帧视频（快速路径）

**适用场景**：
- 简单的标题动画
- 数据展示（单个图表）
- Logo 动画
- 短片头/片尾

**特点**：
- 一个 HTML 文件包含所有动画
- 渲染速度快
- 适合 3-10 秒的短视频

### 多帧视频（Storyboard 路径）

**适用场景**：
- 产品宣传片
- 数据故事（多个数据点）
- 教程/解说视频
- 复杂叙事

**特点**：
- 多个 HTML 文件，每帧一个
- 支持不同模板混合
- 可控制每帧时长
- 适合 10-60 秒的视频

---

## 二、创作流程

### 单帧视频流程

```
Step 1: 理解需求
  → 分析用户意图（标题动画？数据展示？产品展示？）
  → 确定时长、风格、内容

Step 2: 搜索模板
  → video_search_templates(intent, top_n=5)
  → 根据类别和标签选择最匹配的模板

Step 3: 创建项目
  → video_create_project(name, intent)

Step 4: 设置模板
  → video_set_template(project_id, template_id)
  → 系统会自动注入模板的 SKILL.md 设计规范

Step 5: 设置变量
  → video_set_variables(project_id, {key: value, ...})
  → 变量名参考模板的 inputs schema

Step 6: 生成 HTML
  → video_write_preview_html(project_id, html)
  → HTML 必须自包含（内联 CSS + JS）
  → 可引用 Google Fonts 和 GSAP CDN

Step 7: 导出视频
  → video_export_mp4(project_id, resolution, fps)
  → 等待渲染完成
```

### 多帧视频流程

```
Step 1: 理解需求
  → 分析用户意图
  → 规划帧数、顺序、每帧内容

Step 2: 搜索模板
  → video_search_templates(intent)
  → 可以为不同帧选择不同模板

Step 3: 创建项目
  → video_create_project(name, intent)

Step 4: 设置模板（可选）
  → video_set_template(project_id, template_id)
  → 多帧视频可以不设置全局模板

Step 5: 写入 Storyboard
  → video_write_content_graph(project_id, graph)
  → 定义节点（帧）和边（顺序/依赖）

Step 6: 为每帧生成 HTML
  → 循环调用 video_write_frame_html(project_id, node_id, html)
  → 每帧 HTML 独立，但风格应统一

Step 7: 导出视频
  → video_export_mp4(project_id, resolution, fps)
  → 系统自动拼接所有帧
```

---

## 三、Content-Graph 规范

### 基本结构

```json
{
  "schemaVersion": 1,
  "intent": "explainer",
  "synopsis": "视频简介",
  "nodes": [
    {
      "id": "intro",
      "kind": "text",
      "text": "欢迎观看",
      "durationSec": 3
    },
    {
      "id": "data",
      "kind": "data",
      "data": {"values": [10, 20, 30]},
      "durationSec": 5
    },
    {
      "id": "outro",
      "kind": "text",
      "text": "感谢观看",
      "durationSec": 3
    }
  ],
  "edges": [
    {"from": "intro", "to": "data", "kind": "sequence"},
    {"from": "data", "to": "outro", "kind": "sequence"}
  ]
}
```

### 节点类型

| 类型 | 用途 | 必需字段 |
|------|------|---------|
| `text` | 文本内容（标题、说明） | `text` |
| `data` | 数据内容（图表、统计） | `data` |
| `entity` | 实体（Logo、品牌） | `props` |

### 边类型

| 类型 | 用途 | 说明 |
|------|------|------|
| `sequence` | 顺序关系 | 软偏好，影响默认播放顺序 |
| `dependency` | 依赖关系 | 硬约束，必须按此顺序 |
| `contrast` | 对比关系 | 不影响顺序，用于语义标记 |

### 时长建议

| 内容类型 | 建议时长 |
|---------|---------|
| 标题/开场 | 2-3 秒 |
| 数据展示 | 4-6 秒 |
| 文字说明 | 3-5 秒 |
| 转场 | 1-2 秒 |
| 结尾/CTA | 2-3 秒 |

---

## 四、HTML 动画规范

### 基本要求

1. **自包含**：所有样式和脚本内联在 HTML 中
2. **无外部依赖**：除 Google Fonts 和 GSAP CDN 外，不依赖其他资源
3. **响应式**：使用相对单位（vw, vh, %），适配不同分辨率
4. **性能优化**：避免复杂的 CSS 选择器，减少重绘重排

### CSS 动画

```css
/* 使用 @keyframes 定义动画 */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 应用动画 */
.title {
  animation: fadeIn 1s ease-out forwards;
  animation-delay: 0.5s;
}
```

### GSAP 动画

```html
<!-- 引入 GSAP -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>

<script>
// 使用 GSAP Timeline
const tl = gsap.timeline();
tl.from('.title', { opacity: 0, y: 50, duration: 0.8 })
  .from('.subtitle', { opacity: 0, y: 30, duration: 0.6 }, '-=0.3');
</script>
```

### 字体使用

```html
<!-- 引入 Google Fonts -->
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">

<style>
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
</style>
```

---

## 五、模板选择指南

### 按场景选择

| 场景 | 推荐模板 | 说明 |
|------|---------|------|
| 数据可视化 | frame-data-chart-nyt, frame-nyt-graph, frame-pentagram-stat | 图表动画 |
| 标题动画 | frame-glitch-title, frame-kinetic-type, frame-vignelli | 文字特效 |
| 产品展示 | frame-product-promo, frame-product-promo-30s | 产品宣传 |
| 品牌宣传 | frame-bold-poster, frame-bold-signal, frame-liquid-bg-hero | 视觉冲击 |
| 演示文稿 | frame-swiss-grid, frame-build-minimal | 专业简洁 |
| 解说视频 | frame-decision-tree | 流程图 |
| 片头片尾 | frame-logo-outro | Logo 动画 |
| 氛围背景 | frame-takram-organic, frame-warm-grain | 装饰动画 |

### 按风格选择

| 风格 | 推荐模板 |
|------|---------|
| 科技感 | frame-glitch-title, frame-creative-voltage |
| 极简 | frame-build-minimal, frame-swiss-grid |
| 复古 | frame-bold-poster, frame-light-leak-cinema |
| 活泼 | frame-play-mode, frame-kinetic-type |
| 专业 | frame-vignelli, frame-pentagram-stat |

---

## 六、常见问题

### Q: 渲染失败怎么办？

A: 检查以下几点：
1. HTML 是否自包含（无外部 CSS/JS 文件）
2. 是否有语法错误
3. 图片 URL 是否可访问
4. 系统是否安装了 Chromium 和 ffmpeg

### Q: 动画时长不对怎么办？

A: 
- 单帧视频：通过 `duration` 参数控制
- 多帧视频：在 content-graph 中设置每个节点的 `durationSec`

### Q: 如何让动画更流畅？

A:
1. 使用 `transform` 和 `opacity` 做动画（GPU 加速）
2. 避免动画过程中改变布局属性（width, height, margin）
3. 使用 `will-change` 提示浏览器优化
4. 控制动画元素数量（< 100 个）

### Q: 多帧视频如何保持风格统一？

A:
1. 使用相同的配色方案
2. 使用相同的字体组合
3. 保持相似的动画节奏
4. 使用统一的转场效果
