# PPT 质量测试提示词

覆盖 6 轮修复的全部问题域：字体 token 化、反 AI-Slop、主题对比度、暗色主题、排版层级、accent 克制、瑞士风格。

---

## 测试 1：字体 Token 化 + 反 Indigo

```
做一个关于 "开源技术社区" 的 6 页 PPT，用 github 主题

检查点：
- SVG 中不能出现硬编码的 "Inter"、"JetBrains Mono"、"Playfair Display"，必须用 var(--font-sans) 等
- 不能出现 #6366f1、#4f46e5、#8b5cf6
- 封面标题用展示字体，正文用 sans
```

## 测试 2：反 Accent 左竖条 + 反 Emoji 图标

```
做一份 8 页的产品发布 PPT，主题 apple，风格 modern_minimal

检查点：
- section-divider 页不能有左侧 accent 竖条（rect x="0" width="8" fill="var(--accent)"）
- 不能出现 ✨🚀🎯 等 emoji 作为装饰或图标
- accent 每页可见使用不超过 2 处
```

## 测试 3：暗色主题 — 边框 rgba + 文本层级

```
做一份 8 页的技术架构分享，主题 dracula

检查点：
- --border 和 --border-strong 必须是 rgba(255,255,255,...) 格式
- --text-1 是页面最亮的文字色（标题），--text-2 次之（正文），--text-3 最暗（辅助文字）
- 背景不是纯黑 #000，文字不是纯白 #fff
- 所有暗色主题都适用这条
```

## 测试 4：Accent 对比度

```
做一份 6 页的创意提案 PPT，主题 zhangzara-creative-mode

检查点：
- accent 颜色在背景上可见，不会淹没在背景色中
- 如果 accent 是浅色背景上的浅色，应该被自动替换为高对比度颜色
```

## 测试 5：图表 Accent 克制

```
做一份 8 页的数据汇报 PPT，包含柱状图页和饼图页，主题 stripe

检查点：
- 柱状图只有最后一根（或最重要的那根）柱子用 var(--accent)，其余用 var(--surface-2)
- 饼图同理，只有突出的一块用 accent
- 图表的文字标签用 var(--text-1) / var(--text-2)，不用 accent
```

## 测试 6：排版层级（3 层模型）

```
做一份 8 页的品牌故事 PPT，主题 zhangzara-sakura-chroma

每页检查：
- 有且仅有一个视觉主导元素（不是两个、不是三个）
- 至少用 2 种层级向量（Scale/Weight/Spacing/Tracking/Alignment），不能只用字号
- 相邻层级在某个维度上有 ≥1.25x 的跳跃
- 不超过 3 种字号
```

## 测试 7：瑞士国际主义风格

```
用 swiss_international 风格做一份 8 页的商业报告 PPT，主题 klein-blue

严格检查：
- 所有 rect 的 rx/ry=0，严禁任何圆角
- 边框 1px hairline：stroke-width="1"
- 没有渐变（gradient）、没有阴影（filter="url(#shadow)"）
- 封面标题 48-72px，正文 14-16px
- 整份 deck 只用 1 个 accent 颜色，其余黑白灰
- 不允许 serif 字体
```

## 测试 8：节奏与呼吸

```
做一份 10 页的年终总结 PPT，主题 zhangzara-soft-editorial

检查点：
- 连续两页视觉密度不同（紧接松、满版接留白、数据页后接 section-divider）
- 装饰元素（纯视觉 rect/circle）每页不超过 2 个
- 正文与卡片边缘留白 ≥ 24px
- 正文行宽 45-75 字符
```

## 测试 9：混合暗色主题（zhangzara mixed scheme）

```
做一份 6 页的设计作品集 PPT，主题 zhangzara-cobalt-grid

检查点：
- 即使 scheme 是 "mixed"，暗色背景部分的 text-1 必须是亮色，不会出现深色文字在深色背景上
- 边框正确处理为半透明 rgba
- surface 色板在 bg 之上清晰可辨
```

## 测试 10：端到端全风格覆盖

```
依次生成以下 5 份 PPT，每份 8 页，主题自选：

1. "2025 年 AI 行业趋势报告" — editorial 风格
2. "SaaS 产品 3.0 版本发布" — modern_minimal 风格
3. "品牌年度盛典方案" — bold_statement 风格
4. "开源项目技术架构" — tech_dark 风格
5. "团队文化与价值观" — warm_human 风格

全部输出后统一检查：
- 没有硬编码字体、没有 Indigo 色值、没有 emoji 图标
- 暗色主题有 rgba 边框
- 没有左侧 accent 竖条圆角卡片
- 图表 accent 克制
- 每页排版层级清晰
```

---

## 快速验证命令

```bash
# 检查硬编码字体（应该为 0）
grep -rl 'font-family.*Inter' data/ppt-sessions/*/slide_*.svg | wc -l
grep -rl 'font-family.*JetBrains' data/ppt-sessions/*/slide_*.svg | wc -l

# 检查 Indigo（应该为 0，排除 theme CSS 本身）
grep -rn '#6366f1\|#4f46e5\|#8b5cf6' data/ppt-sessions/*/slide_*.svg | wc -l

# 检查 emoji（应该为 0）
grep -rn '✨\|🚀\|🎯\|💡\|🔥\|📊' data/ppt-sessions/*/slide_*.svg | wc -l

# 检查左侧 accent 竖条（应该为 0）
grep -rn 'x="0".*width="8".*accent' data/ppt-sessions/*/slide_*.svg | wc -l

# 检查暗色主题的纯黑边框（应该为 0）
grep -rn 'border.*#000\|border.*#111\|border.*#1a1a' data/ppt-sessions/*/slide_*.svg | wc -l

# 统计当前主题数量
ls data/design-themes/*.css | wc -l
```

## 关注的主题（容易出现问题的）

| 主题 | 风险 | 验证点 |
|------|------|--------|
| dracula, tokyo-night, nord | 暗色 | rgba 边框、text 层级 |
| zhangzara-creative-mode | accent 对比度 | accent 在 cream 背景可见 |
| zhangzara-biennale-yellow | accent 对比度 | accent 在暖色背景可见 |
| zhangzara-cobalt-grid | mixed scheme | 明暗区域文字可读 |
| klein-blue, swiss-grid | 瑞士风格 | 0 圆角、无渐变无阴影 |
| github, monokai | 代码/终端风 | mono 字体 token 化 |
