# 只读 rootfs 下安装新依赖

## 特别篇：任务队列已迁移到 taskiq（原生支持 Redis Cluster）★

### 结论先行

**队列不再需要单独的单节点 Redis。** `REDIS_URL` 可以是完整的集群地址，
队列和业务缓存共用同一个集群。

### 为什么换掉 arq

arq 0.28 的 `ArqRedis` 是普通 `redis.asyncio.Redis`：

- 直连 cluster 的任何一个节点 → key 不归它管就 `MOVED`；
- `RedisCluster.pipeline(transaction=True)` 在 redis-py 里**无条件抛异常**
  （"transaction is deprecated in cluster mode"），与 key 是否同槽无关；
- arq 消费端认领任务重度依赖 `MULTI/EXEC` → 集群上无解。

**内网 6 节点集群实测**：用 arq 的方式写 30 个 key，**15 个抛 `MovedError`**。

### taskiq 为什么可以

`taskiq-redis` 提供原生 cluster 类，实现上**完全不用事务、不跨 slot**：

| 类 | 命令 | cluster 安全 |
|---|---|---|
| `RedisStreamClusterBroker` | `xadd` / `xreadgroup` / `xack` | 单流，带 ACK |
| `RedisAsyncClusterResultBackend` | `get` / `set` | 单 key |
| `RedisClusterScheduleSource` | `scan_iter` / `get` | scan 跨节点 |

**同一集群实测**：投递 → worker 消费 → 取结果，4/4 全对。
node1 真实 Redis 上也验证通过。

### 配置（现在很简单）

```bash
# 集群：直接填多节点，不需要单独给队列一个 Redis
REDIS_URL=redis://default:<密码>@172.73.1.87:6379,redis://default:<密码>@172.73.1.88:6379,...
REDIS_CLUSTER=true
# 可选：想把队列和业务缓存分开时再配（不配就复用 REDIS_URL）
# ARQ_REDIS_URL=redis://default:<密码>@<host>:6379/0
```

单机部署照旧：`REDIS_URL=redis://redis:6379/0`、`REDIS_CLUSTER=false`。

### 部署变化

1. **worker 启动命令变了**：`arq app.services.task_queue.WorkerSettings`
   → `taskiq worker app.services.task_queue:taskiq_broker --workers 2`
   （compose 已改，`docker-compose.offline.yml` / `runtime.yml` 都更新了）
2. **新增 `scheduler` 服务**：arq 的 cron 由 worker 自己跑，taskiq 需要独立进程
   `taskiq scheduler app.services.task_queue:taskiq_scheduler`
3. **cron 需要种子**：部署后跑一次
   `docker exec agenticos-scheduler-1 python -m app.services.task_queue_seed`
   （幂等，重复跑安全；scheduler 会从 Redis 读 cron 并投递）
4. **新依赖**：`taskiq>=0.13.0` + `taskiq-redis>=1.2.4`（会把 `redis` 升到 8.x）

### 升级 redis 5→8 的风险

已核对：项目只在 `core/redis.py` 用 `from_url` / `pubsub` / `aclose` /
`RedisCluster`，这些 API 在 5→8 之间未变，全量测试 1151 passed。

### 已知限制

- `memory_vector_store` 在 cluster 下仍降级（代码里显式判断并 warning），
  与队列无关，是「向量需要单独 binary client」的历史限制。
- taskiq 的 schedule source 用 `scan_iter` 遍历 cron 定义，cron 数量少，
  性能无影响。

---

## 先说结论（依赖安装部分）

### 现在不用手写包名了：`sync-deps.sh`

```bash
cd /opt/agenticos/deploy
sh sync-deps.sh              # 按 pyproject.toml 自动补齐差异
sh sync-deps.sh --dry-run    # 只看差异，不安装
sh sync-deps.sh --all        # 忽略对比，全量重装
```

它做的事：读**包内** `backend/pyproject.toml` 的 `[project].dependencies` →
把清单通过 stdin 送进 backend 容器 → 用容器自带的 `packaging` 逐条判断
「已装版本是否满足声明」→ 只把不满足的交给 `add-deps.sh` 装 → 重启
backend / worker / scheduler。

**升级流程因此变成**：同步代码（含新 `pyproject.toml`）→ `sh sync-deps.sh` → 完事。
不需要记住这次又加了哪个包。

在 node1 实测：检出 `wuwei>=3.3.1` 未满足 → 自动装好 → 再次 dry-run 显示
「✔ 全部依赖已满足」。

> 注意：比对用的是**容器内 `/app/backend/pyproject.toml`**（挂载卷，即你刚同步
> 的那份）。如果还没同步代码就跑 `sync-deps.sh`，比的是旧清单 —— 所以顺序
> 必须是「先 rsync 代码，再 sync-deps」。

### 原始做法（需要单装某个包时）

本轮改动（邮件模板、预览面板、审批链、email-design skill）**只用到项目已有的库**
（fastapi / pydantic / sqlalchemy / wuwei / cachetools 等）和 Python 标准库，
没有引入任何新的第三方包。前端依赖已经 build 进 `frontend/dist/`。

`pyproject.toml` 相对上一个包只有一处变化：`wuwei>=3.3.0` → `wuwei>=3.3.1`
（上一轮升级时的改动）。**只要镜像里的 wuwei ≥ 3.3.1，直接同步代码 + 重启即可。**

先查一下版本，别急着装：

```bash
docker exec <backend容器名> python -c 'import wuwei; print(wuwei.__version__, wuwei.__file__)'
# 或
sh add-deps.sh --check wuwei
```

- 版本 ≥ 3.3.1 → **什么都不用做**
- 版本 3.3.0（或更低）→ 按下面升级 wuwei
- 报 ModuleNotFoundError → 按下面装

---

## 为什么不能直接在容器里 pip install

`docker-compose.offline.yml` 里 backend 是：

```yaml
read_only: true                      # 根文件系统只读
tmpfs: [/tmp, /var/tmp]              # 重启就丢，不能装这儿
volumes:
  - ../backend:/app/backend         # 代码
  - ../data:/app/data               # ★ 唯一可写、且持久化的挂卷
environment:
  PYTHONPATH: /app/data/pylibs:/app/backend   # ★ 预留的依赖覆盖目录
```

`pip install` 默认写 `/usr/local/lib/python3.13/site-packages` → 只读，直接失败。
就算 `pip install --user` 到 `/root` 或装到 `/tmp`，重启也没了。

**项目已经预留了正解**：把包装到 `/app/data/pylibs`（可写挂卷），
PYTHONPATH 前置让 Python 优先从这里加载。backend 和 worker 共享同一
`/app/data` 卷，**装一次两个容器都生效**。

---

## 方案 A：内网有 PyPI 镜像

`add-deps.sh` 已在 `deploy/` 里：

```bash
cd /opt/agenticos/deploy
docker ps --format '{{.Names}}'          # 确认容器实际名，通常带项目前缀

# 默认容器名 agenticos-backend-1；不同就用 CONTAINER=xxx 指定
sh add-deps.sh 'wuwei==3.3.1'
# 或
CONTAINER=agenticos-backend-1 PYPI_MIRROR=http://<内网pypi>/simple \
    sh add-deps.sh 'wuwei==3.3.1'
```

脚本做三件事：`pip install --target=/app/data/pylibs --no-deps --upgrade` →
`docker compose restart backend worker` → 打印验证命令。

`--no-deps` 是刻意的：镜像里已有全部传递依赖，重复装进 pylibs 会被
PYTHONPATH 前置加载，反而可能引发版本冲突。若新依赖确实引入了镜像里
**没有**的传递依赖，加 `--with-deps`。

---

## 方案 B：完全离线（无 PyPI 镜像）★ 内网最常见

**1. 在有网的机器上下载 wheel**（Python 3.13 / linux / x86_64 要匹配镜像）

```bash
pip download --only-binary=:all: --python-version 3.13 \
    --platform manylinux2014_x86_64 --implementation cp \
    -d ./wheels 'wuwei==3.3.1'
# 若 wuwei 不是纯 py3 wheel 或有平台相关依赖，直接在同版本 python:3.13-slim
# 容器里 pip download 最稳妥
```

**2. 把 wheel 拷到部署机**（U 盘 / 内网传输）

```bash
mkdir -p /opt/agenticos/data/wheels
cp ./wheels/*.whl /opt/agenticos/data/wheels/
```

**3. 离线安装**

```bash
cd /opt/agenticos/deploy
sh add-deps.sh --offline 'wuwei==3.3.1'
# 或装 wheels/ 下全部：
sh add-deps.sh --offline
```

对应容器内执行的是：

```bash
pip install --no-index --find-links=/app/data/wheels \
    --target=/app/data/pylibs --upgrade --no-deps 'wuwei==3.3.1'
```

全程**不联网、不写 rootfs**。

**4. 验证**

```bash
sh add-deps.sh --check wuwei
# 应显示 path: /app/data/pylibs/wuwei/__init__.py
```

---

## 方案 C：重建镜像（彻底，但重 3.9GB，非必要不推荐）

只在要长期固化依赖、或改了系统 apt 包时才做。在**有网的构建机**上：

```bash
docker build -f deploy/Dockerfile.offline \
  --build-arg PYPI_MIRROR=http://<内网pypi>/simple \
  -t agenticos-runtime:latest .
docker save agenticos-runtime:latest -o agenticos-runtime.tar
# 拷到内网 → docker load -i agenticos-runtime.tar
```

注意 `pull_policy: never`，重建后要保持镜像 tag 为 `agenticos-runtime:latest`。

---

## 坑位清单

| 坑 | 说明 |
|---|---|
| 直接 `docker exec ... pip install xxx` | rootfs 只读，写 site-packages 必然失败 |
| 装到 `/tmp` 或 `/root` | tmpfs / 非持久层，容器重启即丢 |
| 忘了 `PYTHONPATH` 前置 | 装了也不生效，仍加载镜像里的旧版 |
| 不加 `--no-deps` | 依赖被重复装进 pylibs，PYTHONPATH 前置后可能版本冲突 |
| 装完不 restart | Python 进程已加载旧模块，必须重启 backend + worker |
| worker 没重启 | worker 是独立容器，共享卷但要各自重启 |
| 用 `up -d --force-recreate` 代替 restart | 也行，但会重建容器、更慢；`restart` 足够 |
| wuwei 降到 3.3.0 | `wuwei_patches.py` 与适配器已按 3.3.1 签名对齐，混用会崩 |

---

## 附：本次部署的完整顺序

```bash
cd /opt/agenticos/deploy

# 1. 同步代码（前后端 + skill）
rsync -a --delete --exclude='__pycache__' "$PKG/backend/" /opt/agenticos/backend/
rsync -a --delete "$PKG/frontend/dist/"  /opt/agenticos/frontend/dist/
rsync -a --delete "$PKG/data/skills/email-design/" /opt/agenticos/data/skills/email-design/

# 2. 只有 wuwei < 3.3.1 时才需要（见方案 A / B）
#    sh add-deps.sh --check wuwei
#    sh add-deps.sh --offline 'wuwei==3.3.1'

# 3. 重启
docker compose -f docker-compose.offline.yml up -d --force-recreate backend worker
#    若上一步用了 add-deps.sh，它已经自动 restart 过，这步可省

# 4. 验证
curl -s http://127.0.0.1:10007/api/v1/health/
docker exec <backend容器名> sh -c 'cd /app && python -c "import app.main; print(\"import ok\")"'
```
