# 新艺术运动 Art Nouveau（art-nouveau）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `background` | `#efe6cf` | background | 0.5 |
| `olive` | `#4e5a34` | olive | 0.45 |
| `sage` | `#7f8f5e` | sage | 0.4 |
| `gold` | `#c49a4a` | gold | 0.35 |
| `plum` | `#6b3a4a` | plum | 0.3 |
| `rose` | `#d9a39a` | rose | 0.25 |
| `guimard` | `#2f5d4a` | guimard | 0.2 |
| `bronze` | `#6e4e26` | bronze | 0.15 |
| `ink` | `#2e2a1f` | ink | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 11.51:1 | AAA |
| --fg on --surface | 10.36:1 | AAA |
| --fg-2 on --bg | 4.2:1 | AA-Large |
| --accent on --bg | 5.96:1 | AA |
| --bg on --accent | 5.96:1 | AA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
