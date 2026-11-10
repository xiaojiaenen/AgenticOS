# Theme · tufte（数据墨水比 / 极简发丝线）

> 改造自 garden-skills「Tufte · Data-Ink」。原版为长文排版设计，这里收成邮件语境：
> 保留「每滴墨水都承载信息、以线代框、大页边、排版承载含义」的内核，缩到一封邮件。
> 去掉原版依赖的边注（sidenote）——邮件没法做浮动边注。

## 气质
Edward Tufte 的数据墨水比。不画卡片、不填色、不加阴影圆角装饰。留下的只有文字、
发丝级参考线、充裕的页边。让读者凑近去读、去比较。一句"高级的克制"。
**给爱看数字、讨厌花架子的人**。

## 适合 / 不适合
- **适合**：分析结论、数据型汇报、需要让人认真读的说明、内部研究/复盘。
- **不适合**：需要亲切温度的沟通；需要大标题海报感的场合。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#111111` | 文字（真黑，对比够） |
| sub | `#555555` | 次要正文 |
| faint | `#6b6b6b` | meta（保证 ≥4.5:1） |
| rule | `#cccccc` | 发丝参考线（只用一种线，细 1px） |
| bg | `#fffefb` | 极浅暖白纸 |
| accent | `#8c2f2f` | 极罕见的暗红，只标一处「注意」 |

## 排版
- 全篇一个衬线/一个 sans 建立层级，**靠字号和页边，不靠颜色**。
- 标题 `24px / 600`，正文 `15px / 400 / lh 1.75`，页边内边距 **大**（40–48px）。
- 数字用等宽对齐。

## 版式
极简：一行页眉 → 标题 → 正文（大页边）→ 一条发丝线 → 一行数据/结论。
记忆点是**大页边 + 一条贯穿的发丝参考线**，别无他物。

```
（大页边）
AgenticOS                  2026·11·05
──────────────────────────── (发丝线，1px 浅灰)
标题

正文，页边很大……

  一个缩进的数字对比（表格但无框线，仅发丝线）
  活跃用户        24,180
  转化率           3.6%

李四
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#fffefb;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fffefb;">
<tr><td align="center" style="padding:56px 20px;">
  <table width="560" cellpadding="0" cellspacing="0" border="0" style="width:560px;max-width:560px;background:#fffefb;">
    <!-- 页眉 + 发丝线 -->
    <tr><td style="padding:0 48px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;color:#111111;">AgenticOS</td>
        <td align="right" style="font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:12px;color:#6b6b6b;">2026·11·05</td>
      </tr></table>
      <div style="height:1px;background:#cccccc;margin-top:10px;font-size:0;line-height:0;">&nbsp;</div>
    </td></tr>
    <!-- 标题 -->
    <tr><td style="padding:30px 48px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC','SimSun',serif;font-size:24px;font-weight:600;line-height:1.4;color:#111111;">复购是这季度唯一变好的指标</div>
    </td></tr>
    <!-- 正文（大页边） -->
    <tr><td style="padding:18px 48px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.8;color:#111111;">王总，这季度有三件事值得记一笔。复购率升到 41%，是近四个季度最高；与此同时新客获取成本涨了 18%，两条线第一次交叉。</div>
      <div style="margin-top:14px;font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.8;color:#111111;">换句话说，现在每一分增长都更依赖老客户。这不是坏消息，但它要求我们换一种花钱的方式。</div>
    </td></tr>
    <!-- 无框数据（仅发丝线） -->
    <tr><td style="padding:22px 48px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="padding:8px 0;border-bottom:1px solid #cccccc;font-family:Georgia,'Times New Roman',serif;font-size:14px;color:#555555;">复购率</td>
          <td align="right" style="padding:8px 0;border-bottom:1px solid #cccccc;font-family:'SFMono-Regular',Menlo,monospace;font-size:14px;color:#111111;">41%</td>
        </tr>
        <tr>
          <td style="padding:8px 0;font-family:Georgia,'Times New Roman',serif;font-size:14px;color:#555555;">新客获取成本</td>
          <td align="right" style="padding:8px 0;font-family:'SFMono-Regular',Menlo,monospace;font-size:14px;color:#111111;">+18%</td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="padding:26px 48px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.8;color:#111111;">建议把下季度的投放预算，往老客运营挪三成。</div>
    </td></tr>
    <tr><td style="padding:28px 48px 0;"><div style="height:1px;background:#cccccc;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:14px 48px 0;font-family:Georgia,'Times New Roman',serif;font-size:13px;color:#555555;">李四</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 卡片、背景填色块、阴影、圆角（tufte 的力量就是"没有这些"）
- 用多个颜色强调（只有一处暗红标注意）
- 页边收窄（大页边是这个主题的骨架）
- 给每个数据配图标
