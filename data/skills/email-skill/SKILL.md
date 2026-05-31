---
name: email-skill
description: 帮助用户读取、搜索、发送公司邮件，支持抄送、附件等
version: 1.0.0
tags: [email, imap, smtp, communication]
when_to_use: 用户需要读取、搜索、发送邮件，或管理邮箱凭据时使用
allowed_tools: [setup_email, read_emails, search_emails, get_email, send_email, count_emails, clear_email_credentials]
required_tools: [setup_email]
---

# 公司邮件助手

## 服务器配置

```
IMAP 服务器: mail.company.com
IMAP 端口: 993 (SSL)
SMTP 服务器: mail.company.com
SMTP 端口: 465 (SSL)
```

## 使用流程

### 首次使用

1. 用户提供邮箱地址和应用专用密码
2. 调用 `setup_email` 工具验证并保存凭据
3. 凭据仅在当前会话有效，会话结束自动清除

### 应用专用密码获取方式

**Gmail:**
1. 访问 https://myaccount.google.com
2. 安全 → 两步验证（需先开启）
3. 搜索"应用专用密码" → 生成

**Outlook:**
1. 访问 https://account.microsoft.com/security
2. 安全信息 → 应用密码 → 创建新密码

**QQ 邮箱:**
1. 登录 QQ 邮箱 → 设置 → 账户
2. 开启 IMAP/SMTP 服务
3. 生成授权码

**163 邮箱:**
1. 登录 163 邮箱 → 设置 → POP3/SMTP/IMAP
2. 开启 IMAP/SMTP 服务
3. 生成客户端授权码

## 可用工具

### setup_email
设置邮箱凭据，首次使用必须调用。

**参数：**
- `email_address` (必填): 公司邮箱地址
- `password` (必填): 应用专用密码（不是登录密码）

**示例：**
```
setup_email(
    email_address="zhangsan@company.com",
    password="abcd1234efgh5678"
)
```

---

### read_emails
读取邮件列表。

**参数：**
- `folder` (可选): 邮箱文件夹，可选值：
  - `inbox`: 收件箱（默认）
  - `sent`: 已发送
  - `draft`: 草稿箱
- `limit` (可选): 返回数量，默认 10
- `unread_only` (可选): 是否只显示未读邮件，默认 false

**示例：**
```
read_emails(folder="inbox", limit=5, unread_only=true)
```

**返回格式：**
```
📬 收件箱 共 5 封邮件

● 1. 明天会议议程确认
   发件人: manager@company.com
   时间: 2026-05-12 14:25
   ID: 123

○ 2. 5月份工资条
   发件人: hr@company.com
   时间: 2026-05-12 11:30
   ID: 124
```

---

### search_emails
搜索邮件。

**参数：**
- `query` (必填): 搜索关键词（搜索主题和正文）
- `since` (可选): 起始日期，格式 YYYY-MM-DD
- `from_address` (可选): 发件人地址筛选

**示例：**
```
search_emails(query="会议", since="2026-05-01")
search_emails(query="报告", from_address="manager@company.com")
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
发件人: manager@company.com
收件人: zhangsan@company.com
抄送: lisi@company.com
时间: 2026-05-12 14:25
附件: 会议议程.pdf

==================================================

张三你好，

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
- `to` (必填): 收件人邮箱地址，多个用逗号分隔
- `subject` (必填): 邮件主题
- `body` (必填): 邮件正文
- `cc` (可选): 抄送邮箱地址，多个用逗号分隔

**示例：**
```
# 单个收件人
send_email(
    to="lisi@company.com",
    subject="会议确认",
    body="已确认参加明天的会议。"
)

# 多个收件人 + 抄送
send_email(
    to="lisi@company.com,wangwu@company.com",
    subject="项目进度更新",
    body="本周项目进度如下...",
    cc="manager@company.com,leader@company.com"
)
```

**发送前确认：**
智能体在调用 send_email 前，必须向用户确认以下信息：
- 收件人
- 抄送（如有）
- 主题
- 正文摘要

用户确认后才会执行发送。

---

### clear_email_credentials
清除当前会话的邮箱凭据。

**参数：**
- `session_id` (自动传入): 会话 ID

**示例：**
```
clear_email_credentials()
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
- 收件人: xxx@company.com
- 抄送: yyy@company.com
- 主题: 会议确认
- 正文: 已确认参加明天的会议。

确认发送吗？
```

## 安全提醒

- 不要在聊天中暴露密码
- 敏感邮件内容提醒用户注意安全
- 提示用户定期更换应用专用密码
- 凭据仅在当前会话有效，退出后自动清除

## 常见问题

**Q: 为什么需要应用专用密码而不是登录密码？**
A: Gmail、Outlook 等邮箱服务商已禁止"不安全应用"使用密码登录。应用专用密码更安全，可随时撤销。

**Q: 凭据会保存多久？**
A: 仅在当前会话有效，会话结束或调用 clear_email_credentials 后自动清除。

**Q: 可以发送带附件的邮件吗？**
A: 当前版本暂不支持附件，后续版本会添加。
