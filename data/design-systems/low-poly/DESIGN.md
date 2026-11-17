# 019 · 低多边形 Low Poly（low-poly）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（1993 星际火狐 → 2010 年代独立游戏与插画 → 今天的图标、空状态与 3D 插画）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `paper` | `#fbf4e6` | paper | 0.5 |
| `bg` | `#f6eedd` | bg | 0.469 |
| `red` | `#ee6b57` | red | 0.438 |
| `yellow` | `#f4c54f` | yellow | 0.408 |
| `green` | `#4daf72` | green | 0.377 |
| `lgreen` | `#9ed7a8` | lgreen | 0.346 |
| `sky` | `#8cc8ee` | sky | 0.315 |
| `sea` | `#7db8e8` | sea | 0.285 |
| `pink` | `#f49db6` | pink | 0.254 |
| `lilac` | `#c9a6ec` | lilac | 0.223 |
| `peri` | `#8f9dea` | peri | 0.192 |
| `blue` | `#2f5fd8` | blue | 0.162 |
| `ink` | `#3b3552` | ink | 0.131 |
| `shade` | `#7a5c86` | shade | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 10.56:1 | AAA |
| --fg on --surface | 9.56:1 | AAA |
| --fg-2 on --bg | 3.9:1 | AA-Large |
| --accent on --bg | 5.12:1 | AA |
| --bg on --accent | 5.12:1 | AA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
