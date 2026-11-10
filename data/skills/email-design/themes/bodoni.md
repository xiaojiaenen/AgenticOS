# Theme · bodoni（报刊 / Didone 高反差）

> 改造自 garden-skills「Bodoni · 刊物 / Didone 高反差」。原版为时装刊头 / 大报设计，
> 这里收成邮件：保留「极端粗细对比的刊头大字 + 印刷惯例（双线、首字下沉、小型大写导语）+
> 颜色只留给风险」，缩到一封邮件能承载的量。

## 气质
印刷殿堂派：时装刊头 / 大报。纯白纸、真黑墨、发丝栏线，极端粗细对比的大标题压在从容的
老式衬线正文上。识别度来自**印刷惯例**而非颜色——刊头双线、首字下沉、小型大写导语。
颜色几乎只留给需要警示的地方。庄重、有格调、不喧哗。

## 适合 / 不适合
- **适合**：对外公告、邀请函、季度通讯、需要"分量感/正式感但要有格调"的邮件。
- **不适合**：纯事务流程通知（用 swiss）；暗底技术（terminal）；密集表格（datatable）。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#0c0c0c` | 刊头、正文（真黑） |
| sub | `#4a4a4a` | 正文次色 |
| faint | `#6a6a6a` | meta（≥4.5:1） |
| rule | `#111111` | 刊头粗细双线（黑） |
| hair | `#d8d8d8` | 细栏线 |
| accent | `#8a1c1c` | 酒红，只给"风险/提醒" |

## 排版
- 刊头用极高对比衬线（Didone 风格）：`Georgia / 'Playfair Display' fallback / Songti SC`，
  `34–40px / 700`，紧字距。
- 导语用**小型大写 + 字距**（不是普通小写）。
- 正文老式衬线 `15px / 400 / lh 1.8`；首字下沉。
- 中文没有真 Didone，用宋体高对比替代：`'Songti SC','SimSun',Georgia,serif`。

## 版式
刊头双线 → 刊头大字（可能两行）→ 小型大写导语 → 首字下沉的正文 → 细栏线 → 署名。
记忆点是**粗细双线的刊头 + 极端字重对比的大标题**。

```
═════════════════════   (粗黑线)
─────────────────────   (细黑线)
  WINTER OPEN DAY      (刊头大字 34-40px)
  冬季技术开放日        (中文刊头)

OPEN DAY · DEC 18      (小型大写导语)
─────────────────────
首字下沉 这 次开放日……
正文……
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#f4f2ed;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f2ed;">
<tr><td align="center" style="padding:44px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#ffffff;">
    <!-- 刊头粗细双线 -->
    <tr><td style="padding:24px 36px 0;">
      <div style="height:3px;background:#111111;font-size:0;line-height:0;">&nbsp;</div>
      <div style="height:1px;background:#111111;margin-top:4px;font-size:0;line-height:0;">&nbsp;</div>
    </td></tr>
    <!-- 刊头大字 -->
    <tr><td style="padding:22px 36px 0;">
      <div style="font-family:Georgia,'Playfair Display','Songti SC','SimSun',serif;font-size:38px;font-weight:700;line-height:1.1;color:#0c0c0c;letter-spacing:-0.01em;">Winter<br>Open Day</div>
      <div style="margin-top:6px;font-family:'Songti SC','SimSun',Georgia,serif;font-size:22px;font-weight:700;color:#0c0c0c;">冬季技术开放日</div>
    </td></tr>
    <!-- 小型大写导语 + 细栏线 -->
    <tr><td style="padding:18px 36px 0;">
      <div style="height:1px;background:#d8d8d8;font-size:0;line-height:0;">&nbsp;</div>
      <div style="padding-top:10px;font-family:Georgia,'Times New Roman',serif;font-size:11px;letter-spacing:0.22em;color:#4a4a4a;">OPEN DAY&nbsp;&nbsp;·&nbsp;&nbsp;DEC 18&nbsp;&nbsp;·&nbsp;&nbsp;ALL HANDS</div>
    </td></tr>
    <!-- 首字下沉正文 -->
    <tr><td style="padding:18px 36px 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="top" style="font-family:'Songti SC','SimSun',Georgia,serif;font-size:46px;font-weight:700;line-height:0.9;color:#0c0c0c;padding:4px 10px 0 0;">这</td>
        <td valign="top" style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.8;color:#0c0c0c;">次开放日定在十二月十八日全天。上午主会场由六位一线同学分享真实项目里的取舍，下午分三个小会场动手做。一年一次，不设直播，只现场。</td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:14px 36px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.8;color:#4a4a4a;">想来的同学回复本邮件报名。名额有限，按先来后到。带上你正在纠结的问题，比带笔更有用。</div>
    </td></tr>
    <!-- 提醒（酒红，唯一用色处） -->
    <tr><td style="padding:16px 36px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:13px;line-height:1.7;color:#8a1c1c;"><strong>报名截止 12 月 12 日</strong>，之后不再补录。</div>
    </td></tr>
    <tr><td style="padding:24px 36px 0;"><div style="height:1px;background:#d8d8d8;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:12px 36px 0;font-family:Georgia,'Times New Roman',serif;font-size:12px;letter-spacing:0.14em;color:#6a6a6a;">AGENTICOS&nbsp;&nbsp;·&nbsp;&nbsp;INVITATION</td></tr>
    <tr><td style="height:18px;font-size:0;line-height:0;">&nbsp;</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 用彩色当主导（bodoni 的颜色只留给风险，主体是黑白）
- 没有首字下沉 / 刊头双线（那样就失去报刊味）
- 大标题用无衬线
- 多个酒红强调（只给真正需要注意的一处）
