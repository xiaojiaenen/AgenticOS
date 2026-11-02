# AgenticOS 内网离线部署手册

> **适用前提**：内网有 PyPI 镜像源 + npm 源 + apt 源（可选），外部 MySQL/Redis 已就绪。
>
> 因为内网能装 pip/npm 依赖，**不需要带 8GB 运行时镜像**——内网直接 `docker build`。
> 唯一必须随包带的是 **Chromium 浏览器**（Playwright 从自己 CDN 下载，不在 PyPI）。

---

## 一、需要带进内网的三个包

| 包 | 大小 | 内容 |
|---|---|---|
| `agenticos-code.tar.gz` | 约 80MB | 后端代码 + 前端 dist + 静态资源 + 部署编排 + 本手册 |
| `agenticos-chromium.tar.gz` | 约 680MB | Playwright Chromium（企业网关自动登录用） |
| `agenticos-models.tar.gz` | 约 2.3GB | bge-m3 嵌入模型（内网无 HF 出口，必须随包） |

> 三个包都在构建机的 `/opt/agenticos-offline/` 下，用 U 盘或内网传输拷走。

---

## 二、内网部署机执行

```bash
# 1. 解包
mkdir -p /opt/agenticos && tar -xzf agenticos-code.tar.gz -C /opt/agenticos
cd /opt/agenticos

# 2. 解出 Chromium（供镜像构建使用）
mkdir -p chromium && tar -xzf /path/to/agenticos-chromium.tar.gz -C /tmp
cp -a /tmp/pw-export/. chromium/

# 3. 解出嵌入模型
mkdir -p data && tar -xzf /path/to/agenticos-models.tar.gz -C data/

# 4. 构建运行时镜像（走内网 PyPI/apt 源，不需要外网）
docker build -f deploy/Dockerfile.offline \
  --build-arg PYPI_MIRROR=http://<内网PyPI>/simple \
  --build-arg APT_MIRROR=<内网apt主机，如 apt.local> \
  -t agenticos-runtime:latest .

# 5. 拉 nginx（内网镜像仓库有就拉，没有就 docker load 随包的 nginx.tar.gz）
docker pull nginx:1.27-alpine || docker load -i images/nginx.tar.gz

# 6. 配置并启动
cd deploy && cp .env.offline.example .env && vi .env
docker compose -f docker-compose.offline.yml up -d
```

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

表结构与迁移由应用启动时自动完成。

---

## 四、npm 源配置（网站智能体需要）

容器内 `npm install` 默认走公网 registry，内网需指定：

```bash
# 方式一：构建镜像时写入全局 npmrc
docker build ... --build-arg NPM_REGISTRY=http://<内网npm>/ 
# 方式二：启动后在容器内配置（会被 read_only 挡住，需写到 /app/data）
docker exec agenticos-backend-1 sh -c \
  'echo "registry=http://<内网npm>/" >> /app/data/.npmrc'
```

并在 `.env` 里设 `npm_config_userconfig=/app/data/.npmrc`。

---

## 五、验证

```bash
curl http://127.0.0.1:10007/api/v1/health/        # {"status":"ok"}
curl -I http://127.0.0.1:10008/                    # 200
docker logs agenticos-backend-1 2>&1 | grep -iE "local embedding model ready|Redis 连接"
```

浏览器打开 `http://<IP>:10008` → 首次注册即管理员 → 管理后台配置 AI 提供商与 LDAP。

---

## 六、日常更新（只换代码，不重建镜像）

```bash
tar -xzf agenticos-code.tar.gz -C /opt/agenticos     # 覆盖代码与 dist
cd /opt/agenticos/deploy && docker compose -f docker-compose.offline.yml restart backend worker
```

只有 `pyproject.toml` 依赖变化时才需重新 `docker build`。

---

## 七、内网已知边界

| 项 | 处理 |
|---|---|
| PPT 配图（`search_images`） | 走 Pexels/Pixabay 公网 → 在工具配置里关掉该工具 |
| 网站智能体 `npm install` | 需内网 npm 源（见第四节） |
| Chromium 系统库 | 内网 apt 可用则 Dockerfile 自动装；否则网关自动登录不可用（其余功能不受影响） |
| 嵌入模型 | 必须随包（`agenticos-models.tar.gz`），内网无 HF 出口 |
| 通知邮件 | 需 SMTP 可达（内网邮件服务器） |
