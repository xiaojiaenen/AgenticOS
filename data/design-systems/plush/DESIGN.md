# 毛绒 Plush（plush）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `background` | `#fff1e0` | background | 0.5 |
| `root` | `#7d0a3c` | root | 0.367 |
| `tip` | `#ff4f97` | tip | 0.233 |
| `accent` | `#7b52ff` | accent | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 9.55:1 | AAA |
| --fg on --surface | 8.54:1 | AAA |
| --fg-2 on --bg | 4.24:1 | AA-Large |
| --accent on --bg | 4.21:1 | AA-Large |
| --bg on --accent | 4.21:1 | AA-Large |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
