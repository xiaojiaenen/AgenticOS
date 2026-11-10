# AgenticOS 生产部署指南

## 架构概览

```
                     ┌────────────────────────────┐
                     │       Nginx (:10008)       │
                     │  /api/*      → Backend     │
                     │  /sites/*    → 已上线网站  │
                     │  /*          → Vite SPA    │
                     └─────────────┬──────────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │  Backend  (:10007 → :8000)│
                     │  Python/FastAPI           │
                     └─────────────┬─────────────┘
                                   │  同镜像另一个容器
                     ┌─────────────▼─────────────┐
                     │  Worker (arq 任务队列)    │
                     └───────────────────────────┘

        Backend / Worker ──► 外部 MySQL（必须）
                         ──► 外部 Redis（生产必须）
                         ──► 外部 AI 服务 / 企业网关
```

- **MySQL 和 Redis 都是外部服务，不由 docker-compose 管理**（compose 里没有数据库/缓存容器）。
- **Redis 生产必填**：验证码缓存、审批跨实例广播、登录限流、arq 任务队列都依赖它。
  留空会退化为进程内记忆 fallback——限流计数不共享、worker 无法工作，仅限单机演示。
  普通 Redis 即可：记忆向量检索是进程内余弦计算，不依赖 RediSearch / Redis Stack。
- Backend 与 Worker 共用同一镜像、同一套环境变量，只差启动命令。

## 两种部署方式

| 方式 | compose 文件 | 镜像 | 适用 |
|------|--------------|------|------|
| **A. 运行时镜像（推荐）** | `docker-compose.runtime.yml` | `agenticos-runtime:latest`（pip 依赖 + Chromium + node/npm 预装，代码 volume 挂载） | 生产 / 内网。更新代码只需 restart，不重建镜像 |
| B. 薄镜像构建 | `docker-compose.yml`（默认） | `Dockerfile.backend` 构建时装依赖 | 快速试用 / CI 可联网构建 |

下文命令默认对方式 A 生效；用方式 B 时去掉 `-f docker-compose.runtime.yml`
（或 `export COMPOSE_FILE=docker-compose.runtime.yml` 后命令完全一致）。

## 前置条件

- **Docker 20.10+** 和 **Docker Compose 2.0+**
- **Node.js 22+**（仅本地打包前端时需要）
- 外部 MySQL 8 与 Redis 已就绪、网络可达
- 方式 A 需要先构建或导入 `agenticos-runtime` 镜像（见第 4 节；内网离线见
  [OFFLINE-DEPLOY.md](OFFLINE-DEPLOY.md)）

## 1. 初始化 MySQL 数据库

首次部署需要创建数据库和用户，后端启动时会自动建表与执行 alembic 迁移
（`utf8mb4` 必须，否则中文写不进去）：

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
# 数据库（外部 MySQL）
DATABASE_URL=mysql+pymysql://agenticos:你的密码@mysql-host:3306/agenticos

# Redis（外部 Redis，生产必填）
REDIS_URL=redis://redis-host:6379/0

# AI 服务（兜底配置）
# 注意：这里是**兜底**。只要在「管理后台 → AI 提供商」建了启用中的提供商，
# 就优先使用提供商配置，本段不再参与。两者都没有时对话才会报错。
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://your-ai-backend.com

# 认证密钥（务必替换为随机值）
AUTH_SECRET_KEY=生成一个随机长字符串
```

> **AI 提供商（可选）**：登录管理后台 →「智能体与能力 → AI 提供商」可以建多条配置并
> 全局切换，无需重启。`openai_compatible` 类型填地址 + Key + 模型即可；`enterprise_cookie`
> 类型用于只有浏览器登录态的内网网关，支持自动登录与手贴 Cookie。
>
> 新建时可以先选**厂商预设**（如「企业网关（示例）」），它会一次性填好接口地址、认证方式、
> 登录动作（按钮文案、成功跳转、会话 Cookie 名、是否跳过 TLS 校验）与模型名。预设只是初始值，
> 之后所有字段都能改 —— 上游改版时改配置即可，不必等发版。
>
> 内网网关有两个坑要在配置里体现：**接口地址要带路径前缀**（企业网关是
> `https://gw.example.com/agents/gateway`，少一段会落到前端 SPA 上并返回 HTML 200）；
> **自签证书要显式放行**（预设已置 `transport.insecure_tls=true`，等价于关掉该提供商的
> TLS 校验，只应对内网地址使用）。
>
### 企业网关预设（外置）

公开仓库只内置通用厂商预设（OpenAI、DeepSeek 等）。企业内网网关
（自签证书、SSO 登录、私有模型注册表）通过**外部预设插件**接入，
不需要修改仓库代码：

```bash
# 1. 写一个插件文件，导出 PRESETS 列表
mkdir -p /opt/agenticos-internal/presets
cat > /opt/agenticos-internal/presets/enterprise_gateway.py <<'PY'
from app.services.llm_providers.presets import (
    LoginFlow, ProbeSpec, ProviderPreset, TransportOptions,
)

ENTERPRISE_GATEWAY = ProviderPreset(
    slug="enterprise_gateway",
    label="企业网关",
    provider_type="enterprise_cookie",
    base_url="https://<内网网关>/agents/gateway",
    model="<模型名>",
    login_url="https://<内网网关>/login/oauth2/code/ar",
    login=LoginFlow(
        submit_text="授权并登录",
        wait_until="domcontentloaded",
        settle_ms=4_000,
        success_url="**/chat/home",
        required_cookies=("SESSION",),
        cookie_domain="<内网域名>",
        cookie_poll_attempts=30,
        cookie_poll_interval_ms=2_000,
        ignore_https_errors=True,
    ),
    transport=TransportOptions(
        insecure_tls=True,
        browser_user_agent=True,
        extra_body={"enable_thinking": False},
    ),
    probe=ProbeSpec(kind="registry", path="/json/model-configs.json",
                    scope="origin", parser="registry_models"),
    roles={"chat": "<模型名>", "fast": "<模型名>"},
)

PRESETS = [ENTERPRISE_GATEWAY]
PY

# 2. 让 backend 与 worker 都能看到这个目录
export PROVIDER_PRESETS_DIR=/opt/agenticos-internal/presets
```

Docker 部署时把该目录挂进容器并设置环境变量：

```yaml
services:
  backend:
    environment:
      PROVIDER_PRESETS_DIR: /app/internal-presets
    volumes:
      - /opt/agenticos-internal/presets:/app/internal-presets:ro
  worker:
    environment:
      PROVIDER_PRESETS_DIR: /app/internal-presets
    volumes:
      - /opt/agenticos-internal/presets:/app/internal-presets:ro
```

启动日志里会打印 `已加载外部预设：<slug>（<label>）`。
插件加载失败只记 warning，不影响服务启动。

> 内置的格力百通预设（`presets.py` 里的 `GREE_BAITONG`）就是一个完整参照；
> 该机制同样适用于接入其他不改代码就想快速试的内网网关。

> **多账号**：一个 `enterprise_cookie` 提供商下可以挂多个账号分摊配额，流量按
> 「priority 升序、同级内最久未用优先」轮换；连续失败达 3 次的账号自动退出轮换，
> 重新启用即可复位。上游按账号限流的场景强烈建议配 2 个以上。
>
> **模型目录**：点「模型 → 从上游同步」会按提供商配置的探测方式拉清单
> （企业网关常是站点下的静态注册表，而不是 `/models`；后者的 403 通常是「要 admin 权限」，
> 不是认证失败）。同步后可以在「按用途绑定模型」里把对话 / 轻任务 / 深度思考 / 图像理解
> 分别指到不同模型，未绑定的用途自动跟随主模型。
>
> 只有使用 `enterprise_cookie` 类型时才需要浏览器：`agenticos-runtime` 镜像已内置
> Chromium；薄镜像需自行执行 `playwright install --with-deps chromium`，或设
> `PLAYWRIGHT_CHROMIUM_PATH` 指向已存在的 Chromium。手贴 Cookie 不需要浏览器。
>
> 相关开关：`LLM_PROVIDER_FALLBACK_TO_ENV`（默认 `true`，提供商不可用时回落本文件配置；
> 要求「绝不允许流量外溢」的部署请设为 `false`）、
> `LLM_PROVIDER_COOKIE_REFRESH_BUFFER_HOURS`（默认 `2`）、
> `LLM_PROVIDER_COOKIE_DEFAULT_TTL_HOURS`（默认 `24`）、
> `LLM_STREAM_RETRY_ATTEMPTS`（默认 `2`，流式请求的尝试次数；只在尚未输出任何
> 内容时才重试，避免出现「半句话重来一遍」或工具被执行两次。设为 `1` 可关闭）。

可选但推荐：

```env
# 系统通知邮箱（验证码发送、任务完成通知、欢迎邮件）
NOTIFY_EMAIL_ADDRESS=noreply@yourdomain.com
NOTIFY_EMAIL_PASSWORD=your-app-password
NOTIFY_SMTP_HOST=smtp.exmail.qq.com
NOTIFY_SMTP_PORT=465
NOTIFY_SMTP_SSL=true

# 本地嵌入模型（内网 / 不想走远程 /embeddings 时必配；
# 记忆向量召回 + 知识库语义检索都走它，本地推理零 API 成本）
KNOWLEDGE_EMBEDDING_LOCAL_MODEL=BAAI/bge-m3
KNOWLEDGE_EMBEDDING_LOCAL_DIMENSIONS=1024
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

构建产物输出到 `frontend/dist/`，nginx 容器直接挂载该目录
（方式 A）或构建时复制进镜像（方式 B）。

## 4. 启动

### 方式 A：运行时镜像（推荐）

`agenticos-runtime` 镜像只在**有外网的机器**构建一次（pip、apt、Chromium CDN 都需要外网）：

```bash
# 仓库根目录执行
docker build -f deploy/Dockerfile.runtime -t agenticos-runtime:latest .
# 导出给部署机（可选）：docker save agenticos-runtime:latest | gzip > agenticos-runtime.tar.gz
```

部署机上启动（代码目录挂载进容器，更新代码无需重建镜像）：

```bash
cd deploy
docker compose -f docker-compose.runtime.yml up -d
```

内网无外网出口时，直接使用离线包导入现成镜像：
见 [OFFLINE-DEPLOY.md](OFFLINE-DEPLOY.md)。

### 方式 B：薄镜像构建

```bash
cd deploy
docker compose up -d --build
```

基础镜像自动拉取（默认 Docker Hub，可用 `BASE_REGISTRY` 覆盖）：
- `python:3.13-slim`
- `nginx:1.27-alpine`

## 5. 验证服务

```bash
# 后端健康检查
curl http://localhost:10007/api/v1/health/

# 前端页面
curl -I http://localhost:10008/

# worker 正常在跑
docker compose -f docker-compose.runtime.yml logs worker | tail -5
```

浏览器访问 `http://服务器IP:10008` 进入系统，首次注册即管理员。

## 日常更新

### 方式 A（运行时镜像）：只换代码，不重建镜像

```bash
# 同步新的 backend/ 与 frontend/dist 到部署机后：
cd deploy
docker compose -f docker-compose.runtime.yml restart backend worker
```

依赖变了优先走热装（容器根文件系统只读，新依赖装到可写卷 `/app/data/pylibs`，
`PYTHONPATH` 已前置该目录）：

```bash
sh add-deps.sh 'requests==2.32.3' 'pandas>=2.0'
```

### 前端更新

```bash
cd frontend && npm run build
# 方式 A：dist 是挂载的，直接生效（浏览器强刷即可）
# 方式 B：重新构建镜像
cd ../deploy && docker compose up -d --build frontend
```

## 环境变量说明

### 必填

| 变量名 | 说明 |
|--------|------|
| DATABASE_URL | 外部 MySQL 连接字符串（`mysql+pymysql://user:pass@host:3306/agenticos`） |
| REDIS_URL | 外部 Redis 连接地址，如 `redis://redis-host:6379/0`。生产必填（验证码缓存、审批广播、登录限流、任务队列）；留空仅剩内存 fallback，只可单机演示 |
| OPENAI_API_KEY | AI 服务 API Key（管理后台配了「AI 提供商」后仅作兜底） |
| AUTH_SECRET_KEY | JWT 签名密钥（`python -c "import secrets; print(secrets.token_urlsafe(48))"`） |

### 常用可选项

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| REDIS_CLUSTER | false | Redis 是否集群模式 |
| OPENAI_BASE_URL | 空 | AI 服务地址 |
| OPENAI_MODEL | gpt-5.4 | 兜底模型名 |
| AUTH_TOKEN_EXPIRE_MINUTES | 10080 | Token 有效期（分钟） |
| CORS_ALLOW_ORIGINS | http://localhost:3001 | 跨域白名单；同域走 nginx（10008）时设为 `http://<IP>:10008` |
| KNOWLEDGE_EMBEDDING_LOCAL_MODEL | 空 | 本地嵌入模型（如 `BAAI/bge-m3`）；留空走远程 /embeddings |
| KNOWLEDGE_EMBEDDING_LOCAL_DIMENSIONS | 0 | 嵌入维度（bge-m3 为 1024） |
| NOTIFY_EMAIL_ADDRESS / NOTIFY_EMAIL_PASSWORD / NOTIFY_SMTP_HOST / NOTIFY_SMTP_PORT / NOTIFY_SMTP_SSL | 空 | 系统通知邮箱（验证码、任务完成通知） |
| NOTIFY_TASK_MIN_SECONDS | 120 | 任务完成通知阈值（秒） |
| IMAGE_REGISTRY | docker.io | 应用镜像仓库地址（compose image 前缀） |
| BASE_REGISTRY | docker.io | 基础镜像仓库地址（构建时拉 python/nginx，内网可指向私有仓库） |
| PYPI_MIRROR | https://pypi.org/simple | PyPI 镜像源（方式 B 构建时使用） |
| SKILL_STORAGE_DIR | ./data/skills | Skill 存储目录 |
| BACKEND_PORT / FRONTEND_PORT | 10007 / 10008 | 宿主机端口 |

## 数据持久化

宿主机 `data/` 目录整体挂载到容器 `/app/data/`：

- 只读资产：`icons/`、`charts/`、`design-systems/`、`design-themes/`、`layouts/`、
  `skills/`、`website-templates/`
- 运行时产物（应用自动创建）：`uploads/`、`websites/`、`nginx-serve/`（已上线站点，
  nginx 挂载）、`ppt-sessions/`、`documents/`、`knowledge/`、`hf-cache/`（嵌入模型缓存）、
  `pylibs/`（依赖热装目录）、`*_versions/`、`*.db`

## 常用命令

```bash
# 下文以方式 A 为例；方式 B 去掉 -f 参数即可
cd deploy

# 启动
docker compose -f docker-compose.runtime.yml up -d

# 停止 / 重启
docker compose -f docker-compose.runtime.yml down
docker compose -f docker-compose.runtime.yml restart backend worker

# 查看日志
docker compose -f docker-compose.runtime.yml logs -f
docker compose -f docker-compose.runtime.yml logs -f backend   # 只看后端

# 进入容器
docker compose -f docker-compose.runtime.yml exec backend bash
```

## 故障排查

### 启动失败

```bash
docker compose -f docker-compose.runtime.yml logs backend
docker compose -f docker-compose.runtime.yml logs frontend
```

### 数据库连接问题

```bash
docker compose -f docker-compose.runtime.yml exec backend python -c "
from app.db.session import engine
with engine.connect() as conn:
    print('数据库连接成功')
"
```

### Redis 连接问题

```bash
# 先确认外部 Redis 可达
redis-cli -h <Redis主机> -p 6379 ping

# 再看后端自检（应输出「Redis 已连接」；「内存模式」说明 REDIS_URL 没配对）
docker compose -f docker-compose.runtime.yml exec backend python -c "
from app.core.redis import is_redis_memory
print('内存模式' if is_redis_memory() else 'Redis 已连接')
"
```

### 验证码发送失败

检查系统邮箱配置：

```bash
docker compose -f docker-compose.runtime.yml exec backend python -c "
from app.core.config import get_settings
s = get_settings()
print(f'邮箱: {s.notify_email_address}')
print(f'SMTP: {s.notify_smtp_host}:{s.notify_smtp_port}')
print('配置完整' if s.notify_email_address and s.notify_smtp_host else '配置缺失')
"
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
3. **Redis**：外部 Redis 配置密码认证，限制来源 IP
4. **密钥管理**：`AUTH_SECRET_KEY`、`OPENAI_API_KEY`、`NOTIFY_EMAIL_PASSWORD` 通过 secrets 管理
5. **日志轮转**：配置 Docker 日志 driver 限制日志大小
6. **监控**：后端健康检查 `GET /api/v1/health/`，接告警

---

## OpenAI 兼容接口（把 AgenticOS 接入现有系统）

系统对外暴露标准的 OpenAI Chat Completions 协议，企业的网关、Dify、内部平台
或任意脚本都能直接接入，无需了解 AgenticOS 私有协议。

### 端点

| 路径 | 说明 |
|---|---|
| `GET /v1/models` | 列出当前可用的智能体（作为 `model` 名） |
| `POST /v1/chat/completions` | 对话补全，支持 `stream: true` |

### 鉴权

使用「企业上游」模块里的 API Key（`sk-agenticos-*`），与站内登录是两套密钥：

```bash
# 1) 在管理后台 → 企业上游 创建 API Key，复制明文（仅创建时可见一次）

# 2) 调用
curl http://<host>/v1/chat/completions \
  -H "Authorization: Bearer sk-agenticos-xxxx" \
  -H "Content-Type: application/json" \
  -d '{
        "model": "general",
        "messages": [{"role": "user", "content": "总结上周的工单"}]
      }'
```

用 OpenAI SDK 时只需改 `base_url`：

```python
from openai import OpenAI

client = OpenAI(base_url="http://<host>/v1", api_key="sk-agenticos-xxxx")
resp = client.chat.completions.create(
    model="general",                       # 也可以用 gpt-4o 这类别名
    messages=[{"role": "user", "content": "总结上周的工单"}],
)
print(resp.choices[0].message.content)
```

### 路由规则

`model` 字段决定走哪条链路：

- 命中**本地智能体**（已安装的 slug / 名称）或 **AgenticOS 模式名**
  （`general` / `ppt` / `website` / `email` / `bigdata` / `office`）或通用别名
  （`gpt-4o` 等）→ 由 AgenticOS 本地 Agent 执行（可用知识库、工具、审批等全部能力）
- 其他 `model` 名 → 透传给企业上游（gw.example.com），保持既有行为

### AgenticOS 扩展参数

请求体里可额外传（标准 OpenAI 客户端会忽略未知字段）：

| 字段 | 取值 | 说明 |
|---|---|---|
| `session_id` | string | 复用会话上下文，实现多轮对话 |
| `approval_mode` | `ask` / `auto` / `full` | 工具审批档位，默认 `ask` |
| `plan_mode` | bool | 计划模式：只读调研并输出计划，批准后再执行 |
