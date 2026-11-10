# Theme · press（书卷 / 编辑感 / 温暖衬线）

## 气质
出版、叙事、温暖。像一封用衬线字排印、从一臂之外能舒服读的书面信。标题有书卷气，
正文克制舒展，适合"读一段话"而不是"扫一眼表格"的邮件。

## 适合 / 不适合
- **适合**：对外介绍、announcement、活动邀请、长说明、需要一点文化感的沟通。
- **不适合**：密集数据表（用 datatable）；纯流程通知（用 swiss）；暗底技术现场（用 terminal）。

## 调色
| token | 值 | 用途 |
|---|---|---|
| ink | `#1c1a17` | 标题、正文（暖墨） |
| sub | `#5c5549` | 次要正文 |
| faint | `#6f665a` | 署名、meta |
| ochre | `#9c4f2b` | 唯一强调：一枚记号/短竖线（赭色，不是陶土 #D97757） |
| rule | `#cfc6b6` | 双细线 |
| paper | `#fbf8f2` | 暖纸底 |

## 排版
- 标题用衬线：`Georgia, 'Times New Roman', 'Songti SC', SimSun, serif`，`24px / 700`。
- 正文也用衬线（press 的字体即身份），`15px / 400 / lh 1.8`。
- 辅助/meta 用衬线斜体或小号衬线。

## 版式
报头（衬线品牌名 + 一枚赭色短竖线）→ 双细线分隔 → 衬线大标题 → 正文。
记忆点是**深浅两道衬线标题 + 双细线报头**的编辑感，赭色只点一处。

```
▎AgenticOS            登录/分类
═══════════════════   (双细线)
大标题（衬线 24px）

正文段落，衬线，舒展……
正文段落……

─── (细线)
李四 · meta
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#e9e4da;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#e9e4da;">
<tr><td align="center" style="padding:40px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#fbf8f2;border-top:3px solid #1c1a17;">
    <!-- 报头 -->
    <tr><td style="padding:26px 34px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="middle">
          <table cellpadding="0" cellspacing="0" border="0"><tr>
            <td style="width:3px;height:20px;background:#9c4f2b;font-size:0;line-height:0;">&nbsp;</td>
            <td style="padding-left:10px;font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:19px;font-weight:700;color:#1c1a17;">AgenticOS</td>
          </tr></table>
        </td>
        <td align="right" style="font-family:Georgia,'Times New Roman',serif;font-size:12px;font-style:italic;color:#6f665a;">通知</td>
      </tr></table>
    </td></tr>
    <!-- 双细线 -->
    <tr><td style="padding:16px 34px 0;">
      <div style="height:1px;background:#1c1a17;font-size:0;line-height:0;">&nbsp;</div>
      <div style="height:2px;background:#fbf8f2;font-size:0;line-height:0;">&nbsp;</div>
      <div style="height:1px;background:#1c1a17;font-size:0;line-height:0;">&nbsp;</div>
    </td></tr>
    <!-- 标题 -->
    <tr><td style="padding:26px 34px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC','SimSun',serif;font-size:24px;font-weight:700;line-height:1.35;color:#1c1a17;">关于今年年度技术分享会</div>
      <div style="margin-top:12px;font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.85;color:#5c5549;">各位同事，今年的技术分享会定在十二月中旬，主题围绕「把复杂系统讲清楚」。我们想请几位一线同学讲讲真实项目里的取舍。</div>
    </td></tr>
    <tr><td style="padding:14px 34px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:15px;line-height:1.85;color:#5c5549;">如果你有想分享的题目，这周内回复我即可。形式不限，二十分钟讲清一件事就好。</div>
    </td></tr>
    <tr><td style="padding:24px 34px 0;">
      <div style="font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:14px;color:#5c5549;">李四</div>
    </td></tr>
    <tr><td style="padding:26px 34px 0;"><div style="height:1px;background:#cfc6b6;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:12px 34px 26px;font-family:Georgia,'Times New Roman',serif;font-size:11px;color:#6f665a;">AGENTICOS · 系统通知</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 用陶土色 #D97757（那是 AI 默认三件套之一；press 用更深的赭 #9c4f2b）
- 标题用无衬线（破坏书卷感）
- 正文塞进密集表格（那是 datatable 的活）
- 每个标题上方挂全大写小标签
