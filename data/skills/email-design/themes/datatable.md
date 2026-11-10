# Theme · datatable（数字优先 / 扫描友好）

## 气质
为"看数字"而生的邮件：键值表、对比列、涨跌标记，右对齐数字列，一眼扫完。克制、
不装饰、数据打头。像财务/运营的周报正文。

## 适合 / 不适合
- **适合**：报表结论、KPI 汇总、费用明细、对比数据、任何"信里有数字要说"的场景。
- **不适合**：抒情、叙事、正式公函（用 press/swiss）。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#1a1d21` | 标题、数值 |
| sub | `#5c636b` | 行标签 |
| faint | `#6b737b` | meta、单位 |
| rule | `#e3e6ea` | 行分隔 |
| up | `#1a7a43` | 上升（仅状态，真有涨跌才用） |
| down | `#c0392b` | 下降 |
| bg | `#ffffff` | 底 |

## 排版
- 标题 `20px / 600`。
- 数字用等宽或 `font-variant-numeric: tabular-nums`（对齐），`15–16px / 600`。
- 行标签 `14px` 灰。

## 版式
标题 + 一行副标（周期/口径）→ 一张键值/对比表（右对齐数字 + 涨跌彩标）→ 一句结论。
记忆点是**右对齐的数字列 + 涨跌彩标**。

```
9 月数据小结
统计 9/1–9/30，环比上月

活跃用户         24,180   ↑8.2% (green)
付费转化率         3.6%    ↓0.3pp (red)
ARPU             ¥58.4
────────────────────
一句话结论……
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#f6f7f8;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f6f7f8;">
<tr><td align="center" style="padding:40px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#ffffff;border:1px solid #e3e6ea;">
    <tr><td style="padding:26px 30px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:20px;font-weight:600;color:#1a1d21;">9 月运营数据小结</div>
      <div style="margin-top:6px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:13px;color:#6b737b;">统计 9/1 – 9/30，环比上月</div>
    </td></tr>
    <tr><td style="padding:20px 30px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #e3e6ea;">
        <tr>
          <td style="padding:13px 0;border-bottom:1px solid #e3e6ea;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:14px;color:#5c636b;">活跃用户</td>
          <td align="right" style="padding:13px 0;border-bottom:1px solid #e3e6ea;font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:15px;font-weight:600;color:#1a1d21;">24,180 <span style="color:#1a7a43;font-size:13px;">↑ 8.2%</span></td>
        </tr>
        <tr>
          <td style="padding:13px 0;border-bottom:1px solid #e3e6ea;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:14px;color:#5c636b;">付费转化率</td>
          <td align="right" style="padding:13px 0;border-bottom:1px solid #e3e6ea;font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:15px;font-weight:600;color:#1a1d21;">3.6% <span style="color:#c0392b;font-size:13px;">↓ 0.3pp</span></td>
        </tr>
        <tr>
          <td style="padding:13px 0;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:14px;color:#5c636b;">ARPU</td>
          <td align="right" style="padding:13px 0;font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:15px;font-weight:600;color:#1a1d21;">¥58.4</td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="padding:20px 30px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;line-height:1.8;color:#5c636b;">转化下滑主要来自新渠道用户质量下降，下月会收紧投放定向。</div>
    </td></tr>
    <tr><td style="padding:22px 30px 24px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:13px;color:#6b737b;">李四</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 涨跌彩标乱用（只有真有变化才上色，且只红/绿两色）
- 左对齐数字（数字要右对齐才好比）
- 给每个数字加装饰性大图标
- 编造数据（没数据就留占位或删表）
