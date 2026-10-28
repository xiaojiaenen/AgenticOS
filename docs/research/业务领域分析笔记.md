# AgenticOS 业务领域分析笔记

> 分析日期：2026-07-22
> 分析师：Business Analyzer

---

## 一、项目概述

AgenticOS 是一个**可自托管的前后端分离智能体应用平台**，为开发者和企业提供多模态 AI 智能体编排、工具管理、审批流和管理后台的完整解决方案。

### 5 个元问题

| 问题 | 回答 |
|------|------|
| **解决了谁的什么问题？** | 开发者/企业需要一个可自托管的 AI 智能体平台，能灵活编排多模态智能体（PPT/视频/网站/邮件）、管理工具权限、进行 HITL 审批，并支持私有化部署 |
| **目标用户（4 类）** | 最终用户、管理员、智能体开发者、自托管运维者 |
| **一句话价值主张** | 开箱即用、可自托管的多模态 AI 智能体平台，用户通过对话就能生成 PPT、视频、网站和邮件回复 |
| **业务领域** | AI Agent 平台 / 智能体编排与交付 |
| **主要能力** | 多模式 AI 对话、PPT 智能设计、视频创作、邮箱助手、网站工程师、管理后台、Skill 技能系统 |

---

## 二、数据库 Schema 分析（Phase 2.0）

### 数据源：SQLite（SQLAlchemy ORM models.py）

### 实体-表映射

| 表名 | 业务含义 | 核心字段 | 关联 |
|------|---------|---------|------|
| `users` | 用户账号 | id, email, name, password_hash, role (user/admin), is_active, auth_source (local/ldap) | → auth_sessions, agent_sessions, memories |
| `auth_sessions` | 登录会话 | session_id, user_id, expires_at, revoked_at | → users |
| `auth_rate_limits` | 登录频率限制 | key(IP/email), scope, attempts, blocked_until | — |
| `agent_sessions` | AI 对话会话 | session_id, user_id, agent_profile_id, system_prompt, max_steps, summary | → users, agent_profiles |
| `agent_messages` | 对话消息 | id, session_id, message_json (序列化的消息), created_at | → agent_sessions |
| `agent_usage_events` | LLM 调用用量 | id, user_id, session_id, model_name, response_mode, input_tokens, output_tokens, tool_calls, latency_ms | → users, agent_profiles |
| `agent_tool_configs` | 工具权限配置 | mode (模式), tool_name, enabled, requires_approval, approval_sub_tools_json | → 按 mode 分组 |
| `agent_profiles` | 智能体配置 | id, name, slug, description, system_prompt, response_mode (general/ppt/video/email/website), enabled, listed, is_builtin | → agent_profiles_tools, agent_profiles_skills |
| `agent_profile_tools` | 智能体工具绑定 | profile_id, tool_name, enabled, requires_approval | → agent_profiles |
| `agent_profile_skills` | 智能体技能绑定 | profile_id, skill_id, enabled | → agent_profiles, skills |
| `agent_profile_audiences` | 智能体可见范围 | profile_id, user_id | → agent_profiles, users |
| `skills` | Skill 技能包 | id, name, slug, description, root_dir, enabled | → agent_profile_skills |
| `user_installed_agents` | 用户安装的智能体 | user_id, profile_id, pinned | → users, agent_profiles |
| `agent_approvals` | 工具调用审批 | approval_id, session_id, tool_name, arguments_json, status (pending/approved/rejected/timeout) | → agent_sessions |
| `ppt_artifacts` | PPT 生成产物 | artifact_id, session_id, title, slide_count, deck_json, preview_html | → agent_sessions |
| `video_artifacts` | 视频生成产物 | artifact_id, session_id, user_id, project_id, title, video_path, duration_sec, resolution, fps | → agent_sessions |
| `memories` | 用户记忆 | id, user_id, content, memory_type (fact/preference), importance, source (auto/manual/tool) | → users |
| `user_email_credentials` | 邮箱凭据 | user_id, email_address, imap_host/port, smtp_host/port, password_encrypted | → users |
| `announcements` | 系统公告 | id, title, subtitle, body, theme, is_published, starts_at, ends_at, dismissible | → users(created_by) |
| `website_deploys` | 网站部署记录 | id, session_id, project_slug, stack (vanilla/vue/react), status (pending/approved/rejected/deployed/failed) | → agent_sessions |
| `external_systems` | 外部系统集成 | id, name, description, base_url, auth_type, oauth 配置, JWT 配置 | → external_apis |
| `external_apis` | 外部系统 API 定义 | id, system_id, name, method, path, request_body_schema, requires_approval | → external_systems |
| `external_api_params` | API 参数定义 | api_id, name, param_type (path/query/body), data_type, required, source | → external_apis |
| `external_user_credentials` | 用户外部凭据 | user_id, system_id, oauth 令牌, JWT 缓存, connection_status | → users, external_systems |
| `system_settings` | 系统设置项 | key, value (KV 键值对) | — |

### 状态枚举值

| 字段 | 枚举值 | 业务含义 |
|------|--------|---------|
| UserModel.role | user / admin | 普通用户 vs 管理员 |
| UserModel.auth_source | local / ldap | 本地注册 vs LDAP 认证 |
| ApprovalModel.status | pending / approved / rejected / timeout | 审批四态 |
| WebsiteDeployModel.status | pending / approved / rejected / deployed / failed | 网站部署五态 |
| AnnouncementModel.theme | aurora 等 | 公告主题风格 |
| AgentProfileModel.response_mode | general / ppt / video / email / website | 智能体五种模式 |
| ExternalSystemModel.auth_type | api_key / bearer / basic / oauth2 / custom | 外部系统认证方式 |
| ExternalUserCredentialModel.connection_status | connected / disconnected / error | 外部系统连接状态 |

---

## 三、业务实体详解（Phase 2.1）

### 核心实体

#### 1. 🔐 用户（User）
用户是平台的核心主体，分为普通用户和管理员两种角色，支持本地注册和 LDAP 企业认证。

- **生命周期**：注册 → 登录使用 → 停用/删除
- **关键状态**：is_active（是否可用）
- **业务属性**：email（唯一标识）、name（显示名）、role（角色）、auth_source（认证来源）

#### 2. 🧠 智能体配置（Agent Profile）
智能体是平台提供 AI 能力的单位。每个智能体有自己的身份、能力和行为模式。

- **生命周期**：创建（内置或自定义）→ 发布上架（Agent Store）→ 被用户安装 → 使用 → 停用
- **关键状态**：enabled（是否启用）、listed（是否在商店展示）、is_builtin（是否系统内置）
- **5 种模式**：通用(general)、PPT 设计(ppt)、视频创作(video)、邮箱助手(email)、网站工程(website)
- **关联资产**：绑定的工具集、绑定的 Skill 技能、可见范围（audience）

#### 3. 💬 对话会话（Agent Session）
用户与 AI 智能体的每一次交互会话。

- **生命周期**：创建 → 消息交换（多轮）→ 结束（手动关闭或超时）
- **关键属性**：所选智能体、系统提示词、最大步数、对话摘要

#### 4. 📦 Skill 技能包
上传的本地技能文件集合，可以绑定到智能体上增强其能力。

- **生命周期**：上传 → 注册到系统 → 关联智能体 → 使用 → 下架
- **关键属性**：名称、描述、文件路径、启停状态

#### 5. 🔧 工具（Tool Config）
智能体可以调用的功能单元，如计算、文件操作、搜索引擎等。

- **生命周期**：系统预定义 → 按模式启用/禁用 → 设置审批级别 → 使用
- **关键属性**：所属模式、启用状态、是否需要审批、子工具审批配置
- **审批粒度**：支持按子工具（sub-tool）级别控制审批

#### 6. 📊 PPT 产物（PPT Artifact）
AI 生成的演示文稿产物。

- **生命周期**：AI 设计幻灯片 → 预览 → 导出 .pptx
- **关键属性**：标题、页数、SVG 幻灯片 JSON、预览 HTML

#### 7. 🎬 视频产物（Video Artifact）
AI 生成的视频产物。

- **生命周期**：选择模板 → 创建项目 → 多帧 Storyboard → Chromium 录制 → ffmpeg 编码 → MP4 导出
- **关键属性**：模板 ID、时长、分辨率、FPS、文件大小、声道信息

#### 8. 🌐 外部系统（External System）
平台可集成的外部 API 系统（如 JIRA、Dinky 等数据平台）。

- **生命周期**：注册（手动或 API）→ 配置认证 → 授权用户 → 通过智能体调用
- **关键属性**：名称、URL、认证方式（API Key/Bearer/OAuth2/Basic/JWT）、启停状态
- **支持 6 种认证协议**：API Key、Bearer Token、Basic Auth、OAuth2、JWT Login、自定义签名

#### 9. 📢 公告（Announcement）
系统管理员发布的通知。

- **生命周期**：创建草稿 → 定时发布 → 展示期间 → 到期下线
- **关键属性**：标题、正文、主题风格、发布窗口、可关闭性、是否仅展示一次

---

## 四、业务流程（Phase 2.2）

### 流程 1：用户注册与登录

```
用户 → [注册/登录页面] → 填写凭证 → [认证服务] → 验证 → 生成 JWT → 返回用户信息
                                                                     ↓
                                                              √ 管理员 → 进入管理后台
                                                              √ 普通用户 → 进入聊天页面
                                                              × 失败 → 返回错误信息
```

**分支**：
- **LDAP 模式**：LDAP_ENABLED=true 时，禁用密码登录和注册，跳转到 LDAP 网关认证
- **注册验证码**：可配置邮件验证码发送（通过 NOTIFY_EMAIL）
- **频率限制**：同一 IP/邮箱 5 次/10 分钟，超限封锁 15 分钟

### 流程 2：AI 对话交互（核心流程）

```
用户 → 聊天页面输入消息 → POST /api/v1/agent/stream
                                ↓
                 [AgentService] 拼接系统提示词 + 选择智能体模式
                                ↓
                 [Wuwei Agent] 调用 LLM → 流式 token 输出
                                ↓
                      需要调用工具？──是──→ [工具审批]
                      否                     ↓ 等待用户
                      继续流式输出         审批通过？──是──→ 执行工具
                                ↓         否             ↓
                       返回最终响应        拒绝/超时 → 告知用户终止
                                ↓
                [SSE 事件流] 实时推送至前端
                                ↓
                      消息存入 agent_messages
                      用量记录存入 agent_usage_events
```

**支持事件类型**：
- `session` → `run_status` → `delta`（token 流）→ `reasoning_delta` → `tool_calls` → `tool_results` → `approval_required` → `done` / `error`

### 流程 3：PPT 智能生成

```
用户 → [PPT 设计师] → 描述需求 → Agent 解析需求
                                    ↓
                    选择主题（20+ 预置品牌主题）
                                    ↓
                    规划幻灯片结构（推荐 8-14 页）
                                    ↓
                    每 3 页调用 save_slides_batch 写 SVG
                                    ↓
                    SVG 写入文件 → 系统后处理管线
                                    ↓
                [pptx_to_svg 管线] → SVG 渲染引擎
                [svg_finalize 管线] → 嵌入图片/图标、裁剪、修复
                [svg_to_pptx 管线] → 导出原生 .pptx
                                    ↓
                artifact_ready SSE 事件 → 用户预览/下载
```

### 流程 4：视频创作

```
用户 → [视频创作] → 选择模板（23 种专业模板）
                        ↓
           创建项目 → video_create_project
                        ↓
           video_set_template → 注入设计指南
                        ↓
           video_write_content_graph → 编写 Storyboard（多场景）
                        ↓
           video_write_frame_html（每帧独立）
                        ↓
           video_write_preview_html → 预览
                        ↓
           video_export_mp4 → Chromium 录制 + ffmpeg 编码 → MP4 输出
```

### 流程 5：网站工程

```
用户 → [网站工程师] → 选择技术栈（Vanilla/Vue/React）
                        ↓
            copy_template → 复制项目模板
                        ↓
            多轮对话中通过写文件构建页面
                        ↓
            npm install + npm run build
                        ↓
            build_website / deploy_website
                        ↓
            [审批流] → 管理员批准→部署到目标域名
```

### 流程 6：邮箱管理

```
用户 → [邮箱助手] → setup_email 配置 IMAP/SMTP
                        ↓
            连接外部邮箱（Gmail/Outlook/QQ/163/企业邮箱）
                        ↓
            工具集：count_emails / read_emails / search_emails
                   / get_email / send_email
                        ↓
            用户确认后发送邮件（安全性保护）
```

### 流程 7：审批流（HITL）

```
Agent 调用需审批的工具 → LenientHitlMiddleware 拦截
                              ↓
            ApprovalManager.request_approval()
            → 创建 agent_approvals 记录（status=pending）
                              ↓
            SSE approval_required 事件 → 前端弹出 PendingApprovalPanel
                              ↓
               用户操作 ─┬─ 批准 → 执行工具调用
                        ├─ 拒绝 → 告知 Agent 终止
                        └─ 超时（300s）→ 自动拒绝
```

### 流程 8：外部系统集成调用

```
管理员注册外部系统 → 配置认证方式 → 发布
                              ↓
           用户授权外部系统凭据（OAuth/API Key）
                              ↓
           管理员创建外部 API 定义（method + path + 参数）
                              ↓
           绑定 API 到智能体模式（agent_profile_external_systems）
                              ↓
           用户在对话中通过 tool 调用外部系统 API
```

---

## 五、业务规则（Phase 2.3）

### 认证与安全
| # | 规则 | 触发条件 | 执行动作 | 业务原因 |
|---|------|---------|---------|---------|
| 1 | **登录频率限制** | 同一 IP/邮箱 5 次尝试失败 | 封锁 15 分钟 | 防暴力破解 |
| 2 | **LDAP 模式禁用本地** | LDAP_ENABLED=true | 隐藏密码登录和注册入口 | 企业统一认证管理 |
| 3 | **LADP 自动创建用户** | LDAP_AUTO_CREATE_USERS=true | LDAP 首次登录自动建本地用户 | 免去管理员预建账号 |
| 4 | **第一个用户自动 admin** | 数据库中无任何用户 | 新注册用户 role=admin | 初始化引导 |
| 5 | **JWT 鉴权** | 所有 API（除 auth/health） | 校验 Bearer Token | 接口安全保护 |

### 工具与智能体
| # | 规则 | 触发条件 | 执行动作 | 业务原因 |
|---|------|---------|---------|---------|
| 6 | **模式工具隔离** | 不同模式（general/ppt等） | 只加载该模式配置的工具 | 按需暴露能力，减少安全风险 |
| 7 | **子工具审批粒度** | 工具配置了 sub-tools | 按子工具分别控制审批 | 精细化管理（如文件读取审批但写入不审批） |
| 8 | **智能体不可见规则** | listed=false 或设置了 audience | 只对指定用户展示 | 分权限、分团队管理 |
| 9 | **Context 压缩阈值** | 对话 >16 轮 | LLM 自动压缩历史，保留最近 6 轮 | 控制 token 消耗 |

### PPT 生成
| # | 规则 | 触发条件 | 执行动作 | 业务原因 |
|---|------|---------|---------|---------|
| 10 | **反千篇一律** | 任何 PPT 生成请求 | 强制要求主题多样性、布局多样性 | 避免 AI 生成感 |
| 11 | **PPT 页数下限** | PPT 生成 | ≥3 页，推荐 8-14 页 | 保证内容充实 |
| 12 | **SVG 导出约束** | SVG 存盘时 | 禁止 style/foreignObject/mask/animate/rgba | 兼容 PPTX 导出格式 |

### 部署与运维
| # | 规则 | 触发条件 | 执行动作 | 业务原因 |
|---|------|---------|---------|---------|
| 13 | **网站部署审批** | deploy_website 工具 | 创建审批记录，等待管理员批准 | 防止误发布 |
| 14 | **通知冷却时间** | 任务通知 | 两次通知间隔 ≥120s | 避免通知轰炸 |
| 15 | **HITL 超时** | 审批超过 300s | 自动拒绝 | 防止 Agent 无限等待 |

---

## 六、用户角色与权限（Phase 2.4）

| 角色 | 权限范围 | 典型能力 |
|------|---------|---------|
| **管理员 (admin)** | 全平台管理 | 用户管理、智能体上下架、工具配置、审批决策、数据看板、外部系统管理、公告发布、系统设置 |
| **普通用户 (user)** | 使用已安装的智能体 | 多模式对话、PPT 生成、视频创作、邮箱管理、网站开发、管理个人记忆、安装商店智能体 |

### 权限矩阵

| 功能区域 | 管理员 | 普通用户 |
|---------|--------|---------|
| 💬 AI 对话 | ✅ | ✅ |
| 📊 PPT 生成 | ✅ | ✅ |
| 🎬 视频创作 | ✅ | ✅ |
| 📧 邮箱管理 | ✅ | ✅ |
| 🌐 网站开发 | ✅ | ✅（需要管理员批准部署）|
| 🤖 管理智能体配置 | ✅ 全量 | ❌ |
| 🔧 配置工具权限 | ✅ | ❌ |
| 📦 上传/管理 Skills | ✅ | ❌ |
| 📢 发布公告 | ✅ | ❌ |
| 📈 查看数据看板 | ✅ | ❌ |
| 👥 用户管理 | ✅ | ❌ |
| 🔗 外部系统集成 | ✅ | ❌（但可授权自己的凭据）|
| 🧠 管理个人记忆 | ✅ | ✅ |

---

## 七、领域划分（Phase 2.5）

```
┌────────────────────────────────────────────────────────────┐
│                   AgenticOS 业务领域                          │
├────────────────┬────────────────┬─────────────────────────┤
│  AI 智能体编排   │  内容生产服务     │  平台管理               │
│  (Core Domain) │  (Supporting)  │  (Supporting)           │
├────────────────┼────────────────┼─────────────────────────┤
│ 对话引擎        │  PPT 模板引擎    │ 用户 & 认证              │
│ 工具注册与调用    │  视频渲染管线     │ 智能体商店               │
│ 模式路由        │  网站构建器      │ 数据看板 & 统计         │
│ 上下文压缩       │  邮箱连接器      │ 公告系统                │
│ 审批中间件       │  外部系统集成     │ 系统设置                │
│ 多智能体编排     │                │                         │
│ Skill 技能系统  │                │                         │
└────────────────┴────────────────┴─────────────────────────┘
```

### 子领域说明

#### 1. AI 智能体编排（核心子域 🎯）
平台最核心的差异化竞争力。基于 wuwei 框架的 Agent 引擎，提供多模式智能体路由、工具调用、审批中间件、上下文管理、多智能体（Leader-Worker）编排和 Skill 技能注入。

**关键资产**：agent_service.py、multi_agent_graph_service.py、approval_manager.py、skill_service.py

#### 2. 内容生产服务（支撑子域 🛠️）
帮助用户生成 PPT、视频、网站、邮件、代码等内容。每个生产方式对应一种 Agent 模式，共享底层工具框架，但各自有独立的渲染引擎和模板系统。

**关键资产**：ppt/（模板引擎 + SVG 管线）、video 模板系统、website_deploy_service.py

#### 3. 平台管理（支撑子域 🔧）
管理员管理平台的基础设施：用户、角色、权限、工具配置、外部系统集成、数据看板、公告。

**关键资产**：auth_service.py、dashboard 端点、tool_config_service.py、external_system_service.py

---

## 八、API 业务能力清单

| 路由前缀 | 业务能力 | 主要操作 |
|---------|---------|---------|
| `/api/v1/auth` | 认证管理 | register, login, login_with_code, logout, me, send_code, ldap 相关 |
| `/api/v1/agent` | 智能体交互 | stream（SSE 流式对话）、approval 决策、PPT 导出 |
| `/api/v1/agent-profiles` | 智能体配置 CRUD | 列表、创建、更新、删除、商店浏览、安装 |
| `/api/v1/skills` | Skill 技能管理 | 上传、列表、启用/停用、关联智能体 |
| `/api/v1/tool-config` | 工具权限配置 | 按模式管理工具启停、审批级别 |
| `/api/v1/users` | 用户管理 | 列表、创建、更新、状态管理 |
| `/api/v1/dashboard` | 数据看板 | stats（用户/用量/趋势）、对话详情、webhook |
| `/api/v1/email` | 邮箱管理 | setup, stats, search, read, send_email |
| `/api/v1/video` | 视频创作 | CRUD 项目、模板管理、帧编辑、导出 |
| `/api/v1/website` | 网站开发 | 模板复制、构建、部署（含审批） |
| `/api/v1/memory` | 记忆管理 | 添加、搜索、删除 |
| `/api/v1/announcements` | 公告系统 | CRUD、发布/下架 |
| `/api/v1/external-systems` | 外部系统集成 | 注册系统、配置认证、管理 API、用户凭据授权 |
| `/api/v1/files` | 文件管理 | 上传、列表、下载 |
| `/api/v1/credential-proxy` | 凭据代理 | 加密凭据中转 |
| `/api/v1/settings` | 系统设置 | KV 设置读写 |
| `/api/v1/suggest` | 智能建议 | 输入建议 |
| `/api/v1/health` | 健康检查 | 系统状态 |
