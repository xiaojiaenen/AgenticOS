# 018 · 微缩景观 Diorama（diorama）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（1950s 模型铁路 → 2001 Miniatur Wunderland → 2014 等距游戏 → 今天）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `paper` | `#f6eedd` | paper | 0.5 |
| `cream` | `#fff7ec` | cream | 0.464 |
| `soil` | `#c99a72` | soil | 0.427 |
| `mint` | `#7fcba8` | mint | 0.391 |
| `pink` | `#f28aa6` | pink | 0.355 |
| `peach` | `#f7c9d3` | peach | 0.318 |
| `lilac` | `#cdb9f0` | lilac | 0.282 |
| `sky` | `#7db8e8` | sky | 0.245 |
| `butter` | `#f5c451` | butter | 0.209 |
| `coral` | `#f27d6a` | coral | 0.173 |
| `ink` | `#3b3552` | ink | 0.136 |
| `shade` | `#7a5c86` | shade | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 10.01:1 | AAA |
| --fg on --surface | 9.07:1 | AAA |
| --fg-2 on --bg | 3.81:1 | AA-Large |
| --accent on --bg | 4.91:1 | AA |
| --bg on --accent | 4.91:1 | AA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
