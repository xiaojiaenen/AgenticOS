# AgenticOS 内网离线部署手册

> 面向**完全内网（无外网出口）**部署。外部 MySQL / 外部 Redis 已就绪的形态。
>
> 核心结论：**只有镜像构建需要外网**（pip / apt / npm / playwright / 模型下载）。
> 运行期零外网：嵌入模型本地推理、代码 volume 挂载、数据库与缓存都是外部服务。

---

## 零、部署形态总览

```
内网部署机（只跑容器）             外部既有服务（你的现成基础设施）
┌────────────────────────┐        ┌──────────────────────────┐
│ agenticos-backend :8000│───────▶│ MySQL 8   (DATABASE_URL) │
│ agenticos-worker       │───────▶│ Redis     (REDIS_URL)    │
│ agenticos-frontend :80 │        └──────────────────────────┘
└────────────────────────┘
        ▲
        │ 只挂载代码 / dist / data，不跑数据库不跑缓存
```

**不需要带 Redis Stack**：记忆向量检索已改为进程内余弦（embedder + 本地模型），
不再依赖 RediSearch 的 `FT.SEARCH`。普通 Redis 只承担缓存/队列/限流，够用。

---

## 一、准备离线包（在有外网的构建机执行）

```bash
# 1. 前端构建（产物进包，内网不再 npm install）
cd frontend && npm install && npm run build && cd ..

# 2. 构建运行时镜像（唯一需要外网的一步：pip / apt / npm / playwright）
docker build -f deploy/Dockerfile.runtime -t agenticos-runtime:latest .

# 3. 导出镜像（约 8GB，压缩后 3GB 左右）
docker save agenticos-runtime:latest | gzip > agenticos-runtime.tar.gz

# 4. 打包代码 + 静态资源 + 嵌入模型
tar -czf agenticos-code.tar.gz \
  backend/app backend/alembic backend/alembic.ini backend/main.py backend/pyproject.toml \
  frontend/dist deploy data/charts data/design-systems data/design-themes \
  data/layouts data/skills data/website-templates data/icons data/hf-cache
```

> 用 `deploy/package-intranet.ps1`（Windows）或上面命令（Linux）都行，产物一致。
> 嵌入模型已在 `data/hf-cache` 里（BAAI/bge-m3，1024 维，见第四节）。

把 `agenticos-runtime.tar.gz` + `agenticos-code.tar.gz` 用 U 盘/内网传输拷过去。

---

## 二、内网部署机执行

```bash
# 1. 导入镜像（一次性，之后更新只换代码）
gunzip -c agenticos-runtime.tar.gz | docker load

# 2. 解包到固定目录（代码挂载点，之后更新只覆盖这个目录）
mkdir -p /opt/agenticos && tar -xzf agenticos-code.tar.gz -C /opt/agenticos
cd /opt/agenticos

# 3. 配置环境变量
cp deploy/.env.example deploy/.env
vi deploy/.env      # 按第三节填写

# 4. 起服务
cd deploy
docker compose -f docker-compose.runtime.yml up -d
```

---

## 三、`.env` 必填项（外部 MySQL / Redis 形态）

```bash
# ── 数据库（外部既有 MySQL）──
DATABASE_URL=mysql+pymysql://agenticos:<密码>@<MySQL主机>:3306/agenticos

# ── Redis（外部既有 Redis）──
REDIS_URL=redis://<Redis主机>:6379/0
REDIS_CLUSTER=false

# ── 认证 ──
AUTH_SECRET_KEY=<openssl rand -hex 32>
EXTERNAL_SYSTEM_ENCRYPTION_KEY=<openssl rand -hex 32>   # 与 AUTH_SECRET_KEY 分开

# ── LLM（内网模型网关；配了「AI 提供商」后此项仅作兜底）──
OPENAI_API_KEY=<内网网关 key 或占位>
OPENAI_BASE_URL=http://<内网模型网关>/v1
OPENAI_MODEL=<模型名>

# ── 前端访问地址（跨域与邮件链接用）──
CORS_ALLOW_ORIGINS=http://<部署机IP>:10008

# ── 本地嵌入模型（关键：内网必须走本地，不能留空）──
KNOWLEDGE_EMBEDDING_LOCAL_MODEL=BAAI/bge-m3
KNOWLEDGE_EMBEDDING_LOCAL_DIMENSIONS=1024
HF_HOME=/app/data/hf-cache
HF_ENDPOINT=                       # 内网无外网：留空，配合下方离线开关

# ── 端口 ──
BACKEND_PORT=10007
FRONTEND_PORT=10008
```

**离线开关（重要）**：容器内已缓存模型，但 sentence-transformers 启动时仍会尝试
探测 HuggingFace。在 `docker-compose.runtime.yml` 的 `x-backend-env` 里加两行彻底断掉：

```yaml
  HF_HUB_OFFLINE: "1"
  TRANSFORMERS_OFFLINE: "1"
```

---

## 四、数据库初始化

外部 MySQL 里先建库建号（`utf8mb4` 必须，否则中文与 emoji 会写失败）：

```sql
CREATE DATABASE agenticos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'agenticos'@'%' IDENTIFIED BY '<密码>';
GRANT ALL PRIVILEGES ON agenticos.* TO 'agenticos'@'%';
FLUSH PRIVILEGES;
```

建表由应用自动完成（启动时 `create_all` + 兼容层补列），**迁移脚本也会自动跑**到最新。
首次启动后确认版本：

```bash
docker exec agenticos-backend-1 python -m alembic current   # 应显示最新 head
```

---

## 五、嵌入模型：bge-m3（1024 维，多语言，效果优于 bge-small-zh）

| 项 | bge-small-zh-v1.5 | **bge-m3** |
|---|---|---|
| 维度 | 512 | **1024** |
| 中文效果 | 好 | **更好（且支持中英混排、长文本 8k）** |
| 体积 | 100MB | 约 1.2GB |
| 内存占用 | ~300MB | ~1.5GB（CPU 推理） |
| 单条编码耗时 | ~20ms | ~60-120ms（CPU） |

**部署要点**：
1. 模型文件随包带（`data/hf-cache`），内网不需下载；
2. 维度从 512 换到 1024 后，**旧向量索引必须重建** —— 代码里 `_ensure_index`
   检测到维度不符会自动 DROP 并清空旧向量（日志会打 `dim mismatch`），
   随后记忆的向量通道需要重新回填（见下）；
3. 首次启动会加载模型（约 10-30 秒），健康检查的 `start_period: 40s` 已覆盖。

**切换后回填记忆向量**（一次性，让已有记忆能被语义检索到）：

```bash
docker exec agenticos-backend-1 python - <<'PY'
import asyncio, sys
sys.path.insert(0, "/app/backend")
from sqlalchemy import select
from app.db.session import create_db_session
from app.db.models import MemoryModel
from app.services.memory_pipeline import MemoryPipeline
from app.core.config import get_settings
from app.core.redis import _manager

async def main():
    s = get_settings()
    await _manager.init(s.redis_url, s.redis_cluster)
    def fetch():
        with create_db_session() as db:
            return db.scalars(select(MemoryModel).where(MemoryModel.layer == "L1").limit(500)).all()
    rows = await asyncio.to_thread(fetch)
    pipe = MemoryPipeline()
    done = 0
    for row in rows:
        try:
            await pipe._embed_and_upsert(row.id, "atom", row.user_id, "L1", row.content)
            done += 1
        except Exception:
            pass
    print("backfilled", done, "/", len(rows))

asyncio.run(main())
PY
```

> 若内存紧张（< 4GB 可用），可退回 `BAAI/bge-base-zh-v1.5`（768 维，400MB，
> 中文效果好且轻），只需把上面 `.env` 两行换成该模型名与 `768`。

---

## 六、验证

```bash
# 后端健康
curl http://127.0.0.1:10007/api/v1/health/          # {"status":"ok",...}

# 前端
curl -I http://127.0.0.1:10008/                     # 200

# 嵌入模型是否真的在本地跑（看日志，不该有 HF 联网报错）
docker logs agenticos-backend-1 2>&1 | grep -iE "local embedding model ready|dim mismatch"

# Redis 连通（应无 fallback 到内存）
docker logs agenticos-backend-1 2>&1 | grep -i "Redis 连接"

# 登录页应能打开
curl -s http://127.0.0.1:10007/api/v1/auth/login-mode   # {"mode":"local"...} 或 ldap
```

首次登录后进入 **管理后台**：
1. `AI 提供商`：新建内网模型网关（或百通），设为默认，测试连通；
2. `系统设置 → LDAP`：填服务器/DN/过滤器，开 `email_auto_configure` 与 imap/smtp；
3. `记忆管理`：如从旧环境迁移过数据，点「清理重复记忆」。

---

## 七、日常更新（代码变更，不重建镜像）

```bash
# 构建机上打代码包（不含镜像）
tar -czf agenticos-code.tar.gz backend/app frontend/dist data/...
# 内网机
tar -xzf agenticos-code.tar.gz -C /opt/agenticos
cd /opt/agenticos/deploy && docker compose -f docker-compose.runtime.yml restart backend worker
```

依赖变化（`pyproject.toml` 改了）才需要重新构建镜像并重传 tar.gz。

---

## 八、已知边界

| 项 | 说明 |
|---|---|
| PPT 配图 | `search_images` 走 Pexels/Pixabay（外网）。内网请在工具配置里关掉该工具，PPT 其余功能不受影响 |
| 网站智能体 | 需要容器内 npm；镜像已装 node/npm，但 `npm install` 依赖外网 registry —— 内网需配私有 npm 源或改用预装依赖的模板 |
| 企业网关自动登录 | 走 `agents.gree.com`（内网 SSO），与是否断外网无关；Playwright + Chromium 已内置镜像 |
| 系统通知邮件 | 需要 SMTP 可达（内网邮件服务器或 Coremail） |
| 模型下载 | 内网无 HF 出口，**必须随包带模型**；`.env` 的 `HF_ENDPOINT` 留空并设离线开关 |
