# AgenticOS 生产部署指南

## 架构概览

```
                    ┌──────────────────────────┐
                    │     Nginx (:10008)        │
                    │  /api/*  → Backend        │
                    │  /*      → Vite SPA       │
                    └──────────┬───────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼────────┐  ┌───▼──────────┐  ┌──▼────────┐
     │  Backend :10007 │  │  外部 MySQL  │  │ 外部 AI   │
     │  Python/FastAPI │  │              │  │ 服务      │
     └─────────────────┘  └──────────────┘  └───────────┘
```

## 前置条件

- **Docker 20.10+** 和 **Docker Compose 2.0+**
- **MySQL 8.0**（已部署可访问）
- **Node.js 22+**（仅本地打包前端时需要）
- 能访问内网基础镜像仓库 `172.73.0.156:85`

## 1. 初始化 MySQL 数据库

首次部署需要创建数据库和用户，后端启动时会自动建表：

```sql
CREATE DATABASE IF NOT EXISTS agenticos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'agenticos'@'%' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON agenticos.* TO 'agenticos'@'%';
FLUSH PRIVILEGES;
```

## 2. 配置环境变量

```bash
cd deploy
cp .env.example .env
```

编辑 `.env`，必填项：

```env
# 数据库
DATABASE_URL=mysql+pymysql://agenticos:你的密码@mysql-host:3306/agenticos

# AI 服务
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://your-ai-backend.com

# 认证密钥（务必替换为随机值）
AUTH_SECRET_KEY=生成一个随机长字符串
```

## 3. 打包前端（本地执行）

前端不在 Docker 内构建，需要先在本地打包：

```bash
cd frontend

# 可选：配置 API 地址（非同域部署时）
# 编辑 .env.local，设置 VITE_API_BASE_URL

npm install
npm run build
```

构建产物输出到 `frontend/dist/`，Docker 构建时直接复制进 nginx 镜像。

## 4. 构建镜像并启动

```bash
cd deploy
docker compose up -d --build
```

基础镜像自动从 `172.73.0.156:85` 拉取：
- `python:3.13-slim`
- `nginx:1.27-alpine`

## 5. 验证服务

```bash
# 后端健康检查
curl http://localhost:10007/api/v1/health/

# 前端页面
curl -I http://localhost:10008/
```

浏览器访问 `http://服务器IP:10008` 进入系统。

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| DATABASE_URL | 是 | - | MySQL 连接字符串 |
| OPENAI_API_KEY | 是 | - | AI 服务 API Key |
| AUTH_SECRET_KEY | 是 | - | JWT 签名密钥 |
| OPENAI_BASE_URL | 否 | https://api.openai.com/v1 | AI 服务地址 |
| OPENAI_MODEL | 否 | gpt-5.4 | 模型名称 |
| AUTH_TOKEN_EXPIRE_MINUTES | 否 | 10080 | Token 有效期（分钟） |
| CORS_ALLOW_ORIGINS | 否 | http://localhost:3001 | CORS 允许来源 |
| SKILL_STORAGE_DIR | 否 | ./data/skills | Skill 存储目录 |
| BASE_REGISTRY | 否 | 172.73.0.156:85 | 基础镜像仓库地址 |
| PYPI_MIRROR | 否 | https://pypi.org/simple | PyPI 镜像源 |
| BACKEND_PORT | 否 | 10007 | 后端端口 |
| FRONTEND_PORT | 否 | 10008 | 前端端口 |

## 数据持久化

宿主机 `data/` 目录挂载到容器 `/app/data/`：

- `skills/` — Skill 文件
- 其他运行时文件（SQLite 模式下数据库文件也在此目录）

## 前端更新

前端代码变更后，需重新本地打包：

```bash
cd frontend
npm run build
cd ../deploy
docker compose up -d --build frontend
```

## 常用命令

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 重启
docker compose restart

# 重新构建
docker compose up -d --build

# 仅重建前端
docker compose up -d --build frontend

# 查看日志
docker compose logs -f

# 只看后端
docker compose logs -f backend

# 进入容器
docker compose exec backend bash
```

## 故障排查

### 启动失败

```bash
docker compose logs backend
docker compose logs frontend
```

### 数据库连接问题

验证 MySQL 连通性：

```bash
docker compose exec backend python -c "
from app.db.session import engine
with engine.connect() as conn:
    print('数据库连接成功')
"
```

### 基础镜像拉取失败

确认能访问内网仓库：

```bash
curl http://172.73.0.156:85/v2/_catalog
```

### 端口冲突

修改 `.env`：

```env
BACKEND_PORT=10009
FRONTEND_PORT=10010
```

### 前端白屏或 404

检查 `frontend/dist/` 目录是否存在（本地构建产物）：

```bash
ls frontend/dist/index.html
```

如果不存在，先执行 `cd frontend && npm run build`。

## 生产建议

1. **HTTPS**：在 Nginx 前加反向代理处理 SSL 终止
2. **MySQL**：启用 SSL 连接，定期备份数据库
3. **密钥管理**：`AUTH_SECRET_KEY` 和 `OPENAI_API_KEY` 通过 secrets 管理
4. **日志轮转**：配置 Docker 日志 driver 限制日志大小
5. **资源限制**：在 docker-compose.yml 中添加 `deploy.resources`

   ```yaml
   services:
     backend:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 4G
   ```
