# AgenticOS 部署指南

## 目录结构

```
deploy/
├── DEPLOY.md              # 部署文档（本文件）
├── Dockerfile.backend     # 后端 Docker 镜像
├── Dockerfile.frontend    # 前端 Docker 镜像
├── docker-compose.yml     # Docker Compose 配置
├── .env.example           # 环境变量示例
└── nginx/
    └── nginx.conf         # Nginx 配置
```

## 快速部署

### 1. 准备环境变量

```bash
cd deploy
cp .env.example .env
```

编辑 `.env` 文件，至少配置以下必填项：

```env
# 必填：OpenAI API Key
OPENAI_API_KEY=sk-your-api-key-here

# 必填：认证密钥（改为随机长字符串）
AUTH_SECRET_KEY=your-random-secret-key-here
```

### 2. 构建并启动

```bash
# 构建镜像
docker compose build

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f
```

### 3. 访问服务

- 前端：http://localhost:3001
- 后端 API：http://localhost:8001
- API 文档：http://localhost:8001/docs

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| OPENAI_API_KEY | 是 | - | OpenAI API Key |
| AUTH_SECRET_KEY | 是 | - | JWT 认证密钥 |
| OPENAI_BASE_URL | 否 | https://api.openai.com/v1 | OpenAI API 地址 |
| OPENAI_MODEL | 否 | gpt-5.4 | 使用的模型 |
| DATABASE_URL | 否 | sqlite:///./data/agenticos.db | 数据库连接字符串 |
| SKILL_STORAGE_DIR | 否 | ./data/skills | Skill 存储目录 |
| ENVIRONMENT | 否 | production | 运行环境 |
| CORS_ALLOW_ORIGINS | 否 | http://localhost:3001 | CORS 允许的源 |
| BACKEND_PORT | 否 | 8001 | 后端端口 |
| FRONTEND_PORT | 否 | 3001 | 前端端口 |
| VITE_API_BASE_URL | 否 | - | 前端 API 地址（留空使用相对路径） |

## 数据持久化

数据目录 `data/` 挂载到容器中，包含：

- `agenticos.db` - SQLite 数据库
- `skills/` - Skill 文件
- `websites/` - 网站文件

## 常用命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看日志
docker compose logs -f

# 查看后端日志
docker compose logs -f backend

# 查看前端日志
docker compose logs -f frontend

# 进入后端容器
docker compose exec backend bash

# 进入前端容器
docker compose exec frontend sh
```

## 数据库配置

### SQLite（默认）

```env
DATABASE_URL=sqlite:///./data/agenticos.db
```

### MySQL

```env
DATABASE_URL=mysql+pymysql://user:password@host:3306/database
```

## 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并部署
cd deploy
docker compose down
docker compose build --no-cache
docker compose up -d
```

## 故障排查

### 1. 启动失败

查看日志：
```bash
docker compose logs backend
docker compose logs frontend
```

### 2. 数据库问题

检查数据库文件权限：
```bash
ls -la data/
```

### 3. 端口冲突

修改 `.env` 中的端口配置：
```env
BACKEND_PORT=8002
FRONTEND_PORT=3002
```

### 4. OpenAI API 问题

检查 API Key 和网络连接：
```bash
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

## 生产环境建议

1. **使用 MySQL**：生产环境建议使用 MySQL 替代 SQLite
2. **配置 HTTPS**：使用 Nginx 反向代理并配置 SSL 证书
3. **定期备份**：定期备份 `data/` 目录
4. **监控日志**：配置日志收集和监控
5. **限制资源**：在 docker-compose.yml 中配置资源限制

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```
