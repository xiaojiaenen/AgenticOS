---
name: email-design
description: 邮件设计指南——让 AI 生成的邮件正文更专业、更有品味，避免 AI 味。发送 HTML 邮件时加载。
version: 1.0.0
tags: [email, design, html, layout, typography]
when_to_use: 生成 HTML 邮件正文时，加载此指南以提升设计质量
allowed_tools: []
required_tools: []
---

# 邮件设计指南

**让你的邮件看起来像专业设计师做的，而不是 AI 生成的。**

---

## 一、反 AI 味铁律

### 禁止

- ❌ 大量使用渐变色背景
- ❌ 圆角卡片嵌套圆角卡片
- ❌ 过多的 emoji 表情 🎉✨🚀
- ❌ "亲爱的用户"、"尊敬的客户" 开头
- ❌ 过于正式、模板化的措辞
- ❌ 每段都有小标题
- ❌ 列表项超过 5 个
- ❌ 全文超过 500 字（除非必要）

### 必须

- ✅ 简洁直接，开门见山
- ✅ 用口语化但专业的语气
- ✅ 段落短小，每段 2-3 句
- ✅ 重点内容加粗，不要全部加粗
- ✅ 适当留白，不要塞满

---

## 二、邮件布局模板

### 模板 1: 商务汇报（推荐）

```html
<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6;">
  <div style="padding: 32px 24px;">
    <h2 style="font-size: 20px; font-weight: 600; margin: 0 0 16px; color: #0f172a;">项目进度汇报</h2>
    <p style="margin: 0 0 16px;">Hi 张三，</p>
    <p style="margin: 0 0 16px;">本周完成了用户系统的重构，主要包括：</p>
    <ul style="margin: 0 0 16px; padding-left: 20px;">
      <li style="margin-bottom: 8px;">登录流程优化，响应时间降低 40%</li>
      <li style="margin-bottom: 8px;">新增 OAuth 第三方登录支持</li>
      <li style="margin-bottom: 8px;">修复了 3 个安全漏洞</li>
    </ul>
    <p style="margin: 0 0 16px;">下周计划开始支付模块的开发。</p>
    <p style="margin: 0; color: #64748b; font-size: 14px;">Best,<br/>李四</p>
  </div>
  <div style="padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8;">
    此邮件由 AgenticOS 发送
  </div>
</div>
```

### 模板 2: 通知提醒

```html
<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6;">
  <div style="padding: 32px 24px;">
    <div style="background: #f0f9ff; border-left: 4px solid #0ea5e9; padding: 16px; margin-bottom: 24px; border-radius: 0 8px 8px 0;">
      <p style="margin: 0; font-weight: 500; color: #0c4a6e;">会议提醒</p>
      <p style="margin: 4px 0 0; font-size: 14px; color: #0369a1;">今天下午 3:00 - 产品评审会</p>
    </div>
    <p style="margin: 0 0 16px;">Hi 团队，</p>
    <p style="margin: 0 0 16px;">提醒大家今天下午 3 点有产品评审会议，请提前查看设计稿并准备反馈意见。</p>
    <p style="margin: 0 0 16px;">会议链接：<a href="#" style="color: #0ea5e9; text-decoration: none;">点击加入</a></p>
    <p style="margin: 0; color: #64748b; font-size: 14px;">谢谢！</p>
  </div>
</div>
```

### 模板 3: 简洁回复

```html
<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6;">
  <div style="padding: 32px 24px;">
    <p style="margin: 0 0 16px;">收到，我看一下。</p>
    <p style="margin: 0 0 16px;">关于这个问题，我的建议是先做一个 POC 验证可行性，然后再决定是否全面铺开。</p>
    <p style="margin: 0 0 16px;">明天给你详细方案。</p>
    <p style="margin: 0; color: #64748b; font-size: 14px;">Best,<br/>李四</p>
  </div>
</div>
```

---

## 三、设计规范

### 颜色

```css
/* 主色调 - 仅用于强调 */
--primary: #0ea5e9;      /* 天蓝色 */
--primary-dark: #0369a1;  /* 深蓝 */

/* 文字颜色 */
--text-primary: #0f172a;   /* 标题 */
--text-body: #1a1a1a;      /* 正文 */
--text-muted: #64748b;     /* 辅助文字 */
--text-light: #94a3b8;     /* 最浅文字 */

/* 背景 */
--bg-white: #ffffff;
--bg-gray: #f8fafc;
--bg-blue: #f0f9ff;        /* 提示背景 */

/* 边框 */
--border: #e2e8f0;
```

### 字体

```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
```

### 字号

| 元素 | 字号 | 字重 |
|------|------|------|
| 大标题 | 24px | 600 |
| 小标题 | 20px | 600 |
| 正文 | 16px | 400 |
| 辅助文字 | 14px | 400 |
| 脚注 | 12px | 400 |

### 间距

- 容器内边距：24-32px
- 段落间距：16px
- 列表项间距：8px
- 标题与正文间距：12-16px

---

## 四、HTML 邮件注意事项

### 必须使用内联样式

邮件客户端不支持 `<style>` 标签，所有样式必须写在 `style` 属性中：

```html
<!-- ✅ 正确 -->
<p style="margin: 0 0 16px; color: #1a1a1a;">正文</p>

<!-- ❌ 错误 -->
<style>p { margin-bottom: 16px; }</style>
<p>正文</p>
```

### 不要使用的 CSS 属性

- `position: fixed/sticky` — 邮件不支持
- `float` — 用 `display: flex` 代替
- `@media` 查询 — 部分客户端不支持
- `background-image` — 很多客户端屏蔽
- `box-shadow` — 部分客户端不支持

### 安全的 CSS 属性

- `margin`, `padding`
- `color`, `background-color`
- `font-family`, `font-size`, `font-weight`
- `line-height`, `text-align`
- `border`, `border-radius`
- `display: flex` (大部分客户端支持)

---

## 五、写作技巧

### 开头

```
❌ "尊敬的张三先生，您好！非常感谢您一直以来的支持与信任。"
✅ "Hi 张三，" 或 "张三，"
```

### 正文

```
❌ "经过我们团队的不懈努力和精心打磨，项目终于取得了重大突破性进展。"
✅ "项目进展顺利，本周完成了核心功能开发。"
```

### 结尾

```
❌ "如有任何问题，请随时与我们联系。我们将竭诚为您服务。祝您工作顺利！"
✅ "有问题随时找我。"
```

### 签名

```
❌ "此致敬礼！XXX团队 敬上"
✅ "Best, 李四"
```

---

## 六、检查清单

生成 HTML 邮件前检查：

- [ ] 内联样式（不用 `<style>` 标签）
- [ ] 最大宽度 600px（适配手机）
- [ ] 字体栈包含系统字体
- [ ] 颜色不超过 3 种
- [ ] 段落简短（2-3 句）
- [ ] 没有过多 emoji
- [ ] 语气自然不模板化
- [ ] 重点内容加粗
- [ ] 适当留白
