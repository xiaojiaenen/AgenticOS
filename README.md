# AgenticOS

AgenticOS 是一个前后端分离的智能体应用，当前仓库已经接入了聊天、智能体配置、Skill 本地存储、管理后台、审批流和数据看板。

默认开发端口：

- 前端：`http://127.0.0.1:3001`
- 后端：`http://127.0.0.1:8001`

## 内置智能体

AgenticOS 内置了 4 个专业智能体，覆盖常见场景：

| 智能体 | 模式 | 说明 |
|--------|------|------|
| **通用助手** | `general` | 日常问答、资料整理、轻量工具调用 |
| **PPT 设计师** | `ppt` | 使用 SVG 原生图形生成演示文稿，支持导出 .pptx |
| **视频创作** | `video` | 智能视频生成，23 种专业模板，Chromium 录制 + ffmpeg 编码 |
| **邮箱助手** | `email` | 邮件管理，支持读取、搜索、发送和统计 |
| **网站工程师** | `website` | 页面方案、前端代码、交互原型，支持 Vue/React |

### 视频创作模式

视频创作模式基于 [html-video](https://github.com/nexu-io/html-video) 项目，支持：

- **23 种专业模板**：数据可视化、标题动画、产品展示、解说视频等
- **多帧 Storyboard**：支持多场景视频，自动拼接
- **专业级动画**：GSAP Timeline 编排，5 层叠放设计
- **高清导出**：MP4 格式，支持自定义分辨率和帧率

**系统依赖**：

```bash
# macOS
brew install ffmpeg  # 或 sudo port install ffmpeg
uv run playwright install chromium
```

## 项目结构

```text
AgenticOS/
├─ backend/                  # FastAPI 后端
│  ├─ app/
│  │  ├─ api/v1/endpoints/   # 真实接口定义
│  │  ├─ core/               # 配置、安全、基础能力
│  │  ├─ db/                 # 数据库模型与初始化
│  │  ├─ schemas/            # 请求/响应模型
│  │  └─ services/           # Agent / Skill / Dashboard 等服务
│  ├─ data/                  # 本地数据库与技能文件
│  ├─ .env.example
│  ├─ main.py
│  ├─ pyproject.toml
│  └─ uv.lock
├─ frontend/                 # React + Vite 前端
│  ├─ src/
│  ├─ .env.example
│  ├─ package.json
│  └─ vite.config.ts
└─ data/                     # Docker 部署时推荐挂载的数据目录
   ├─ skills/                # Skill 文件
   ├─ video-projects/        # 视频项目文件
   ├─ ppt-sessions/          # PPT 会话文件
   └─ websites/              # 网站项目文件
```

## 内置智能体详细说明

### 1. 通用助手（general）

适合日常问答、资料整理、轻量工具调用和多轮协作。

**可用工具**：计算、时间、文件操作、记忆

### 2. PPT 设计师（ppt）

使用 SVG 原生图形生成演示文稿，支持导出原生 .pptx 文件，形状可编辑。

**特性**：
- 15 种核心布局 + 71 种图表模板
- 主题系统：apple、github、stripe 等 20+ 主题
- 反千篇一律：自动避免 AI 生成感
- 批量生成：每 3 页一批，减少调用次数

**可用工具**：save_slide、save_slides_batch、read_slide、batch_edit_slides、submit_spec_lock、submit_slide_plan、search_icons、search_images 等

### 3. 视频创作（video）

智能视频生成，将想法转化为动画 MP4 视频。

**特性**：
- **23 种专业模板**：数据可视化、标题动画、产品展示、解说视频等
- **多帧 Storyboard**：支持多场景视频，自动拼接
- **专业级动画**：GSAP Timeline 编排，5 层叠放设计
- **高清导出**：MP4 格式，支持自定义分辨率和帧率
- **自动设计规范**：设置模板时自动注入 SKILL.md 设计指南

**系统依赖**：
```bash
# macOS
brew install ffmpeg  # 或 sudo port install ffmpeg
uv run playwright install chromium
```

**可用工具**：video_search_templates、video_create_project、video_set_template、video_write_content_graph、video_write_frame_html、video_write_preview_html、video_export_mp4 等

**模板类别**：
| 类别 | 模板 | 适用场景 |
|------|------|---------|
| data-viz | frame-data-chart-nyt, frame-nyt-graph | 数据可视化 |
| social-shorts | frame-glitch-title, frame-kinetic-type | 社交短视频 |
| product-demo | frame-product-promo | 产品展示 |
| marketing | frame-bold-poster, frame-liquid-bg-hero | 营销宣传 |
| presentation | frame-swiss-grid, frame-build-minimal | 演示文稿 |
| explainer | frame-decision-tree | 解说视频 |
| intro-outro | frame-logo-outro | 片头片尾 |
| ambient | frame-takram-organic, frame-warm-grain | 氛围背景 |

### 4. 邮箱助手（email）

帮助用户高效管理公司邮件。

**特性**：
- **邮件概览**：快速查看收件箱、未读邮件、重要邮件
- **邮件统计**：快速获取邮件总数、未读数量等统计信息
- **邮件搜索**：按发件人、主题、日期、关键词搜索
- **邮件阅读**：读取邮件内容、查看附件信息
- **邮件回复**：帮助用户撰写和发送邮件（需用户确认）

**可用工具**：count_emails、read_emails、search_emails、get_email、send_email、setup_email

**支持的邮箱**：
- Gmail
- Outlook/Office 365
- QQ 邮箱
- 163/126 邮箱
- 企业邮箱（IMAP/SMTP）

### 5. 网站工程师（website）

用于页面方案、前端代码、交互原型和网站结构设计。

**特性**：
- 三种技术栈：vanilla（HTML+CSS+JS）、vue（Vue3+Vite）、react（React18+Vite）
- 设计系统：内置 CSS 变量主题系统
- 一键构建：自动 npm install + npm run build

**可用工具**：copy_template、check_website_project、build_website、deploy_website、write_text_file、replace_text_in_file 等

## 本地运行

### 1. 启动后端

```bash
cd backend
uv sync
cp .env.example .env
uv run python main.py
```

后端启动后可访问：

- 首页：`http://127.0.0.1:8001/`
- Swagger：`http://127.0.0.1:8001/docs`
- 健康检查：`http://127.0.0.1:8001/api/v1/health/`

后端关键环境变量：

- `OPENAI_API_KEY`：必填，模型服务密钥
- `OPENAI_BASE_URL`：可选，兼容网关地址
- `OPENAI_MODEL`：默认 `gpt-5.4`
- `DATABASE_URL`：默认 `sqlite:///./data/agenticos.db`
- `SKILL_STORAGE_DIR`：默认 `./data/skills`
- `AUTH_SECRET_KEY`：建议在正式环境改成长随机串
- `HITL_REQUIRE_APPROVAL_TOOLS`：示例文件里已包含 `run_skill_python_script`

补充说明：

- 本地模式下，Skill 文件默认保存在 `backend/data/skills/`
- 第一个注册的账号会自动成为管理员
- Skill 工具默认开启审批，管理员可在后台继续调整

### 2. 启动前端

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

前端默认地址：

- `http://127.0.0.1:3001`

前端环境变量：

- `VITE_API_BASE_URL`：默认 `http://127.0.0.1:8001`
- `VITE_API_PROXY_TARGET`：本地开发代理目标，默认 `http://127.0.0.1:8001`

### 3. 本地联调顺序

建议按下面顺序启动：

1. 启动后端并确认 `http://127.0.0.1:8001/docs` 可打开
2. 启动前端并访问 `http://127.0.0.1:3001`
3. 注册首个账号，系统会自动赋予管理员权限
4. 进入管理后台，配置用户、智能体、Skill 与审批规则

## Skill 系统

AgenticOS 的 Skill 系统允许智能体按需加载专业知识。每个 Skill 是一个 Markdown 文件，包含特定领域的指导和规范。

### 内置 Skill

| Skill | 说明 | 适用智能体 |
|-------|------|-----------|
| `video-workflow` | 视频创作工作流 | video |
| `video-design-guide` | HTML 动画设计规范 | video |
| `video-templates` | 23 个模板速查 | video |
| `ppt-workflow` | PPT 创作工作流 | ppt |
| `ppt-design-guide` | SVG 设计规范 | ppt |
| `ppt-template-library` | 布局和图表模板 | ppt |
| `website-design-taste` | 网站设计品味 | website |

### 使用方式

智能体在对话中可以通过 `load_skill("skill-name")` 加载 Skill：

```
用户：帮我做一个数据可视化视频
智能体：load_skill("video-workflow")  ← 加载工作流
智能体：video_search_templates("data visualization")
智能体：load_skill("video-templates")  ← 查看模板库
智能体：video_create_project(...)
智能体：video_set_template(...)
智能体：load_skill("video-design-guide")  ← 加载设计规范
智能体：video_write_preview_html(...)
智能体：video_export_mp4(...)
```

### Skill 存储位置

- 本地模式：`backend/data/skills/`
- Docker 模式：`/app/data/skills/`

## 当前后端接口

以下都是当前项目里已经存在的真实接口：

### 认证

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

### 智能体

- `POST /api/v1/agent/stream`
- `POST /api/v1/agent/approvals/{approval_id}/decision`
- `GET /api/v1/agent/sessions/{session_id}`
- `GET /api/v1/agent/artifacts/{artifact_id}`

### 智能体配置

- `GET /api/v1/agent-profiles`
- `POST /api/v1/agent-profiles`
- `PATCH /api/v1/agent-profiles/{profile_id}`
- `DELETE /api/v1/agent-profiles/{profile_id}`
- `GET /api/v1/agent-store`
- `POST /api/v1/agent-store/{profile_id}/install`
- `DELETE /api/v1/agent-store/{profile_id}/install`
- `GET /api/v1/my/agents`

### Skill 管理

- `GET /api/v1/skills`
- `POST /api/v1/skills`
- `POST /api/v1/skills/upload`
- `PATCH /api/v1/skills/{skill_id}`
- `DELETE /api/v1/skills/{skill_id}`

### 管理后台

- `GET /api/v1/dashboard/stats`
- `GET /api/v1/dashboard/conversations`
- `GET /api/v1/dashboard/conversations/{session_id}`
- `DELETE /api/v1/dashboard/conversations/{session_id}`
- `GET /api/v1/tool-config`
- `PUT /api/v1/tool-config/modes/{mode}`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `PATCH /api/v1/users/{user_id}`
- `PATCH /api/v1/users/{user_id}/status`
- `DELETE /api/v1/users/{user_id}`

## Docker 部署

仓库已经补好了下面这些文件：

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `docker-compose.yml`

### 1. 准备环境变量

先在 `backend/` 下创建 `.env`：

```bash
cd backend
cp .env.example .env
```

至少补上：

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.4
AUTH_SECRET_KEY=replace-with-a-long-random-secret
```

### 2. 构建并启动

在仓库根目录执行：

```bash
docker compose up -d --build
```

启动后默认访问地址：

- 前端：`http://127.0.0.1:3001`
- 后端：`http://127.0.0.1:8001`
- Swagger：`http://127.0.0.1:8001/docs`

### 3. Docker 部署说明

- 前端容器使用 `nginx` 托管静态资源
- 浏览器里的 `/api` 请求由 `nginx` 反向代理到 `backend:8001`
- Compose 会把根目录 `./data` 挂载到后端容器 `/app/data`
- Docker 模式下：
  - 数据库文件位于 `/app/data/agenticos.db`
  - Skill 文件位于 `/app/data/skills`

## 常用命令

### 后端

```bash
cd backend
uv sync
uv run python main.py
uv run pytest
```

### 前端

```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```
