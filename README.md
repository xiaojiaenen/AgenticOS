# AgenticOS

AgenticOS 是一个前后端分离的智能体应用，当前仓库已经接入了聊天、智能体配置、Skill 本地存储、管理后台、审批流和数据看板。

默认开发端口：

- 前端：`http://127.0.0.1:3001`
- 后端：`http://127.0.0.1:8001`

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
```

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
