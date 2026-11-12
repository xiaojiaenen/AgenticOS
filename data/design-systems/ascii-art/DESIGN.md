# 020 · 字符画 ASCII Art（ascii-art）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `background` | `#06060a` | background | 0.5 |
| `ink` | `#fff6da` | ink | 0.42 |
| `orange` | `#ff6a1a` | orange | 0.34 |
| `pink` | `#ff2d8a` | pink | 0.26 |
| `blue` | `#2346e0` | blue | 0.18 |
| `gold` | `#ffc530` | gold | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 18.73:1 | AAA |
| --fg on --surface | 17.01:1 | AAA |
| --fg-2 on --bg | 7.94:1 | AAA |
| --accent on --bg | 12.79:1 | AAA |
| --bg on --accent | 12.79:1 | AAA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
