# Theme · quiet（极简留白 / 近乎无装饰）

## 气质
极简、留白多、靠字重和字号撑层级，几乎零装饰。像一个人认真、平静地回你一句话。
适合短邮件、一对一、确认类——**越短越好看，越简单越不容易出错**。

## 适合 / 不适合
- **适合**：短回复、确认、一句话说明、一对一沟通、内部快速同步。
- **不适合**：信息量大的多段邮件（留白会变成空洞）；需要正式卷面（用 swiss/press）。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#1a1a1a` | 正文（近黑） |
| sub | `#6e6e6e` | 次要 |
| faint | `#6e6e6e` | 署名/meta |
| rule | `#e6e6e6` | 唯一的细线 |
| bg | `#ffffff` | 白 |

## 排版
- 正文 `16px / 400 / lh 1.85`（比常规大一点、行高更松，留白感来自这里）。
- 标题（如果有一句重的话）`20–24px / 600`，通常不需要标题。
- 署名 `14px` 灰。

## 版式
几乎只有一个居左的内容块 + 大量上下留白。一条极淡细线出现在非常次要的地方。
记忆点是**留白本身**和**一句干净的话**。

```
（大片空白）

张三，你好。
收到，我看一下，明天给你答复。

Best,
李四

（大片空白）
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#ffffff;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;">
<tr><td align="center" style="padding:64px 20px;">
  <table width="560" cellpadding="0" cellspacing="0" border="0" style="width:560px;max-width:560px;background:#ffffff;">
    <tr><td style="padding:0 40px;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;font-weight:600;letter-spacing:0.16em;color:#6e6e6e;">AGENTICOS</div>
    </td></tr>
    <tr><td style="height:40px;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:0 40px;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.85;color:#1a1a1a;">张三，你好。</div>
      <div style="margin-top:14px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.85;color:#1a1a1a;">收到，我看一下，明天上午给你答复。如果这个时间太紧，告诉我，我今晚加急。</div>
      <div style="margin-top:26px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;font-size:14px;line-height:1.7;color:#6e6e6e;">Best,<br>李四</div>
    </td></tr>
    <tr><td style="height:52px;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:0 40px;"><div style="height:1px;background:#e6e6e6;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:14px 40px 0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;color:#6e6e6e;">AGENTICOS</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 在这封邮件里塞卡片、色块、按钮（quiet 的力量就是"什么都没有"）
- 超过三段——超过就换 swiss/press
- 用大量颜色
