---
name: video-design-guide
description: HTML 动画设计指南——参考原版 html-video 模板的 5 层叠放、配色纪律、GSAP 编排、装饰层工具箱。生成视频 HTML 时必须加载。
version: 2.0.0
tags: [video, design, css, animation, gsap, html, motion-graphics]
when_to_use: 生成视频 HTML 前，加载此指南以获取专业级设计规范
allowed_tools: []
required_tools: []
---

# HTML 动画设计指南（基于原版 html-video 模板）

**你的视频必须看起来像专业 Motion Graphics，而不是 PPT 录屏！**

---

## 一、5 层叠放规范（必须遵循）

所有模板必须遵循从底到顶的标准层叠：

```
Layer 1: 背景色/渐变          z-index: 0
Layer 2: 网格/纹理底层        z-index: 1; opacity: 3-5%
Layer 3: 主内容层             z-index: 2-10
Layer 4: 噪点 grain 层        z-index: 20; opacity: 6-14%; mix-blend-mode: overlay
Layer 5: 暗角 vignette 层      z-index: 30; pointer-events: none
```

### Layer 1: 背景

```css
/* 深色背景 */
body {
  background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
}

/* 浅色背景 (NYT 风格) */
body {
  background: #f7f5ee;
}

/* 流体背景 */
body {
  background: #1e1b4b;
}
```

### Layer 2: 网格/纹理底层

```css
/* 细网格底纹 */
body::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
  opacity: 0.03;
  background-image:
    linear-gradient(rgba(255,255,255,1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,1) 1px, transparent 1px);
  background-size: 64px 64px;
}

/* 扫描线 */
body::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
  background-image: repeating-linear-gradient(
    0deg,
    rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 1px,
    transparent 1px, transparent 3px
  );
  mix-blend-mode: multiply;
  opacity: 0.6;
}
```

### Layer 3: 主内容层

```css
.content {
  position: relative;
  z-index: 5;
}
```

### Layer 4: 噪点 Grain 层

```css
.grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 20;
  opacity: 0.1;
  mix-blend-mode: overlay;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)'/%3E%3C/svg%3E");
}
```

### Layer 5: 暗角 Vignette 层

```css
.vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 30;
  background: radial-gradient(circle at center, transparent 50%, rgba(0,0,0,0.7) 100%);
}
```

---

## 二、配色纪律（5 套预设）

**严格限制色板**：每个模板只用 1 个主色 + 1 个强调色 + 黑白灰。**严禁全彩虹！**

### 预设 1: Cyberpunk（赛博朋克）

```css
:root {
  --bg: #0d0e10;
  --text: #f5f5f7;
  --accent-1: #00f0ff;    /* cyan */
  --accent-2: #ff2bd6;    /* magenta */
  --warning: #ffb547;     /* amber */
}
```

### 预设 2: Aurora Violet（极光紫）

```css
:root {
  --bg: #1e1b4b;
  --text: #fafaf8;
  --accent-1: #a78bfa;    /* 淡紫 */
  --accent-2: #7c5cff;    /* 亮紫 */
  --accent-3: #ec4899;    /* 粉 */
  --accent-4: #06b6d4;    /* 青 */
}
```

### 预设 3: NYT Editorial（纽约时报）

```css
:root {
  --bg: #f7f5ee;
  --text: #1a1a1a;
  --accent: #a91d1d;      /* NYT 红 */
  --muted: #666;
}
```

### 预设 4: Swiss Navy（瑞士海军）

```css
:root {
  --bg: #f2f2f2;
  --text: #0a1e3d;
  --accent: #d4a017;      /* 金色 */
  --border: #0a1e3d;
}
```

### 预设 5: Cinema Amber（电影琥珀）

```css
:root {
  --bg: #1a0d08;
  --text: #f5f0e8;
  --accent: #ffb547;      /* 暖橙 */
  --muted: #8b7355;
}
```

---

## 三、字体栈模板化（3 套预设）

### 预设 1: Editorial（编辑风格）

```html
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  .display { font-family: 'Source Serif 4', Georgia, serif; }
  .body { font-family: 'IBM Plex Sans', 'Noto Sans SC', sans-serif; }
  .mono { font-family: 'IBM Plex Mono', monospace; }
</style>
```

### 预设 2: Modern（现代风格）

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=Noto+Sans+SC:wght@400;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  .display { font-family: 'Inter', 'Noto Sans SC', sans-serif; font-weight: 800; }
  .body { font-family: 'Inter', 'Noto Sans SC', sans-serif; }
  .mono { font-family: 'JetBrains Mono', monospace; }
</style>
```

### 预设 3: Display（展示风格）

```html
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700&family=Libre+Baskerville:wght@400;700&family=Noto+Sans+SC:wght@400;700&display=swap" rel="stylesheet">
<style>
  .display { font-family: 'Libre Baskerville', 'Noto Sans SC', serif; }
  .body { font-family: 'Space Grotesk', 'Noto Sans SC', sans-serif; }
  .mono { font-family: 'Space Grotesk', monospace; }
</style>
```

### 字号规律

```css
/* 主标题：响应式大字 */
h1 { font-size: clamp(48px, 7vw, 200px); }

/* 副标题/标签 */
.label {
  font-size: 11-24px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
}

/* 数据标注 */
.data-label {
  font-size: 10.5px;
  font-family: monospace;
}
```

---

## 四、动画实现路径

### 路径 A: 纯 CSS @keyframes（适合简单、自循环动画）

**使用场景**：blob 浮动、glitch 抖动、stroke 绘制、fade/slide 入场

```css
/* Blob 流体浮动 */
.blob {
  position: absolute;
  border-radius: 50%;
  mix-blend-mode: screen;
  filter: blur(70px);
  will-change: transform;
}

@keyframes float1 {
  0%, 100% { transform: translate(0,0) scale(1); }
  50% { transform: translate(80px,-60px) scale(1.15); }
}

.b1 {
  width: 600px; height: 600px;
  background: #a78bfa;
  top: -100px; left: -100px;
  animation: float1 12s ease-in-out infinite;
}

/* Glitch 抖动（长静短爆） */
@keyframes glitch {
  0%, 92%, 100% { transform: translate(0,0); filter: none; }
  93% { transform: translate(-6px, 1px); filter: url(#rgb); }
  94% { transform: translate(8px, -2px); filter: url(#rgb); }
  95% { transform: translate(-4px, 2px); }
  96% { transform: translate(4px, -1px); filter: url(#rgb); }
  97% { transform: translate(0,0); }
}

.glitch-host { animation: glitch 4s infinite; }

/* SVG Stroke 绘制 */
@keyframes draw {
  from { stroke-dashoffset: 1000; }
  to { stroke-dashoffset: 0; }
}

.line {
  stroke-dasharray: 1000;
  animation: draw 1.4s ease-out 0.4s forwards;
}
```

### 路径 B: GSAP Timeline（适合精确编排、多场景切换）

**使用场景**：场景转场、复杂 stagger、精确时间点触发

```javascript
// 必须引入 GSAP
// <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>

const tl = gsap.timeline({ defaults: { duration: 0.8, ease: 'power3.out' } });

// 元素依次入场
tl.from('.title', { y: 100, opacity: 0, scale: 0.8 })
  .from('.subtitle', { y: 50, opacity: 0 }, '-=0.4')
  .from('.decor', { scale: 0, opacity: 0, stagger: 0.1 }, '-=0.2');

// 文字逐词入场
tl.to('.word', {
  opacity: 1, y: 0, stagger: 0.15, duration: 0.5, ease: 'power2.out'
});

// 横线展开
tl.to('.rule', { width: 300, duration: 0.4 });

// 场景切换（白色擦除转场）
tl.to('#white-wipe', { xPercent: 0, duration: 0.2, ease: 'power2.in' });
tl.set('#scene-1', { opacity: 0 });
tl.to('#white-wipe', { xPercent: 100, duration: 0.2, ease: 'power2.out' });
```

---

## 五、缓动函数速查

| 场景 | GSAP 缓动 | CSS 缓动 |
|------|-----------|----------|
| 入场 | `power3.out`, `expo.out` | `cubic-bezier(0.16,1,0.3,1)` |
| 弹性 | `back.out(1.7)` | `cubic-bezier(0.34,1.56,0.64,1)` |
| 出场 | `power2.in`, `expo.in` | `ease-in` |
| 平滑 | `power2.inOut` | `ease-in-out` |
| 匀速 | `none` | `linear` |

---

## 六、装饰层工具箱（可插入代码片段）

### SVG RGB 通道分离

```html
<svg width="0" height="0" style="position:absolute">
  <defs>
    <filter id="rgb">
      <feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0"/>
      <feOffset in="SourceGraphic" dx="3" dy="0" result="r"/>
      <feOffset in="SourceGraphic" dx="-3" dy="0" result="b"/>
      <feMerge><feMergeNode in="r"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
</svg>
```

### mix-blend-mode: difference 万能可读文字

```css
.text-diff {
  mix-blend-mode: difference;
  color: #fafaf8;
}
```

---

## 七、动画时长基准

| 类型 | 时长 |
|------|------|
| 简单元素入场 | 0.2-0.5s |
| 场景切换 | 0.2-0.4s |
| 持续循环 | 8-16s |
| Stroke 绘制 | 1.0-1.5s |
| Glitch 爆发 | 0.2s (5% 的周期) |

---

## 八、检查清单

生成 HTML 前必须检查：

- [ ] 5 层叠放完整（背景 → 网格 → 内容 → 噪点 → 暗角）
- [ ] 配色来自预设（严禁全彩虹）
- [ ] 字体栈来自预设（三层：Display + Body + Mono）
- [ ] 使用 GSAP 或 CSS @keyframes 做动画
- [ ] 元素依次入场，有节奏感
- [ ] 至少 2 种装饰效果（grain/vignette/scanlines/grid）
- [ ] 缓动函数正确（入场用 out，出场用 in）
- [ ] `@media (prefers-reduced-motion: reduce)` 无障碍规则
