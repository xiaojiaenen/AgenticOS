# M6 完整设计与落地方案

> 2026-09-30 · 承接 docs/development-plan-v2.md 第六部分 · 目标：支撑 500 并发在线 / 100 并发 SSE / 企业级权限
> 本文档既是设计稿也是实施清单，三条实施线并行推进：性能优化、部署拆分、权限体系。

---

## 一、容量模型与性能预算

### 1.1 目标 SLO

| 指标 | 目标 | 测量口径 |
|---|---|---|
| 并发在线用户 | 500 | 30s 窗口内有心跳的活跃会话 |
| 并发 SSE 流式会话 | 100 | 同时进行的 /agent/stream 长连接 |
| 聊天首字延迟 P95 | < 2s（不含模型首 token 时间） | 服务端收到请求 → 首个 delta 事件 |
| 普通 API P95 | < 300ms | 排除 SSE 与 LLM 调用 |
| 知识库检索 P95 | < 50ms | BM25 + 向量融合 |
| 错误率 | < 0.5% | 5xx 占比 |
| LLM 上游并发 | 全局 ≤ 60（可配） | 跨实例共享信号量 |

### 1.2 资源估算（单实例 core-api，2C/4G）

- 100 条 SSE 长连接：每条常驻 ~200KB（buffer + Python 对象）→ ~50MB，连接文件描述符 100，**瓶颈是 FD 与 worker 数而非内存**
- 500 在线用户的轮询类 API：QPS 约 30-50，uvicorn 单 worker 可承载
- 结论：**core-api 2 实例 × 2 worker，agent-service 2 实例 × 4 worker** 起步（agent 单次运行 CPU 吃 LLM 解析与工具编排）

### 1.3 压测规范（locust）

场景三档，脚本在 `backend/loadtest/`：
1. `smoke`（1 用户/1min）：CI 冒烟，压连接建立与鉴权
2. `standard`（50 用户/10min）：登录 → 建会话 → 短消息（LLM mock）→ 拉历史 → 管理页查询
3. `target`（500 用户/30min，100 独立 SSE）：验证 SLO

- LLM 调用在压测环境用 **mock 模式**（配置项 `LLM_MOCK_ENABLED`，压测专用 env），不打真实模型、不产生费用
- 产出 `backend/loadtest/baseline.md`：M6 基线数据与压测命令，变更后可复跑对比

---

## 二、性能优化清单（实施线 A）

| # | 项 | 落点 | 说明 |
|---|---|---|---|
| **B 线** | **部署单元拆分 + 蓝绿脚本** | **2026-09-30 决定暂缓** | compose 保持单 backend 现状；本文档第三节的拓扑/脚本/文档待单实例性能数据出来、确认伸缩墙位置后再启动。本轮不实施。 |
| A1 | 连接池分级配置 | `db/session.py` | `pool_size=10, max_overflow=20, pool_recycle=1800`；新增 settings 项 `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` 走 env |
| A2 | SSE 期间短会话轮询降频 | `agent/orchestrator.py` | 持久化批量化（已有 batch 接口则扩大批量），审批轮询已有队列推送，DB 写入合并到流结束 |
| A3 | 复合索引迁移 | alembic `0004` | `agent_usage_events(user_id, created_at)`、`(session_id, created_at)`、`agent_messages(session_id, id)`、`agent_sessions(user_id, updated_at)`；MySQL/SQLite 双方言幂等 |
| A4 | dashboard 统计缓存 | `endpoints/dashboard.py` | `/stats`、`/analytics` 30s Redis 缓存（cache_service 现有封装），用户维度 key 隔离 |
| A5 | LLM 全局并发信号量 | 新 `services/llm_gate.py` | 跨实例共享计数（Redis INCR + TTL 租约），超时排队上限；释放可靠（finally）；与 memory_pipeline 已有信号量并存不冲突 |
| A6 | 知识库 wiki 内存缓存 | `knowledge/retrieval.py` | 全量评分路径（SQLite/dev）加进程内缓存 + 写入失效钩子 |
| A7 | 长消息列表虚拟化 | 前端 M4 已装 react-virtuoso | MessagesList 未接的改接虚拟化（长会话 >200 消息） |
| A8 | 压测脚本与基线 | `backend/loadtest/` | locust 三档场景 + mock LLM 开关 + baseline.md |

## 三、部署单元拆分（实施线 B）

```
nginx (:80)
├── /api/agent/stream  → agent-service ×2   (SSE 长连接，CPU/FD 敏感，独立扩缩)
├── /api/*             → core-api ×2        (普通 API，IO 密集)
└── /                  → frontend 静态
Redis（会话/审批/队列/缓存）  MySQL（主）  arq worker 池 ×3（web 重任务 / notify 轻任务 / default）
```

- `docker-compose.yml` 重构：`core-api`、`agent-service` 两个 api 服务复用同一镜像与同一 env anchor（沿用 M0 的 anchor 模式），nginx 按路径分流并为 SSE 关闭 proxy_buffering
- arq 分池：web 池单独部署（npm build 内存大）、notify/default 合并轻池
- **无状态确认清单**（拆分前置条件，逐项验证并在文档记录）：会话/审批/在线用户状态全在 Redis ✓；agent TTLCache 跨实例不共享可接受 ✓；memory_pipeline 计数字典仅影响单实例轮次节奏（可接受）✓
- 蓝绿部署脚本 `deploy/bluegreen.sh`：起 green → healthcheck → 切 nginx upstream → 观察 5 分钟 → 停 blue
- CI 不变（构建镜像加 tag 规范：`{registry}/agenticos-{core-api|agent-service|frontend}:{git-sha}`）

## 四、企业权限体系（实施线 C）

> **现状更新（2026-10-27）**：产品侧确认不需要「部门」这一层，4.2 的部门树、
> `dept_admin` 角色与 `dept:<id>` 授权域已整体下线（迁移 `0010_drop_departments`
> 删除了 `departments` 表与 `users.department_id`）。当前授权模型为
> **用户 → 角色 → Casbin 策略**，所有策略落在 `global` 域，只保留 `admin` /
> `user` 两个内置角色 + 自定义角色。下文 4.2 仅作历史设计留档。

### 4.1 权限模型（Casbin）

- **角色**：`admin`（全权）、`user`（本人会话 + 被授权资源）；角色可自定义（`roles` 表）
- **资源**：知识库（kb）、Agent Profile 发布、Skill、Memory（按用户）、外部系统凭据（仅 admin）、公告、成员管理
- **策略存储**：MySQL `casbin_rule` 表（policy, ptype），模型定义 `backend/app/resources/casbin_model.conf`（RBAC + 域/部门 key）
- **关键策略示例**：
  - `p, auditor, *, kb:12, read`（角色 auditor 可读知识库 12）
  - `p, user:7, *, kb:3, write`（用户 7 直接授权写知识库 3）
  - 知识库行级过滤：`require_kb_access(kb_id, "read")` → service 层统一注入过滤（禁止端点各自手写）
- **接入点**：`api/deps.py` 新增 `require_permission(action, resource_resolver)`；保留 `require_admin` 兼容

### 4.2 部门树（已下线，历史设计留档）

- `departments` 表（id, name, parent_id, path, ldap_dn）；用户表加 `department_id` 外键
- LDAP 同步任务（扩 `ldap_auth_service.py`）：登录时按需同步本人部门 + 管理员手动触发全量同步
- 部门树查询用 `path` 物化路径（避免递归查询）

### 4.3 审计日志

- `audit_logs` 表：actor、action（`resource.action` 字符串枚举）、resource_type、resource_id、result（allow/deny/error）、ip、user_agent、detail(JSON)、created_at；索引 (actor_id, created_at)、(resource_type, resource_id, created_at)
- 覆盖范围：登录/登出、审批决策、管理员 CRUD（用户/角色/知识库/Agent/Skill/外部系统）、权限变更、知识库读写（create/update/delete，不含普通检索）
- 写入：service 层 `audit_service.record(...)`（同步异步双写：入队 + 关键操作同步落库）；复用 arq 队列
- 保留策略：180 天，清理任务进 worker

### 4.4 SSO 与密钥

- OIDC 接入（Authlib）：`OIDC_ENABLED/OIDC_ISSUER/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET`，回调发本系统 JWT，逻辑复用现有 LDAP 登录路径（`auth_service`）
- 密钥收敛：ENVIRONMENT=production 时 `AUTH_SECRET_KEY` 与 `EXTERNAL_SYSTEM_ENCRYPTION_KEY` 必填校验（留空则启动失败，不再静默派生），compose 提示改用 docker secrets

## 五、验收与里程碑

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| M6-A | A1~A8 性能优化 | standard 压测 P95 达标；baseline.md 有前后对比 |
| M6-B | 部署拆分 | compose 起全栈健康；蓝绿脚本演练一次；SSE 100 并发通过 |
| M6-C | 权限体系 | 权限矩阵用例全过（新增 test_permissions.py）；审计事件覆盖抽查通过；生产密钥必填校验生效 |

回滚策略：A/C 为代码级可 revert（单提交粒度）；B 部署拆分保留旧 compose 文件 backup 入口（`docker-compose.legacy.yml` 一周后删）。

## 六、风险

1. 拆分后 SSE 跨实例：审批/决策经 Redis 广播已支持；新增**长会话粘性**（nginx ip_hash 或 session_id 参数）非必须，仅记录
2. LLM 信号量跨实例用 Redis 租约，Redis 抖动时退化为本地信号量（保可用不保精确）
3. Casbin 首次全量授权需要一次性数据迁移脚本（现有 admin/user 映射到策略表）
4. 审计量增长快，1 年后需分区表或冷备
