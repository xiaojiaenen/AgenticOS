"""
Compiled design craft rules from open-design craft/ for injection into PPT prompts.

Adapted from ~/code/open-design/craft/{anti-ai-slop,typography,color}.md
Contextualized for SVG-native slide generation.
"""


def build_craft_rules_text() -> str:
    """Return condensed SVG-specific craft rules (~70 lines)."""
    return """## 设计工艺铁律（Design Craft Rules）

以下规则区分「人类设计」与「AI 默认输出」。每条规则都是具体的、可检查的。

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
- **严禁正文两端对齐**（text-anchor 只用 start/middle，禁止 justify 等效处理）

### 颜色纪律

- **每页 accent 色可见使用不超过 2 处**：典型组合 = 一个装饰元素 + 一个数据高亮，或一个标签 + 一个 CTA
- **链接/箭头/图标也算 accent 使用次数**，合理分配
- **前景背景对比度**：正文文字 ≥ 4.5:1，大号文字（≥18px 或 14px bold）≥ 3:1
- **暗色背景**：背景不用纯黑 `#000`，用 `var(--bg)`；文字不用纯白，用 `var(--text-1)`
- **中性色占画面 70–90%**（var(--bg)、var(--surface)、var(--text-2)），accent 占 5–10%

### 节奏与呼吸

- 连续两页不要视觉密度相同——紧接松、满版接留白、数据页后接 big-quote 或 section-divider
- 装饰元素（纯视觉 rect/circle，不承载信息）每页不超过 2 个
- ~80% 验证过的模式 + ~20% 有意的差异化选择 = 有「灵魂」的设计"""
