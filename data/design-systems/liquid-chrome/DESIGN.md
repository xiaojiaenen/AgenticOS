# 液态金属 Liquid Chrome（liquid-chrome）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `background` | `#090e18` | background | 0.5 |
| `ink` | `#f5f5f2` | ink | 0.3 |
| `accent` | `#ed80b8` | accent | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 17.68:1 | AAA |
| --fg on --surface | 15.64:1 | AAA |
| --fg-2 on --bg | 7.72:1 | AAA |
| --accent on --bg | 7.71:1 | AAA |
| --bg on --accent | 7.71:1 | AAA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
