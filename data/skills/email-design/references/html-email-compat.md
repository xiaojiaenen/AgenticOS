# 邮件客户端 CSS 兼容全表

邮件客户端（Gmail / Outlook / Apple Mail / 企业 Exchange）支持的 CSS 是网页的极小
真子集。这张表是写邮件 HTML 前必看的"能不能用"清单。

## 可靠可用 ✅

| 属性 | 说明 |
|---|---|
| `<table>` / `<tr>` / `<td>` 嵌套 | 唯一可靠的布局方式 |
| 内联 `style="..."` | 所有样式都应该内联 |
| `margin` / `padding` | 用 `padding` 比 `margin` 在 Outlook 里更稳 |
| `color` / `background-color` | 纯色可靠；渐变不可靠 |
| `font-family` / `font-size` / `font-weight` / `font-style` | 系统字体栈 |
| `line-height` / `letter-spacing` / `text-align` | |
| `border` / `border-top` 等 | 细线分隔可靠 |
| `width` / `max-width`（用法见下） | `<table width="600">` 可靠 |
| `<a href>` | 唯一 100% 可靠的"交互" |
| `:hover` + `transition`（小范围） | Apple Mail / iOS / Outlook.com 支持；Gmail 不播但静态可读 |

## 按客户端分级

| 属性 | Gmail | Outlook(Win) | Apple Mail | 备注 |
|---|---|---|---|---|
| `border-radius` | ✅ | ❌ 直角 | ✅ | 不关键，别依赖 |
| `box-shadow` | ❌ | ❌ | ✅ | 不用 |
| `background-image` | ⚠️ 部分 | ❌ | ✅ | 不用 |
| `@media` | ✅ 部分 | ⚠️ | ✅ | 只用于移动端微调 |
| `@keyframes` | ❌ | ❌ | ⚠️ | 不用 |
| `display:flex/grid` | ⚠️ | ❌ | ✅ | **多列一律用 table** |
| `max-width` on div | ✅ | ❌ | ✅ | 用 `<table width>` 更稳 |

## 硬红线（踩了邮件基本废掉）

- ❌ `<style>` 里写类选择器/排版规则 —— Gmail 剥掉，正文变裸文字
- ❌ `display:flex` / `grid` 做主布局 —— Outlook 退化成竖排
- ❌ `position` / `float` —— 布局塌
- ❌ 外链字体 —— 被拦，回退到难看字体
- ❌ `@keyframes` —— 全剥

## 安全的按钮写法

```html
<table cellpadding="0" cellspacing="0" border="0"><tr>
  <td style="background:#2f6f4f;border-radius:6px;">
    <a href="https://..."
       style="display:inline-block;padding:12px 28px;color:#ffffff;
              font-size:14px;font-weight:600;text-decoration:none;">
      查看方案
    </a>
  </td>
</tr></table>
```

## 宽度写法

```html
<!-- 外层铺满、内层固定 600px 居中 -->
<table width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" border="0"
           style="width:600px;max-width:600px;">
      ...
    </table>
  </td></tr>
</table>
```

## 字体栈（中文必带）

```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
             'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC',
             'Helvetica Neue', Arial, sans-serif;
```
少了 `PingFang SC / Microsoft YaHei`，部分客户端中文会回退成很难看的衬线。

## 深浅主题

深色底邮件在「强制深色模式」的客户端里可能被自动反色。若用深底（terminal 主题），
不要指望它一定保持深底；关键信息（文字、数字）要在任何底色下都可读。
