# 图文布局模式库

本文档定义了 72 种编号的图文布局技术，分两层自由组合。

---

## Primary Structures（主体结构）— 45 种

### 一、单图布局（1-15）

#### 01. Full Bleed（全出血）
- **用途**：封面、章节页、视觉冲击力强的页面
- **SVG**：`image-layouts/01-full-bleed.svg`
- **特点**：图片铺满整个画布，文字浮于上方
- **适用场景**：封面、产品发布、品牌展示

#### 02. Split Horizontal（水平分割）
- **用途**：图文并排介绍
- **SVG**：`image-layouts/02-split-horizontal.svg`
- **特点**：左图右文或右图左文
- **适用场景**：产品介绍、人物介绍、特性展示

#### 03. Split Vertical（垂直分割）
- **用途**：上图下文或下图上文
- **SVG**：`image-layouts/03-split-vertical.svg`
- **特点**：上下分割，图片占 40-60%
- **适用场景**：案例展示、场景介绍

#### 04. Hero with Overlay（英雄区叠加）
- **用途**：封面、重点页面
- **SVG**：`image-layouts/04-hero-overlay.svg`
- **特点**：大图背景 + 渐变遮罩 + 居中文字
- **适用场景**：封面、章节页

#### 05. Diagonal Split（对角分割）
- **用途**：创意封面、设计展示
- **SVG**：`image-layouts/05-diagonal-split.svg`
- **特点**：对角线分割，视觉动感
- **适用场景**：创意类、设计类主题

#### 06. Circle Frame（圆形框架）
- **用途**：人物介绍、产品特写
- **SVG**：`image-layouts/06-circle-frame.svg`
- **特点**：图片裁剪为圆形
- **适用场景**：团队介绍、产品展示

#### 07. Arch Frame（拱形框架）
- **用途**：优雅的产品展示
- **SVG**：`image-layouts/07-arch-frame.svg`
- **特点**：图片裁剪为拱形
- **适用场景**：高端产品、建筑类

#### 08. Offset Float（偏移浮动）
- **用途**：现代感的图文布局
- **SVG**：`image-layouts/08-offset-float.svg`
- **特点**：图片偏移放置，文字环绕
- **适用场景**：产品特性、功能介绍

#### 09. Text Wrap（文字环绕）
- **用途**：杂志风格排版
- **SVG**：`image-layouts/09-text-wrap.svg`
- **特点**：文字环绕图片
- **适用场景**：编辑类、内容类

#### 10. Corner Accent（角落点缀）
- **用途**：轻量级图文布局
- **SVG**：`image-layouts/10-corner-accent.svg`
- **特点**：小图点缀在角落
- **适用场景**：数据页配图、补充说明

#### 11. Background Texture（背景纹理）
- **用途**：增加视觉层次
- **SVG**：`image-layouts/11-bg-texture.svg`
- **特点**：图片作为纹理背景，降低透明度
- **适用场景**：氛围营造、品牌展示

#### 12. Gradient Mask（渐变遮罩）
- **用途**：文字可读性优化
- **SVG**：`image-layouts/12-gradient-mask.svg`
- **特点**：图片 + 渐变遮罩，确保文字清晰
- **适用场景**：封面、章节页

#### 13. Duotone Effect（双色调）
- **用途**：品牌一致性
- **SVG**：`image-layouts/13-duotone.svg`
- **特点**：图片转为品牌双色调
- **适用场景**：品牌展示、统一视觉

#### 14. Parallax Layers（视差层）
- **用途**：深度感
- **SVG**：`image-layouts/14-parallax.svg`
- **特点**：前景/中景/背景分层
- **适用场景**：创意展示、故事叙述

#### 15. Minimal Frame（极简框架）
- **用途**：干净的图文布局
- **SVG**：`image-layouts/15-minimal-frame.svg`
- **特点**：细线边框 + 大量留白
- **适用场景**：极简风格、高端展示

---

### 二、双图布局（16-30）

#### 16. Duo Side（双图并排）
- **用途**：对比展示
- **SVG**：`image-layouts/16-duo-side.svg`
- **特点**：左右并排两张图
- **适用场景**：前后对比、A/B 对比

#### 17. Duo Stack（双图堆叠）
- **用途**：上下展示
- **SVG**：`image-layouts/17-duo-stack.svg`
- **特点**：上下堆叠两张图
- **适用场景**：流程展示、步骤说明

#### 18. Duo Overlap（双图重叠）
- **用途**：创意叠加
- **SVG**：`image-layouts/18-duo-overlap.svg`
- **特点**：两张图部分重叠
- **适用场景**：创意展示、产品组合

#### 19. Main + Thumbnail（主图+缩略图）
- **用途**：细节展示
- **SVG**：`image-layouts/19-main-thumb.svg`
- **特点**：大图 + 小图组合
- **适用场景**：产品细节、功能展示

#### 20. Before After（前后对比）
- **用途**：效果对比
- **SVG**：`image-layouts/20-before-after.svg`
- **特点**：左右对比，带分割线
- **适用场景**：改造前后、效果对比

#### 21. Split Screen（分屏）
- **用途**：等分展示
- **SVG**：`image-layouts/21-split-screen.svg`
- **特点**：左右等分
- **适用场景**：双栏内容、对比展示

#### 22. Asymmetric Split（不对称分割）
- **用途**：视觉层次
- **SVG**：`image-layouts/22-asymmetric-split.svg`
- **特点**：不等分，主次分明
- **适用场景**：重点突出、主次分明

#### 23. Floating Cards（浮动卡片）
- **用途**：现代感展示
- **SVG**：`image-layouts/23-floating-cards.svg`
- **特点**：图片以卡片形式浮动
- **适用场景**：产品展示、功能介绍

#### 24. Grid 2x2（2x2 网格）
- **用途**：多图展示
- **SVG**：`image-layouts/24-grid-2x2.svg`
- **特点**：四宫格布局
- **适用场景**：产品系列、案例展示

#### 25. Mosaic（马赛克）
- **用途**：创意拼贴
- **SVG**：`image-layouts/25-mosaic.svg`
- **特点**：不规则拼贴
- **适用场景**：作品集、创意展示

#### 26. Carousel Preview（轮播预览）
- **用途**：序列展示
- **SVG**：`image-layouts/26-carousel.svg`
- **特点**：突出主图，两侧露出相邻图
- **适用场景**：产品系列、流程展示

#### 27. Stacked Layers（层叠）
- **用途**：深度感
- **SVG**：`image-layouts/27-stacked-layers.svg`
- **特点**：多层叠加，有阴影
- **适用场景**：产品展示、功能层级

#### 28. Mirror Reflection（镜像反射）
- **用途**：高端展示
- **SVG**：`image-layouts/28-mirror.svg`
- **特点**：图片有倒影效果
- **适用场景**：产品展示、品牌展示

#### 29. Film Strip（胶片条）
- **用途**：序列展示
- **SVG**：`image-layouts/29-film-strip.svg`
- **特点**：横向排列，像电影胶片
- **适用场景**：时间线、流程展示

#### 30. Polaroid Stack（拍立得堆叠）
- **用途**：创意展示
- **SVG**：`image-layouts/30-polaroid.svg`
- **特点**：拍立得照片风格，随意堆叠
- **适用场景**：团队展示、活动回顾

---

### 三、多图布局（31-45）

#### 31. Gallery（画廊）
- **用途**：作品展示
- **SVG**：`image-layouts/31-gallery.svg`
- **特点**：整齐排列，等间距
- **适用场景**：作品集、产品系列

#### 32. Masonry（瀑布流）
- **用途**：不等高图片展示
- **SVG**：`image-layouts/32-masonry.svg`
- **特点**：Pinterest 风格瀑布流
- **适用场景**：创意作品、案例展示

#### 33. Timeline Visual（时间线视觉）
- **用途**：时间序列
- **SVG**：`image-layouts/33-timeline-visual.svg`
- **特点**：图片沿时间线排列
- **适用场景**：发展历程、项目进度

#### 34. Hub and Spoke（中心辐射）
- **用途**：核心与分支
- **SVG**：`image-layouts/34-hub-spoke.svg`
- **特点**：中心图 + 周围小图
- **适用场景**：产品生态、功能架构

#### 35. Pyramid（金字塔）
- **用途**：层级展示
- **SVG**：`image-layouts/35-pyramid.svg`
- **特点**：金字塔结构排列
- **适用场景**：层级关系、优先级

#### 36. Circular Flow（环形流程）
- **用途**：循环流程
- **SVG**：`image-layouts/36-circular-flow.svg`
- **特点**：图片围成圆形
- **适用场景**：循环流程、闭环系统

#### 37. Stepped（阶梯式）
- **用途**：递进展示
- **SVG**：`image-layouts/37-stepped.svg`
- **特点**：阶梯式排列
- **适用场景**：步骤说明、递进关系

#### 38. Cluster（聚类）
- **用途**：自由组合
- **SVG**：`image-layouts/38-cluster.svg`
- **特点**：不规则聚类
- **适用场景**：创意展示、头脑风暴

#### 39. Wave（波浪形）
- **用途**：动态展示
- **SVG**：`image-layouts/39-wave.svg`
- **特点**：波浪形排列
- **适用场景**：趋势展示、动态变化

#### 40. Diamond Grid（菱形网格）
- **用途**：创意网格
- **SVG**：`image-layouts/40-diamond-grid.svg`
- **特点**：45度旋转的网格
- **适用场景**：创意展示、设计作品

#### 41. Hexagon Grid（六边形网格）
- **用途**：蜂巢布局
- **SVG**：`image-layouts/41-hexagon-grid.svg`
- **特点**：六边形排列
- **适用场景**：产品生态、模块化展示

#### 42. Tree Structure（树形结构）
- **用途**：层级关系
- **SVG**：`image-layouts/42-tree-structure.svg`
- **特点**：树形分支
- **适用场景**：组织架构、分类展示

#### 43. Network Graph（网络图）
- **用途**：关联关系
- **SVG**：`image-layouts/43-network-graph.svg`
- **特点**：节点连线
- **适用场景**：关系网络、生态系统

#### 44. Isometric Grid（等距网格）
- **用途**：3D 感展示
- **SVG**：`image-layouts/44-isometric-grid.svg`
- **特点**：等距视角的网格
- **适用场景**：技术架构、系统设计

#### 45. Staggered Grid（交错网格）
- **用途**：现代感展示
- **SVG**：`image-layouts/45-staggered-grid.svg`
- **特点**：错落有致的网格
- **适用场景**：产品展示、案例展示

---

## Modifier Layers（修饰层）— 27 种

### 四、裁剪形状（46-55）

#### 46. Circle Crop（圆形裁剪）
- **SVG**：`image-layouts/46-circle-crop.svg`
- **效果**：图片裁剪为圆形

#### 47. Hexagon Crop（六边形裁剪）
- **SVG**：`image-layouts/47-hexagon-crop.svg`
- **效果**：图片裁剪为六边形

#### 48. Blob Crop（不规则裁剪）
- **SVG**：`image-layouts/48-blob-crop.svg`
- **效果**：图片裁剪为不规则形状

#### 49. Arch Crop（拱形裁剪）
- **SVG**：`image-layouts/49-arch-crop.svg`
- **效果**：图片裁剪为拱形

#### 50. Diamond Crop（菱形裁剪）
- **SVG**：`image-layouts/50-diamond-crop.svg`
- **效果**：图片裁剪为菱形

#### 51. Triangle Crop（三角形裁剪）
- **SVG**：`image-layouts/51-triangle-crop.svg`
- **效果**：图片裁剪为三角形

#### 52. Star Crop（星形裁剪）
- **SVG**：`image-layouts/52-star-crop.svg`
- **效果**：图片裁剪为星形

#### 53. Rounded Square（圆角方形）
- **SVG**：`image-layouts/53-rounded-square.svg`
- **效果**：大圆角方形

#### 54. Squircle（超椭圆）
- **SVG**：`image-layouts/54-squircle.svg`
- **效果**：iOS 风格的超椭圆

#### 55. Custom Path（自定义路径）
- **SVG**：`image-layouts/55-custom-path.svg`
- **效果**：任意 SVG 路径裁剪

---

### 五、叠加效果（56-65）

#### 56. Color Overlay（纯色叠加）
- **SVG**：`image-layouts/56-color-overlay.svg`
- **效果**：半透明纯色叠加

#### 57. Gradient Overlay（渐变叠加）
- **SVG**：`image-layouts/57-gradient-overlay.svg`
- **效果**：渐变遮罩

#### 58. Pattern Overlay（图案叠加）
- **SVG**：`image-layouts/58-pattern-overlay.svg`
- **效果**：重复图案叠加

#### 59. Noise Texture（噪点纹理）
- **SVG**：`image-layouts/59-noise-texture.svg`
- **效果**：增加噪点质感

#### 60. Vignette（暗角效果）
- **SVG**：`image-layouts/60-vignette.svg`
- **效果**：边缘变暗

#### 61. Blur Background（模糊背景）
- **SVG**：`image-layouts/61-blur-bg.svg`
- **效果**：背景模糊

#### 62. Shadow Frame（阴影边框）
- **SVG**：`image-layouts/62-shadow-frame.svg`
- **效果**：增加阴影深度

#### 63. Border Accent（边框强调）
- **SVG**：`image-layouts/63-border-accent.svg`
- **效果**：彩色边框

#### 64. Corner Badge（角落徽章）
- **SVG**：`image-layouts/64-corner-badge.svg`
- **效果**：角落添加标签

#### 65. Watermark（水印）
- **SVG**：`image-layouts/65-watermark.svg`
- **效果**：半透明水印

---

### 六、特殊技法（66-72）

#### 66. Duotone（双色调）
- **SVG**：`image-layouts/66-duotone.svg`
- **效果**：图片转为双色调

#### 67. Glitch Effect（故障效果）
- **SVG**：`image-layouts/67-glitch.svg`
- **效果**：RGB 偏移故障风

#### 68. Pixelate（像素化）
- **SVG**：`image-layouts/68-pixelate.svg`
- **效果**：局部像素化

#### 69. Halftone（半调网点）
- **SVG**：`image-layouts/69-halftone.svg`
- **效果**：印刷半调效果

#### 70. Split Tone（分离色调）
- **SVG**：`image-layouts/70-split-tone.svg`
- **效果**：高光和阴影不同色调

#### 71. Parallax Cutout（视差剪纸）
- **SVG**：`image-layouts/71-parallax-cutout.svg`
- **效果**：主体抠出，背景虚化

#### 72. Textured Overlay（纹理叠加）
- **SVG**：`image-layouts/72-textured-overlay.svg`
- **效果**：纸张/布料纹理叠加

---

## 使用规则

### 选择优先级

1. **封面和章节页**：必须使用图文布局（01-15 单图布局）
2. **内容页**：根据图片数量选择
   - 0 张图：使用纯文字布局（bullets、two-column 等）
   - 1 张图：从 01-15 选择
   - 2 张图：从 16-30 选择
   - 3+ 张图：从 31-45 选择
3. **修饰层**：可叠加使用，增强视觉效果

### 组合规则

- **主体结构**选择 1 个
- **修饰层**可叠加 0-2 个
- **禁止**连续 2 页使用相同布局
- **禁止**在数据密集页使用全出血布局

### 示例组合

```
封面 = 01-full-bleed + 57-gradient-overlay
章节页 = 04-hero-overlay
内容页 = 02-split-horizontal
数据页 = 10-corner-accent（小图点缀）
结尾页 = 04-hero-overlay + 60-vignette
```
