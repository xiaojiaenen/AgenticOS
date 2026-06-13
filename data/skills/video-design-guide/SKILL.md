---
name: video-design-guide
description: HTML 动画设计指南——CSS 动画、GSAP 技巧、颜色排版规范、性能优化。生成视频 HTML 时参考。
version: 1.0.0
tags: [video, design, css, animation, gsap, html]
when_to_use: 生成视频 HTML 时，加载此指南以获取设计规范和最佳实践
allowed_tools: []
required_tools: []
---

# HTML 动画设计指南

生成高质量 HTML 动画的设计规范和最佳实践。

---

## 一、画布设置

### 基本画布

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1920, height=1080">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      width: 1920px;
      height: 1080px;
      overflow: hidden;
      background: #000;
    }
  </style>
</head>
<body>
  <!-- 内容 -->
</body>
</html>
```

### 常用分辨率

| 场景 | 分辨率 | 比例 |
|------|--------|------|
| 横屏视频 | 1920×1080 | 16:9 |
| 竖屏视频 | 1080×1920 | 9:16 |
| 方形视频 | 1080×1080 | 1:1 |
| 超宽屏 | 2560×1080 | 21:9 |

---

## 二、颜色规范

### 配色原则

1. **主色 + 辅助色 + 强调色**：3 色原则
2. **对比度**：文字与背景对比度 ≥ 4.5:1
3. **一致性**：整个视频保持统一的配色方案

### 推荐配色

```css
/* 科技感 */
:root {
  --bg: #0a0a0a;
  --primary: #00d4ff;
  --secondary: #7c3aed;
  --text: #ffffff;
  --muted: #64748b;
}

/* 极简 */
:root {
  --bg: #ffffff;
  --primary: #0f172a;
  --secondary: #475569;
  --text: #0f172a;
  --muted: #94a3b8;
}

/* 温暖 */
:root {
  --bg: #fef3c7;
  --primary: #d97706;
  --secondary: #dc2626;
  --text: #451a03;
  --muted: #92400e;
}
```

### 渐变使用

```css
/* 线性渐变 */
.gradient-linear {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

/* 径向渐变 */
.gradient-radial {
  background: radial-gradient(circle, #667eea 0%, #764ba2 100%);
}

/* 锥形渐变 */
.gradient-conic {
  background: conic-gradient(from 0deg, #667eea, #764ba2, #667eea);
}
```

---

## 三、字体规范

### 字体选择

```css
/* 西文字体 */
.font-sans { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
.font-serif { font-family: 'Playfair Display', Georgia, serif; }
.font-mono { font-family: 'JetBrains Mono', 'Fira Code', monospace; }

/* 中文字体 */
.font-cn { font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif; }

/* 混合字体 */
.font-mixed {
  font-family: 'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
}
```

### 字号层级

```css
/* 标题层级 */
h1 { font-size: 72px; font-weight: 800; line-height: 1.1; }
h2 { font-size: 48px; font-weight: 700; line-height: 1.2; }
h3 { font-size: 36px; font-weight: 600; line-height: 1.3; }

/* 正文 */
p { font-size: 24px; font-weight: 400; line-height: 1.6; }

/* 小字 */
small { font-size: 16px; font-weight: 400; line-height: 1.5; }
```

### 字体加载

```html
<!-- Google Fonts -->
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">

<!-- 预加载 -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
```

---

## 四、动画规范

### CSS 动画

```css
/* 基础动画 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { transform: translateY(40px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

@keyframes scaleIn {
  from { transform: scale(0.8); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

@keyframes rotateIn {
  from { transform: rotate(-10deg) scale(0.9); opacity: 0; }
  to { transform: rotate(0) scale(1); opacity: 1; }
}

/* 应用动画 */
.animate-fade { animation: fadeIn 0.8s ease-out forwards; }
.animate-slide { animation: slideUp 0.8s ease-out forwards; }
.animate-scale { animation: scaleIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards; }
.animate-rotate { animation: rotateIn 0.8s ease-out forwards; }

/* 延迟 */
.delay-1 { animation-delay: 0.1s; }
.delay-2 { animation-delay: 0.2s; }
.delay-3 { animation-delay: 0.3s; }
.delay-4 { animation-delay: 0.4s; }
.delay-5 { animation-delay: 0.5s; }
```

### GSAP 动画

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>

<script>
// Timeline 动画
const tl = gsap.timeline({ defaults: { duration: 0.8, ease: 'power3.out' } });

tl.from('.title', { y: 50, opacity: 0 })
  .from('.subtitle', { y: 30, opacity: 0 }, '-=0.4')
  .from('.button', { scale: 0.8, opacity: 0 }, '-=0.2');

// 文字逐字动画
const text = document.querySelector('.text');
const chars = text.textContent.split('');
text.innerHTML = chars.map(c => `<span>${c}</span>`).join('');

gsap.from('.text span', {
  opacity: 0,
  y: 20,
  stagger: 0.05,
  duration: 0.5,
  ease: 'back.out(1.7)'
});

// 数字滚动
gsap.to('.number', {
  innerHTML: 100,
  duration: 2,
  snap: { innerHTML: 1 },
  ease: 'power1.inOut'
});
</script>
```

### 缓动函数

```css
/* 常用缓动 */
.ease-out-expo { animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1); }
.ease-out-back { animation-timing-function: cubic-bezier(0.34, 1.56, 0.64, 1); }
.ease-in-out-quart { animation-timing-function: cubic-bezier(0.76, 0, 0.24, 1); }
.ease-spring { animation-timing-function: cubic-bezier(0.175, 0.885, 0.32, 1.275); }
```

---

## 五、布局规范

### 居中布局

```css
/* Flexbox 居中 */
.flex-center {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* Grid 居中 */
.grid-center {
  display: grid;
  place-items: center;
}

/* 绝对定位居中 */
.absolute-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
```

### 网格布局

```css
/* 2 列网格 */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 40px;
}

/* 3 列网格 */
.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 30px;
}

/* 自适应网格 */
.grid-auto {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}
```

---

## 六、性能优化

### GPU 加速

```css
/* 使用 transform 和 opacity 做动画 */
.animate {
  transform: translateX(100px);  /* GPU 加速 */
  opacity: 0.5;                  /* GPU 加速 */
}

/* 避免 */
.animate-bad {
  left: 100px;    /* 触发重排 */
  width: 200px;   /* 触发重排 */
}
```

### will-change 提示

```css
/* 提示浏览器优化 */
.will-animate {
  will-change: transform, opacity;
}

/* 动画结束后移除 */
.animated {
  will-change: auto;
}
```

### 减少重绘

```css
/* 使用 contain */
.contained {
  contain: layout style paint;
}

/* 使用 isolation */
.isolated {
  isolation: isolate;
}
```

---

## 七、常见动画效果

### 淡入淡出

```css
@keyframes fadeInOut {
  0% { opacity: 0; }
  20% { opacity: 1; }
  80% { opacity: 1; }
  100% { opacity: 0; }
}
```

### 弹跳效果

```css
@keyframes bounce {
  0%, 20%, 53%, 80%, 100% {
    animation-timing-function: cubic-bezier(0.215, 0.61, 0.355, 1);
    transform: translate3d(0, 0, 0);
  }
  40%, 43% {
    animation-timing-function: cubic-bezier(0.755, 0.05, 0.855, 0.06);
    transform: translate3d(0, -30px, 0);
  }
  70% {
    animation-timing-function: cubic-bezier(0.755, 0.05, 0.855, 0.06);
    transform: translate3d(0, -15px, 0);
  }
  90% {
    transform: translate3d(0, -4px, 0);
  }
}
```

### 打字机效果

```css
@keyframes typing {
  from { width: 0; }
  to { width: 100%; }
}

@keyframes blink {
  50% { border-color: transparent; }
}

.typewriter {
  overflow: hidden;
  border-right: 2px solid;
  white-space: nowrap;
  animation: typing 2s steps(20) forwards, blink 0.7s step-end infinite;
}
```

### 数字滚动

```html
<div class="counter" data-target="100">0</div>

<script>
const counter = document.querySelector('.counter');
const target = parseInt(counter.dataset.target);

gsap.to(counter, {
  innerHTML: target,
  duration: 2,
  snap: { innerHTML: 1 },
  ease: 'power1.inOut',
  onUpdate: function() {
    counter.textContent = Math.round(this.targets()[0].innerHTML);
  }
});
</script>
```

---

## 八、模板结构

### 单帧模板

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1920, height=1080">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      width: 1920px;
      height: 1080px;
      overflow: hidden;
      background: #0a0a0a;
      font-family: 'Inter', sans-serif;
      color: white;
    }
    /* 样式 */
  </style>
</head>
<body>
  <!-- 内容 -->
  <script>
    // 动画
  </script>
</body>
</html>
```

### 多帧模板

每帧独立一个 HTML 文件，结构相同，内容不同。

---

## 九、检查清单

生成 HTML 前检查：

- [ ] 画布尺寸正确（1920×1080）
- [ ] 字体已加载（Google Fonts 链接）
- [ ] GSAP 已引入（如需要）
- [ ] 所有样式内联
- [ ] 所有脚本内联
- [ ] 无外部资源依赖
- [ ] 动画时长合适
- [ ] 颜色对比度足够
- [ ] 性能优化（transform/opacity）
