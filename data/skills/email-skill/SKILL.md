---
name: email-skill
description: 帮助用户读取、搜索、发送公司邮件，支持抄送
version: 1.1.0
tags: [email, imap, smtp, communication]
when_to_use: 用户需要读取、搜索、发送公司邮件时使用
allowed_tools: [read_emails, search_emails, get_email, send_email, count_emails]
---

# 公司邮件助手

## 邮箱凭据

登录系统时已自动配置公司邮箱，无需手动设置。
若凭据失效，请在侧边栏「邮箱设置」中更新密码。

## 邮箱地址格式

用户对话中可写邮箱号（如 `731302`）或完整地址（如 `731302@gree.com.cn`）。

**你的处理规则：**
- 调用任何邮件工具前，检查地址是否包含 `@`
- 不含 `@` → 自动拼接 `@gree.com.cn`
- 含 `@` → 原样使用
- 多个地址（逗号分隔）→ 逐个检查处理

示例：用户说"给 731302 发邮件"，你调用时 `to` 参数应为 `731302@gree.com.cn`。

## 可用工具

### read_emails
读取邮件列表。

**参数：**
- `folder` (可选): 邮箱文件夹，可选值：
  - `inbox`: 收件箱（默认）
  - `sent`: 已发送
  - `draft`: 草稿箱
  - `trash`: 已删除
  - `junk`: 垃圾邮件
- `limit` (可选): 返回数量，默认 10
- `offset` (可选): 跳过前 N 封，默认 0
- `unread_only` (可选): 是否只显示未读邮件，默认 false
- `since` (可选): 起始日期，格式 YYYY-MM-DD
- `before` (可选): 结束日期，格式 YYYY-MM-DD

**示例：**
```
read_emails(folder="inbox", limit=5, unread_only=true)
read_emails(since="2026-06-01", limit=20)
```

**返回格式：**
```
📬 收件箱 共 5 封邮件（最新 5 封）

● 1. 明天会议议程确认
   发件人: 731302@gree.com.cn
   时间: Wed, 12 Jun 2026 14:25:00 +0800
   ID: 123

○ 2. 6月工资条
   发件人: hr@gree.com.cn
   时间: Wed, 12 Jun 2026 11:30:00 +0800
   ID: 124
```

---

### search_emails
搜索邮件。

**参数：**
- `query` (必填): 搜索关键词（搜索主题和正文）
- `since` (可选): 起始日期，格式 YYYY-MM-DD
- `before` (可选): 结束日期，格式 YYYY-MM-DD
- `from_address` (可选): 发件人地址筛选

**示例：**
```
search_emails(query="会议", since="2026-06-01")
search_emails(query="报告", from_address="731302@gree.com.cn")
```

---

### get_email
读取邮件完整内容。

**参数：**
- `message_id` (必填): 邮件 ID（从 read_emails 或 search_emails 返回）

**示例：**
```
get_email(message_id="123")
```

**返回格式：**
```
📧 邮件详情

主题: 明天会议议程确认
发件人: 731302@gree.com.cn
收件人: 731303@gree.com.cn
抄送: 731300@gree.com.cn
时间: Wed, 12 Jun 2026 14:25:00 +0800
附件: 会议议程.pdf

==================================================

你好，

请确认明天下午2点的会议议程：
1. Q2业绩回顾
2. Q3计划讨论
3. 其他事项

请回复确认。
```

---

### send_email
发送邮件（需要用户确认后才能发送）。

**参数：**
- `to` (必填): 收件人邮箱地址，多个用逗号分隔（支持邮箱号或完整地址）
- `subject` (必填): 邮件主题
- `body` (必填): 邮件正文
- `cc` (可选): 抄送邮箱地址，多个用逗号分隔

**示例：**
```
# 用户说：给 731302 发邮件，标题"会议确认"
# 你调用时自动拼接后缀：
send_email(
    to="731302@gree.com.cn",
    subject="会议确认",
    body="已确认参加明天的会议。"
)

# 用户说：发给 731302 和 731303，抄送 731300
send_email(
    to="731302@gree.com.cn,731303@gree.com.cn",
    subject="项目进度更新",
    body="本周项目进度如下...",
    cc="731300@gree.com.cn"
)
```

**发送前确认：**
调用 send_email 前，必须向用户确认以下信息：
- 收件人
- 抄送（如有）
- 主题
- 正文摘要

用户确认后才会执行发送。

---

### count_emails
统计邮件数量。

**参数：**
- `folder` (可选): 邮箱文件夹，默认 inbox
- `unread_only` (可选): 是否只统计未读邮件，默认 false
- `since` (可选): 起始日期，格式 YYYY-MM-DD
- `before` (可选): 结束日期，格式 YYYY-MM-DD

**示例：**
```
count_emails(folder="inbox", unread_only=true)
count_emails(since="2026-06-01")
```

---

## 回复格式规范

### 邮件列表
使用列表格式，显示：
- 状态（未读 ● / 已读 ○）
- 序号
- 主题（超过50字截断）
- 发件人
- 时间
- 邮件 ID

### 邮件内容
提取关键信息：
- 主题、发件人、收件人、抄送
- 时间
- 附件列表
- 正文内容

### 发送确认
发送前必须确认：
```
即将发送邮件：
- 收件人: 731303@gree.com.cn
- 抄送: 731300@gree.com.cn
- 主题: 会议确认
- 正文: 已确认参加明天的会议。

确认发送吗？
```

## 安全提醒

- 不要在聊天中暴露密码
- 敏感邮件内容提醒用户注意安全
- 凭据通过 LDAP 登录自动管理，如需更新请在侧边栏操作

## 常见问题

**Q: 如何更新邮箱密码？**
A: 在侧边栏点击「邮箱设置」更新密码即可。

**Q: 可以发送带附件的邮件吗？**
A: 当前版本暂不支持附件，后续版本会添加。
