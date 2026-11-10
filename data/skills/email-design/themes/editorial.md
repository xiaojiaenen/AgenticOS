# Theme · editorial（杂志式 / 大标题 / 图片与引文位）

## 气质
杂志版式：大标题占版面、有配图位或引文块、编辑感强但不做作。像一本内刊或对外简报的
一封。比 press 更现代、更"版式化"，比 warm 更成熟。

## 适合 / 不适合
- **适合**：对外简报、活动邀请、季度通讯、带配图的介绍、需要"版式感"的表达型邮件。
- **不适合**：纯事务通知（用 swiss）、密集数据（用 datatable）、加密/安全类。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#16161a` | 标题、正文 |
| sub | `#57575f` | 次要正文 |
| faint | `#6b6b75` | meta |
| accent | `#b0472f` | 一枚砖红：栏目记号/引文强调（比陶土更沉） |
| rule | `#dcdce2` | 细线 |
| bg | `#ffffff` | 白 |

## 排版
- 大标题 `28–34px / 700`，可略微紧字距。
- 引文块用斜体衬线或大号引号。
- 正文 `15px / 400 / lh 1.8`。

## 版式
栏目名（一枚砖红小记号 + 名字）→ 大标题 → 导语 → 一张图位（或引文块）→ 正文。
记忆点是**大标题 + 一处图片或引文块**的版式节奏。

```
▎活动    (砖红小记号 + 栏目名)
大标题占一大块（28–34px）

导语一句……

[图位] （或引文块：大引号 / 砖红强调）
正文……
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#f2f2f4;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f2f2f4;">
<tr><td align="center" style="padding:44px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#ffffff;">
    <!-- 栏目名 -->
    <tr><td style="padding:28px 34px 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="width:3px;height:14px;background:#b0472f;font-size:0;line-height:0;">&nbsp;</td>
        <td style="padding-left:8px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:12px;font-weight:700;letter-spacing:0.14em;color:#b0472f;">活动</td>
      </tr></table>
    </td></tr>
    <!-- 大标题 -->
    <tr><td style="padding:14px 34px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:30px;font-weight:700;line-height:1.25;color:#16161a;letter-spacing:-0.01em;">冬季技术开放日，<br>周四见</div>
    </td></tr>
    <!-- 导语 -->
    <tr><td style="padding:14px 34px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.75;color:#57575f;">一天，六个真实项目，讲我们今年踩过的坑和修好的路。</div>
    </td></tr>
    <!-- 图位（没有图就用引文块，不要画假图） -->
    <tr><td style="padding:22px 34px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#faf3f0;border-left:3px solid #b0472f;">
        <tr><td style="padding:22px 24px;font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:18px;font-style:italic;line-height:1.6;color:#8a3a26;">「把复杂系统讲清楚，是这个行业最缺的能力。」</td></tr>
      </table>
    </td></tr>
    <!-- 正文 -->
    <tr><td style="padding:20px 34px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:15px;line-height:1.85;color:#57575f;">这次开放日放在本周四全天，上午是主会场分享，下午分三个小会场动手做。名额有限，想来的同学回复本邮件报名，我按先来后到排。</div>
    </td></tr>
    <!-- 按钮 -->
    <tr><td style="padding:24px 34px 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background:#b0472f;border-radius:4px;">
          <a href="https://example.com/signup" style="display:inline-block;padding:11px 26px;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;">我要报名</a>
        </td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:24px 34px 0;"><div style="height:1px;background:#dcdce2;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:14px 34px 26px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;color:#6b6b75;">AGENTICOS · 内刊</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 没有真图就别画假图——用引文块占位（画假图是 AI 味的头号来源）
- 用陶土 #D97757（editorial 用更沉的砖红 #b0472f）
- 大标题配渐变背景
- 每个栏目都套同一套"图左文右/图右文左"的锯齿节奏
