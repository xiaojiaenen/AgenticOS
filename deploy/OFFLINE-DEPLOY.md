# AgenticOS 内网离线部署手册

> **适用前提**：内网**无外网出口**、**apt 源不可用**、外部 MySQL / Redis 已就绪。
>
> apt 不可用意味着内网**无法 docker build**（node/npm、Chromium 系统库都装不上），
> 所以运行时镜像必须**整体带过去**（`agenticos-runtime.tar.gz`，3.9GB）。

---

## 一、四个离线包（构建机 `/home/offline/`，共 6.9GB）

| 包 | 大小 | 必需 | 内容 |
|---|---|---|---|
| `agenticos-runtime.tar.gz` | 3.9GB | ✅ | 运行时镜像：pip 依赖 + Chromium + node/npm 全部预装 |
| `agenticos-models.tar` | 2.3GB | ✅ | bge-m3 嵌入模型（内网无 HF 出口） |
| `agenticos-code.tar.gz` | 80MB | ✅ | 后端代码 + 前端 dist + 静态资源 + 部署编排 + 本手册 |
| `agenticos-chromium.tar` | 679MB | ⬜ | Chromium 备份（镜像已内含，仅在重建镜像时需要） |

校验：`sha256sum -c SHA256SUMS`（清单在同一目录）。

---

## 二、内网部署机执行（约 15 分钟）

```bash
# 1. 导入镜像（3.9GB，解压约 8GB，需要约 10GB 空闲磁盘）
gunzip -c agenticos-runtime.tar.gz | docker load
docker images | grep agenticos-runtime        # 应显示 8.05GB

# 2. 解包代码与模型
mkdir -p /opt/agenticos && tar -xzf agenticos-code.tar.gz -C /opt/agenticos
cd /opt/agenticos
mkdir -p data && tar -xf /path/to/agenticos-models.tar -C data/

# 3. nginx（内网仓库有就 pull；没有则需随包带，见下方说明）
docker pull nginx:1.27-alpine

# 4. 配置并启动
cd deploy && cp .env.offline.example .env && vi .env
docker compose -f docker-compose.offline.yml up -d
```

> **nginx 镜像**：`nginx:1.27-alpine` 仅 48MB，若内网无镜像仓库，
> 在有网机器 `docker save nginx:1.27-alpine | gzip > nginx.tar.gz` 一起带过去。

---

## 三、`.env` 必填（外部 MySQL / 外部 Redis）

```bash
DATABASE_URL=mysql+pymysql://agenticos:<密码>@<MySQL主机>:3306/agenticos
REDIS_URL=redis://<Redis主机>:6379/0
AUTH_SECRET_KEY=<openssl rand -hex 32>
EXTERNAL_SYSTEM_ENCRYPTION_KEY=<另一个随机值>
KNOWLEDGE_EMBEDDING_LOCAL_MODEL=BAAI/bge-m3
KNOWLEDGE_EMBEDDING_LOCAL_DIMENSIONS=1024
CORS_ALLOW_ORIGINS=http://<部署机IP>:10008
OPENAI_BASE_URL=http://<内网模型网关>/v1
OPENAI_API_KEY=<内网网关 key>
```

**不需要 Redis Stack**：记忆向量检索已改为进程内余弦，普通 Redis 够用。

MySQL 建库（`utf8mb4` 必须，否则中文写不进去）：

```sql
CREATE DATABASE agenticos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'agenticos'@'%' IDENTIFIED BY '<密码>';
GRANT ALL PRIVILEGES ON agenticos.* TO 'agenticos'@'%';
```

表结构与 alembic 迁移在应用启动时自动完成。

---

## 四、验证

```bash
curl http://127.0.0.1:10007/api/v1/health/     # {"status":"ok",...}
curl -I http://127.0.0.1:10008/                 # 200
docker logs agenticos-backend-1 2>&1 | grep -iE "local embedding model ready|Redis 连接"
docker exec agenticos-backend-1 python -m alembic current   # 最新 head
```

浏览器打开 `http://<IP>:10008` → 首次注册即管理员 → 管理后台配 AI 提供商、LDAP、记忆清理。

---

## 五、日常更新（只换代码，不重建镜像）

```bash
tar -xzf agenticos-code.tar.gz -C /opt/agenticos
cd /opt/agenticos/deploy && docker compose -f docker-compose.offline.yml restart backend worker
```

只有 `pyproject.toml` 依赖变化时才需在有网机器重建镜像并重传。

---

## 六、内网已知边界

| 项 | 处理 |
|---|---|
| PPT 配图（`search_images`） | 走 Pexels/Pixabay 公网 → 工具配置里关掉该工具，PPT 其余功能正常 |
| 网站智能体 `npm install` | 需内网 npm 源；设 `npm_config_userconfig=/app/data/.npmrc` 并在其中写 registry |
| 网关自动登录（百通） | Chromium 与系统库已内置镜像，可直接用 |
| 嵌入模型 | 必须随包，内网无 HF 出口 |
| 通知邮件 | 需 SMTP 可达（内网邮件服务器） |
| 镜像更新 | 只能整包重传（内网无法 build）；建议改动攒批 |

---

## 七、镜像重建（仅在有外网的机器）

```bash
docker build -f deploy/Dockerfile.runtime -t agenticos-runtime:latest .
docker save agenticos-runtime:latest > rt.tar && gzip -1 rt.tar   # 约 4GB
```

> 该构建需外网：pip（PyPI 或镜像）、apt（Debian 源）、playwright（Chromium CDN）。
> 若构建机 apt 也不可用，改用 `deploy/Dockerfile.offline` 并自备 chromium 目录。
