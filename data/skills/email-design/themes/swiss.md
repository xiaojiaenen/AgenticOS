# Theme · swiss（瑞士国际主义 · 冷中性网格）

## 气质
冷中性、严格网格、系统化。像一份排过版的现代文档：不打扮、不抢戏，但每个间距、
每条对齐都精确。给人「专业、可靠、不啰嗦」的印象。**最安全的通用选择。**

## 适合 / 不适合
- **适合**：周报、汇报、正式通知、跨部门沟通、流程说明、任何"拿不准时"的邮件。
- **不适合**：需要温度的私人感谢；需要高饱和品牌感的营销邮件。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#111315` | 标题、正文主色 |
| sub | `#5b636b` | 次要文字 |
| faint | `#6b737b` | 署名、meta |
| rule | `#e3e6e9` | 分割线 |
| bg | `#ffffff` | 底色 |
| page | `#f4f5f6` | 页面底（邮件外层） |
| accent | `#2f6f4f` | 唯一强调：链接、一个按钮 |

## 排版
- 标题 `26px / 600`，正文 `15px / 400 / lh 1.8`，辅助 `13px`，脚注 `12px`。
- 字体栈：`'Helvetica Neue', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif`
- 标题紧字距 `letter-spacing:-0.01em`。

## 版式
左对齐、单栏、一条顶部实心细线收口。大标题之后紧跟一句引导句，正文用短段。
记忆点是**标题的字号对比**，没有花哨色块。

```
════════ 2px ink 顶线 ════════
AgenticOS                     2026·11·05
────────────────────────────────────
你要说的事（26px 标题）

一句引导。
正文段落……
正文段落……

李四
────────────────────────────────────
AGENTICOS
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#f4f5f6;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f5f6;">
<tr><td align="center" style="padding:40px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#ffffff;">
    <!-- 顶线 + 页眉 -->
    <tr><td style="height:2px;background:#111315;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:22px 32px 14px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;font-weight:700;color:#111315;letter-spacing:-0.01em;">AgenticOS</td>
        <td align="right" style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;color:#6b737b;">2026·11·05</td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:0 32px;"><div style="height:1px;background:#e3e6e9;font-size:0;line-height:0;">&nbsp;</div></td></tr>

    <!-- 标题 + 正文 -->
    <tr><td style="padding:30px 32px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:26px;font-weight:600;line-height:1.3;color:#111315;letter-spacing:-0.01em;">三季度复盘结论</div>
      <div style="margin-top:14px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:15px;line-height:1.8;color:#5b636b;">王总，你好。三季度的增长主要来自老客户复购，新客获取成本还在上升，下面是三个要点。</div>
    </td></tr>
    <tr><td style="padding:16px 32px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:15px;line-height:1.8;color:#5b636b;">复购率环比升到 41%，是近四个季度最高。新客 CAC 环比涨了 18%，主要是渠道投放变贵。下季度会把预算往老客运营挪一部分。</div>
    </td></tr>

    <!-- 一个按钮（可选） -->
    <tr><td style="padding:24px 32px 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background:#2f6f4f;border-radius:6px;">
          <a href="https://example.com/report" style="display:inline-block;padding:11px 26px;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;">查看完整报告</a>
        </td>
      </tr></table>
    </td></tr>

    <!-- 署名 -->
    <tr><td style="padding:24px 32px 30px;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:14px;color:#5b636b;">李四</div>
    </td></tr>

    <!-- 页脚 -->
    <tr><td style="padding:0 32px;"><div style="height:1px;background:#e3e6e9;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:14px 32px 22px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;color:#6b737b;">AGENTICOS</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 用多个颜色强调（swiss 只有一个 accent 绿）
- 大圆角、投影、渐变
- 每个标题上挂全大写小标签
