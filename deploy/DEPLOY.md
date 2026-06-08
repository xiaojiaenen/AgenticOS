# AgenticOS 生产部署指南

## 架构概览

```
                    ┌──────────────────────────┐
                    │     Nginx (:10008)        │
                    │  /api/*  → Backend        │
                    │  /*      → Vite SPA       │
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Backend :10007     │
                    │  Python/FastAPI     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼────────┐  ┌───▼──────────┐  ┌──▼────────┐
     │  外部 MySQL     │  │  外部 Redis  │  │ 外部 AI   │
     │  （可选）       │  │  （可选）    │  │ 服务      │
     └─────────────────┘  └──────────────┘  └───────────┘
```

- MySQL 和 Redis 都是外部服务，不由 docker-compose 管理
- Redis 留空则自动 fallback 到内存模式（开发环境可用）

## 前置条件

- **Docker 20.10+** 和 **Docker Compose 2.0+**
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

可选但推荐：

```env
# Redis（验证码、输入补全等缓存功能，留空则内存 fallback）
REDIS_URL=redis://your-redis-host:6379/0

# 系统通知邮箱（验证码发送、任务完成通知、欢迎邮件）
NOTIFY_EMAIL_ADDRESS=noreply@yourdomain.com
NOTIFY_EMAIL_PASSWORD=your-app-password
NOTIFY_SMTP_HOST=smtp.exmail.qq.com
NOTIFY_SMTP_PORT=465
NOTIFY_SMTP_SSL=true
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

### 必填

| 变量名 | 说明 |
|--------|------|
| DATABASE_URL | MySQL 连接字符串 |
| OPENAI_API_KEY | AI 服务 API Key |
| AUTH_SECRET_KEY | JWT 签名密钥 |

### Redis（可选）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| REDIS_URL | 空（内存 fallback） | Redis 连接地址，如 `redis://your-redis-host:6379/0` |
| REDIS_CLUSTER | false | 是否使用 Redis 集群模式 |

### 系统通知邮箱（可选）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| NOTIFY_EMAIL_ADDRESS | 空 | 发件邮箱地址 |
| NOTIFY_EMAIL_PASSWORD | 空 | 邮箱密码/应用专用密码 |
| NOTIFY_SMTP_HOST | 空 | SMTP 服务器地址 |
| NOTIFY_SMTP_PORT | 465 | SMTP 端口 |
| NOTIFY_SMTP_SSL | true | 是否使用 SSL |
| NOTIFY_TASK_MIN_SECONDS | 120 | 任务完成通知阈值（秒） |

### AI 服务

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| OPENAI_BASE_URL | https://api.openai.com/v1 | AI 服务地址 |
| OPENAI_MODEL | gpt-5.4 | 模型名称 |

### 认证

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| AUTH_TOKEN_EXPIRE_MINUTES | 10080 | Token 有效期（分钟） |

### 其他

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| CORS_ALLOW_ORIGINS | http://localhost:3001 | CORS 允许来源 |
| SKILL_STORAGE_DIR | ./data/skills | Skill 存储目录 |
| BASE_REGISTRY | 172.73.0.156:85 | 基础镜像仓库地址 |
| PYPI_MIRROR | https://pypi.org/simple | PyPI 镜像源 |
| BACKEND_PORT | 10007 | 后端端口 |
| FRONTEND_PORT | 10008 | 前端端口 |

## 数据持久化

宿主机 `data/` 目录挂载到容器 `/app/data/`：

- `charts/` — SVG 图表模板（PPT 图表生成）
- `design-systems/` — 设计系统定义（PPT/网站主题）
- `design-themes/` — 设计主题
- `layouts/` — 布局模板
- `skills/` — Agent 技能
- `website-templates/` — 网站模板
- 运行时产物（ppt-output/、ppt-sessions/、websites/）由应用自动创建

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

### Redis 连接问题

验证 Redis 连通性：

```bash
docker compose exec backend python -c "
from app.core.redis import get_redis, is_redis_memory
print('内存模式' if is_redis_memory() else 'Redis 已连接')
"
```

### 验证码发送失败

检查系统邮箱配置：

```bash
docker compose exec backend python -c "
from app.core.config import get_settings
s = get_settings()
print(f'邮箱: {s.notify_email_address}')
print(f'SMTP: {s.notify_smtp_host}:{s.notify_smtp_port}')
print('配置完整' if s.notify_email_address and s.notify_smtp_host else '配置缺失')
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
3. **Redis**：生产环境建议使用外部 Redis 服务，配置密码认证
4. **密钥管理**：`AUTH_SECRET_KEY`、`OPENAI_API_KEY`、`NOTIFY_EMAIL_PASSWORD` 通过 secrets 管理
5. **日志轮转**：配置 Docker 日志 driver 限制日志大小
6. **监控**：配置后端健康检查告警
