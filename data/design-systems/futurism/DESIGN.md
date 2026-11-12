# 015-futurism（futurism）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（1909—1944）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `paper` | `#ede5d3` | paper | 0.5 |
| `ink` | `#16130f` | ink | 0.25 |
| `orange` | `#f2501c` | orange | 0.12 |
| `cobalt` | `#1f3fd0` | cobalt | 0.08 |
| `silver` | `#b9bdc3` | silver | 0.05 |
| `mute` | `#776f62` | mute | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 14.77:1 | AAA |
| --fg on --surface | 13.06:1 | AAA |
| --fg-2 on --bg | 5.23:1 | AA |
| --accent on --bg | 6.25:1 | AA |
| --bg on --accent | 6.25:1 | AA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
