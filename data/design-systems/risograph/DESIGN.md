# 008-risograph（risograph）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（1946—今天）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `paper` | `#f3ecdb` | 米白道林纸 | 0.55 |
| `pink` | `#ff48b0` | 荧光粉 Fluorescent Pink | 0.16 |
| `teal` | `#00838a` | 青绿 Teal | 0.14 |
| `yellow` | `#ffb511` | 芥末黄 Sunflower | 0.12 |
| `black` | `#000000` | 黑 Black | 0.03 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 17.83:1 | AAA |
| --fg on --surface | 15.64:1 | AAA |
| --fg-2 on --bg | 6.53:1 | AA |
| --accent on --bg | 3.87:1 | AA-Large |
| --bg on --accent | 3.87:1 | AA-Large |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
