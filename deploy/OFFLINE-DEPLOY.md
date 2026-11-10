# AgenticOS 内网离线部署手册

> **适用前提**：内网**无外网出口**、**apt 源不可用**、外部 MySQL / Redis 已就绪。
>
> apt 不可用意味着内网**无法 docker build**（node/npm、Chromium 系统库都装不上），
> 所以运行时镜像必须**整体带过去**（`agenticos-runtime.tar.gz`，3.9GB）。

---

## 一、离线包内容（`pwsh deploy/package-intranet.ps1` 产出）

| 内容 | 大小（约） | 必需 | 说明 |
|---|---|---|---|
| `images/agenticos-runtime.tar` | 8GB | ✅ | 运行时镜像：pip 依赖 + Chromium + node/npm 全部预装 |
| `images/nginx.tar` | 50MB | ✅ | 前端 nginx 镜像（内网无镜像仓库时随包带） |
| `backend/` `frontend/dist` `data/` `deploy/` | 数百 MB | ✅ | 代码 + 前端产物 + 静态资源 + 部署编排 + 本手册 |
| `data/hf-cache/` | 随模型 | ✅ | 本地嵌入模型（bge-m3 或 bge-small-zh-v1.5），内网无 HF 出口 |
| `MANIFEST.sha256` | — | ✅ | 全包 SHA256 校验清单 |
| `agenticos-chromium.tar` | 679MB | ⬜ | Chromium 备份（镜像已内含，仅在重建镜像时需要） |

校验：`sha256sum -c MANIFEST.sha256`（`install.sh` 会自动做）。

---

## 二、内网部署机执行

### 一键安装（推荐）

```bash
sudo sh install.sh /opt/agenticos
# 脚本自动完成：校验 MANIFEST → 导入 images/*.tar →
# 拷贝 backend/frontend/data/deploy → 生成 .env（从 .env.offline.example）
```

### 手动步骤（等价，约 15 分钟）

```bash
# 1. 导入镜像（runtime 约 8GB，需要约 10GB 空闲磁盘；nginx 也在包内）
docker load -i images/agenticos-runtime.tar
docker load -i images/nginx.tar
docker images | grep agenticos-runtime

# 2. 安装代码与模型
mkdir -p /opt/agenticos
cp -a backend frontend data deploy /opt/agenticos/

# 3. 配置并启动
cd /opt/agenticos/deploy && cp .env.offline.example .env && vi .env
docker compose -f docker-compose.offline.yml up -d
```

> **nginx 镜像**：包内 `images/nginx.tar` 已随包；若内网有自己的镜像仓库，
> 也可以直接 `docker pull nginx:1.27-alpine`。

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
# 把新包里的 backend/ 与 frontend/dist 覆盖到部署目录后：
cd /opt/agenticos/deploy && docker compose -f docker-compose.offline.yml restart backend worker
```

### 依赖变了怎么办（两种路径）

**路径 A：内网 PyPI 可用 → 热装，不重建镜像（推荐）**

容器根文件系统是只读的（`read_only: true`），装不进 `site-packages`；但 `/app/data`
是可写卷。compose 里已把 `PYTHONPATH` 前置为 `/app/data/pylibs:/app/backend`，
所以新增依赖装到该目录即可优先生效：

```bash
cd /opt/agenticos/deploy
sh add-deps.sh 'requests==2.32.3' 'pandas>=2.0'
```

脚本做的事：`pip install --target=/app/data/pylibs -i <内网源>` → 重启 backend/worker。
验证：`docker exec agenticos-backend-1 python -c 'import pandas; print(pandas.__file__)'`
应显示 `/app/data/pylibs/...`。

> 注意：backend 与 worker 共享同一个 `/app/data` 卷，装一次两边都生效。
> 升级已有依赖（版本冲突）时，先 `rm -rf /opt/agenticos/data/pylibs` 再重装。

**路径 B：内网无 PyPI 或依赖涉及编译/系统库 → 必须重建镜像**

```bash
# 有外网的机器
docker build -f deploy/Dockerfile.runtime -t agenticos-runtime:latest .
docker save agenticos-runtime:latest > rt.tar && gzip -1 rt.tar   # 约 4GB
# 内网：gunzip -c rt.tar.gz | docker load
```

涉及 `torch`、`playwright`、需要 apt 系统库的包，只能走路径 B。

---

## 六、内网已知边界

| 项 | 处理 |
|---|---|
| PPT 配图（`search_images`） | 走 Pexels/Pixabay 公网 → 工具配置里关掉该工具，PPT 其余功能正常 |
| 网站智能体 `npm install` | 在 `.env` 设 `NPM_CONFIG_REGISTRY=https://nexus.gree.com/repository/npm-proxy/`、`NPM_CONFIG_STRICT_SSL=false`、`NEXUS_HOST=10.2.47.210`（compose 已为 backend/worker/scheduler 注入 env 与 `extra_hosts`）；默认走公网镜像，内外网同一份代码 |
| 网关自动登录（百通） | Chromium 与系统库已内置镜像，可直接用；**首次配置后需在「AI 提供商」里把百通的 `enable_thinking` 设为 `true`**（预设默认 `false`，不改则界面看不到「思考过程」区块，`reasoning_delta` 不会下发） |
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
