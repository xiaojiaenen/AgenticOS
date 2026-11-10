# Theme · warm（暖白 + 明黄 / 机灵有人味）

## 气质
暖白纸面、近黑墨、明黄只作**荧光笔/色块**（绝不作文字色）。俏皮的圆润标题压在干净的
正文之上。机灵、亲切、有人味，但不失专业。像 Mailchimp 那种"专业但不端着"的感觉。

## 适合 / 不适合
- **适合**：产品更新、团队公告、友好通知、面向普通用户的内容、changelog 叙事。
- **不适合**：严肃正式的对外公函（用 swiss/press）；密集数据（用 datatable）。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#2a2420` | 标题、正文（暖黑） |
| sub | `#6b625a` | 次要 |
| faint | `#9c928a` | meta |
| yellow | `#f4d63a` | 明黄 —— **只作高亮块/贴纸/按钮底，不作文字色** |
| paper | `#fffdf7` | 暖白底 |
| rule | `#ece5d8` | 细线 |

## 排版
- 标题 `24px / 700`，圆润但不必真的圆体，可用略带个性的 sans。
- 正文 `15px / 400 / lh 1.8`。
- 关键词用「黑字 + 黄底 highlight」，不用黄字。

## 版式
暖白纸面；标题用黄底贴纸或高亮强调一个词；列表用黄圆点；按钮黄底黑字。
记忆点是**一枚明黄色块/荧光笔**，其余安静。

```
AgenticOS                 (暖白)
──────────────────────────
这次更新，我们重写了搜索   （其中一个词黄底）
正文……
• 黄圆点 一条
• 黄圆点 一条
[黄底黑字 按钮]
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#f4efe4;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4efe4;">
<tr><td align="center" style="padding:44px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#fffdf7;">
    <tr><td style="padding:28px 32px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:15px;font-weight:700;color:#2a2420;">AgenticOS</div>
      <div style="height:14px;"></div>
    </td></tr>
    <tr><td style="padding:0 32px;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:24px;font-weight:700;line-height:1.35;color:#2a2420;">这次更新，我们<span style="background:#f4d63a;padding:0 4px;border-radius:3px;">重写了搜索</span></div>
      <div style="margin-top:14px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:15px;line-height:1.8;color:#6b625a;">之前的搜索经常"找得到但不对"，这次从结果排序到高亮都重做了一遍，你可以直接试试。</div>
    </td></tr>
    <tr><td style="padding:18px 32px 0;">
      <table cellpadding="0" cellspacing="0" border="0" style="width:100%;">
        <tr><td style="padding:4px 0;width:16px;vertical-align:top;"><div style="width:7px;height:7px;background:#f4d63a;border-radius:7px;font-size:0;line-height:0;margin-top:7px;">&nbsp;</div></td><td style="padding:4px 0;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:15px;color:#2a2420;">结果更准：按相关性而非时间排</td></tr>
        <tr><td style="padding:4px 0;vertical-align:top;"><div style="width:7px;height:7px;background:#f4d63a;border-radius:7px;font-size:0;line-height:0;margin-top:7px;">&nbsp;</div></td><td style="padding:4px 0;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:15px;color:#2a2420;">关键词自动高亮</td></tr>
        <tr><td style="padding:4px 0;vertical-align:top;"><div style="width:7px;height:7px;background:#f4d63a;border-radius:7px;font-size:0;line-height:0;margin-top:7px;">&nbsp;</div></td><td style="padding:4px 0;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:15px;color:#2a2420;">加载快了一半</td></tr>
      </table>
    </td></tr>
    <tr><td style="padding:24px 32px 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background:#f4d63a;border-radius:6px;">
          <a href="https://example.com" style="display:inline-block;padding:11px 26px;color:#2a2420;font-size:14px;font-weight:700;text-decoration:none;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;">去试试</a>
        </td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:24px 32px 26px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:14px;color:#6b625a;">产品组</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 把明黄当文字色（读不清、破坏识别）
- 用黄 + 多个其他色（warm 只有一个黄作为强调）
- 大圆角大投影卡片堆叠
- 用 emoji 代替黄圆点
