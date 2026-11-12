# 013-art-deco（art-deco）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（1925—1939）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
| `onyx` | `#0e0d0b` | 黑曜：底 | 0.6 |
| `onyx2` | `#1a1711` | 体块的亮面 | 0.45 |
| `gold` | `#c9a45a` | 鎏金：线、大字、唯一的按钮 | 0.1 |
| `goldlt` | `#f2dc9c` | 金的高光 | 0.35 |
| `golddk` | `#7e5e26` | 金的暗部 | 0.3 |
| `ivory` | `#f1e7d2` | 象牙：正文、纸 | 0.25 |
| `emerald` | `#0e4a3c` | 孔雀绿：第二底色（上海的绿铜屋顶） | 0.2 |
| `lacquer` | `#9e2b25` | 漆红：点缀、错误 | 0.05 |
| `smoke` | `#a89f8c` | 烟灰：次要文字 | 0.1 |

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
| --fg on --bg | 15.82:1 | AAA |
| --fg on --surface | 14.14:1 | AAA |
| --fg-2 on --bg | 7.03:1 | AAA |
| --accent on --bg | 8.27:1 | AAA |
| --bg on --accent | 8.27:1 | AAA |

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
