# 017 · 中世纪现代 Mid-Century Modern（mid-century-modern）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `paper` | `#fbf3e3` | paper | 0.5 |
| `red` | `#f2542d` | red | 0.45 |
| `sun` | `#ffc62e` | sun | 0.4 |
| `pink` | `#f57aa8` | pink | 0.35 |
| `turq` | `#1fb3a6` | turq | 0.3 |
| `blue` | `#2f6bd8` | blue | 0.25 |
| `ink` | `#1e1b19` | ink | 0.2 |
| `mute` | `#8a7f72` | mute | 0.15 |
| `shadow` | `#3a1c0c` | shadow | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 15.52:1 | AAA |
| --fg on --surface | 13.81:1 | AAA |
| --fg-2 on --bg | 5.1:1 | AA |
| --accent on --bg | 3.13:1 | AA-Large |
| --bg on --accent | 3.13:1 | AA-Large |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
