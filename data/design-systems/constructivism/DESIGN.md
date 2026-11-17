# 003-constructivism（constructivism）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（1917—1932）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `paper` | `#ece4d2` | 旧纸 | 0.5 |
| `ink` | `#161412` | 印刷黑 | 0.3 |
| `red` | `#d3261c` | 构成红 | 0.15 |
| `grey` | `#8f897d` | 网点灰 | 0.05 |
| `light` | `#f6f1e6` | 亮纸（只给白圆） | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 14.52:1 | AAA |
| --fg on --surface | 12.93:1 | AAA |
| --fg-2 on --bg | 5.18:1 | AA |
| --accent on --bg | 4.08:1 | AA-Large |
| --bg on --accent | 4.08:1 | AA-Large |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
