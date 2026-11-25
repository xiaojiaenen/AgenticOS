# 数据库选型评估：要不要从 MySQL 换到 PostgreSQL

> 评估日期：2026-11-17。基于当前仓库代码排查 + 2026 年主流实践调研。
> 结论先行见第 1 节，只看结论可跳到第 7 节的建议。

---

## 1. 结论先行

**首先纠正一个前提：项目当前「默认跑的是 SQLite，不是 MySQL」。**

- `backend/app/core/config.py:77`：`database_url` 默认值是 `sqlite:///{PROJECT_ROOT}/data/agenticos.db`；
- `backend/.env.example:36`：示例配置也是 SQLite；
- `pymysql` 只是列在依赖里，供**需要时**切到 MySQL 部署（生产可用，但非默认）。

所以"要不要把 MySQL 换成 PG"这个问题，实际要拆成两个：

1. **开发环境**：SQLite（零运维、够用）→ 是否要统一成 PG？
2. **生产环境**：可选 MySQL → 是否改成 PG？

**我的建议：方向认同 PG，但不建议现在大动，更不建议一刀切迁移。**

- **该做**：把 PostgreSQL 确立为**生产环境的推荐/默认选项**，新增能力优先按 PG 设计（尤其向量检索）；开发继续用 SQLite。
- **不该做**：立刻把已有 MySQL 生产库物理迁移到 PG。收益主要是"未来少折腾"，而当前代码对 MySQL 的耦合其实很浅，迁移的工程价值没有被网上的通用论调放大得那么大。
- **触发迁移的时机**：当知识库向量检索要上规模（千万级）、或明确需要 JSONB 索引查询 / 复杂分析查询时，再迁——那时候 PG + pgvector 的收益才真正兑现。

一句话：**把 PG 定为"生产推荐 + 未来默认"，但保留 SQLite/MySQL，按收益拐点渐进迁移，不要现在花大代价做纯换库。**

---

## 2. 当前数据库使用现状（代码事实）

### 2.1 抽象层做得比较干净

- ORM：SQLAlchemy 2.0（Mapped / mapped_column）+ Alembic 28 个迁移脚本。
- `backend/app/db/session.py`：`_create_engine()` 只按 `is_sqlite` 分支——SQLite 加 WAL/超时，非 SQLite 统一走通用连接池（`pool_pre_ping` / `pool_recycle` / `pool_size` / `max_overflow`）。**这套参数对 PG 同样适用，无需改代码。**
- 迁移脚本普遍做了方言判断（`bind.dialect.name == "mysql" / "sqlite"`），多数是幂等的（先 `sa.inspect()` 再操作）。

### 2.2 字段类型：几乎没有绑死 MySQL

`backend/app/db/models.py` 里的"JSON 字段"几乎全部用通用 `Text` 存 JSON 字符串（`metadata_json`、`config_json`、`args_json`、`message_json` 等），而不是 MySQL 的 `JSON` 类型：

- 好处：不依赖任何数据库的 JSON 实现，换 PG 零成本；
- 代价：也没享受到 PG `JSONB` 的索引与查询能力（这是"迁移收益"而非"迁移障碍"）。

真正用到 MySQL 专有类型的只有一处：`Text().with_variant(LONGTEXT, "mysql")`（`message_json`、`deck_json`，见 2.3）。

### 2.3 与 MySQL 耦合的三处（迁移要改的点）

| 位置 | 耦合内容 | 迁 PG 的处理 |
|------|----------|--------------|
| `models.py:387,414` | `Text().with_variant(LONGTEXT, "mysql")` | PG 的 `Text` 本身无长度上限，去掉 variant 即可 |
| 迁移 `0002_mysql_longtext.py` | 仅 MySQL 执行，把两列改 `LONGTEXT` | 新库不需要；历史脚本保留即可（对 PG no-op） |
| 迁移 `0003_kb_fulltext_ngram.py` | 仅 MySQL 执行，建 `FULLTEXT ... WITH PARSER ngram` 中文分词索引 | **这是唯一有实质工作量的点**，见下节 |

### 2.4 知识库检索是最大的耦合点

`backend/app/services/knowledge/retrieval.py` 的 BM25 检索是**双路径设计**：

- `_is_mysql()` 探测方言：`mysql` → 走 `_bm25_search_mysql()`（数据库内 `MATCH AGAINST ... IN NATURAL LANGUAGE MODE`，ngram 分词、BM25 权重由数据库算）；
- 其他（SQLite/开发）→ `_bm25_search_python()`（jieba 分词 + 进程内 Python BM25，全量加载评分）；
- MySQL 路径异常会降级到 Python 路径，不阻断检索。

向量检索：embedding 以打包后的字节/文本存在模型字段里（`pack_vector`），相似度在应用侧算，**不依赖 pgvector / MySQL VECTOR 类型**。

**含义**：换 PG 时，BM25 会因为没有 `_bm25_search_mysql` 而直接落到 Python 全量评分路径——**功能不中断，但检索性能和可伸缩性会退回开发档**（全量加载文档到内存评分）。要恢复生产级性能，需要为 PG 新写一个 `_bm25_search_postgres`（用 `tsvector` + GIN 索引，或中文用 zhparser/pg_jieba，或直接用 pg_trgm）。这是整个迁移里唯一需要认真设计的一块。

---

## 3. 主流实践调研（2026）

调研来源见第 8 节。核心共识：

1. **AI/RAG 场景 PostgreSQL 是主流默认**：pgvector 几乎是"AI 项目的默认向量方案"，支持 HNSW/IVFFlat 索引、0.8.0 起有迭代扫描（缓解带过滤条件的过筛问题），被 LangChain/LlamaIndex 及 Supabase/Neon 等托管平台原生集成；MySQL 9.0 虽引入原生 VECTOR 类型，但生态、索引类型、生产验证都明显年轻。
2. **JSONB 是半结构化 Agent 状态/元数据的成熟解**：jsonb 二进制存储可索引、GIN 索引 + 丰富操作符，从 PG 9.4 起已生产验证十余年；mysql 的 JSON 支持够用但弱于 jsonb。
3. **混合检索（关键词 + 向量）PG 更顺**：可在一个 SQL 事务里完成关系过滤 + 全文检索 + 向量排序，避免多套存储的数据同步问题。
4. **中文全文检索**：bigram（如项目当前 ngram 做法）够用于 RAG 辅助层；要更高质量可用 PG 的 zhparser/pg_jieba 扩展；搜索是核心业务则上 Elasticsearch。有观点明确："配合 Reranker 时关键词层不需要很精确，bigram 通常够用"——项目已有自研 rerank，契合这一点。
5. **诚实的反面**：MySQL 在纯 OLTP、团队已有 MySQL 运维体系、WordPress/PHP 生态里仍是合理选择；`toolchew` 的对比也指出托管云上（RDS/Supabase/Neon）复制/高可用差异被抹平，不必为 HA 单独选边。

---

## 4. 迁移收益 vs 成本（针对本项目）

### 收益（迁到 PG 后能拿到什么）

- **向量检索一体化**：未来知识库/记忆的语义检索可以从"应用侧算相似度 + 全量加载"升级为 pgvector + HNSW 数据库内检索，性能与规模上限提升；可与业务数据同事务。
- **JSONB**：当前 20+ 个 `*_json` 的 Text 字段可逐步转 JSONB，获得索引与查询能力（如按元数据过滤、审计字段检索）。
- **中文检索质量可选升级**：zhparser/pg_jieba 比 ngram bigram 分词质量高。
- **复杂查询**：CTE/窗口函数/并行查询更强，利于运营报表、分析类需求（项目已有 dashboard、user_analytics、eval 等模块）。

### 成本（真正要付出什么）

| 成本项 | 评估 |
|--------|------|
| 引擎与连接层 | **低**：SQLAlchemy 抽象已就位，改 `DATABASE_URL` + 装 `psycopg` 即可 |
| 现有表结构迁移 | **低**：字段类型基本通用，LONGTEXT variant 去掉即可 |
| Alembic 历史脚本 | **低**：老脚本按方言 no-op，新库从头 upgrade head 即可；需实测 |
| **知识库 BM25** | **中高**：要为 PG 新写检索路径（tsvector/GIN 或 zhparser），并做质量回归（见 `tests/test_kb_hybrid_retrieval.py`） |
| 输入/审计等 SQL | **低**：未见 MySQL 专有函数（`GROUP_CONCAT`/`ON DUPLICATE KEY` 等均未使用） |
| 运维 | **中**：需部署 PG 实例、备份/监控；团队若无 PG 经验有学习成本 |
| 回归测试 | **中**：28 个迁移 + 全量测试需在 PG 上跑一遍 |
| 数据迁移（存量生产库） | **中**：若已有 MySQL 生产数据，要停机/双写/导出导入，有一致性风险 |

**总评**：技术耦合很低，真正的工作量集中在"知识库检索的 PG 路径"和"回归验证"，不是"换数据库"本身。所以成本可控，但收益目前也主要是"未来兑现"——这正是建议"定方向、缓执行"的原因。

---

## 5. 推荐方案（分阶段）

### 阶段 0：确立方向，不动代码
- 文档与配置层面：把 PostgreSQL 写为**生产推荐**数据库，`DATABASE_URL` 示例补充 PG 写法；开发继续 SQLite。
- 依赖：把 `psycopg[binary]` 列为可选 extra（如 `pg`），不强制安装。

### 阶段 0.5：本机 PG 开发环境（已具备条件，2026-11-17 实测）
本机已经装好 PG，**可以直接用来做 PG 开发/双轨验证**，无需先搭环境。实测事实：

| 项 | 实测结果 |
|---|---|
| PostgreSQL 版本 | **16.15**（Homebrew，`postgresql@16`），已安装 |
| 命令行工具 | `psql`/`postgres`/`pg_ctl`/`initdb`/`createdb`/`pg_isready` 齐全（`/opt/homebrew/bin/`） |
| 数据目录 | `/opt/homebrew/var/postgresql@16`，已初始化（PG_VERSION=16，39MB，属主 xiaojia） |
| 服务状态 | **未启动**（`pg_isready` 无响应、5432 无监听、无 postmaster.pid） |
| Python 驱动 | 项目 venv **未装** psycopg/psycopg2/asyncpg/pg8000（只有 greenlet 3.5.0） |
| 项目对接 | `session.py` 对非 SQLite URL 有通用连接池分支；`config.py:77` 默认仍是 SQLite；`.env` 无 DATABASE_URL |

**从零到能开发只需 3 步**：
1. 启动服务：`brew services start postgresql@16`（或 `pg_ctl -D /opt/homebrew/var/postgresql@16 -l /tmp/pg.log start`），`pg_isready` 确认 5432 通。
2. 建库建用户：`createdb agenticos_dev`（本机默认用户即 xiaojia），或用 `psql` 建专用用户+库。
3. 装驱动并配 URL：`backend/.venv/bin/pip install 'psycopg[binary]'`，然后 `.env` 里设 `DATABASE_URL=postgresql+psycopg://xiaojia@localhost:5432/agenticos_dev`。

> 注意：项目 SQLAlchemy 2.0 + Alembic，PG 走 `psycopg` 3 即可（同步）；若将来上异步需 `asyncpg`，但当前代码是同步引擎（`create_engine`），先用 psycopg 就够。启动/装驱动/改 `.env` 属于操作本机环境，本次只做只读排查、**未实际执行**，按此文档即可开干。

### 阶段 1：加 PG 支持，双轨验证（不迁移存量）
- 在 CI 里增加"PG 跑全量测试"的 job（SQLite 与 PG 双数据库矩阵），用容器起临时 PG。
- 修复 PG 下暴露的问题（预计集中在迁移脚本的方言分支与索引创建）。
- 新增 `_bm25_search_postgres()`：`tsvector` + GIN（中文可选 zhparser/pg_jieba 扩展，先用简单配置 + 自研 rerank 兜质量），复用现有降级机制。

### 阶段 2：新功能优先按 PG 设计
- 新的检索/向量能力直接用 pgvector（`vector` 列 + HNSW 索引），不再扩充应用侧相似度计算。
- 新增的元数据字段逐步用 JSONB（保留 Text 兼容迁移）。

### 阶段 3：存量生产库迁移（按收益触发）
- 触发条件：数据量/检索质量/分析需求达到拐点，或明确要上 pgvector 规模化。
- 方式：新库 `create_all` + `alembic upgrade head` 建结构 → 全量导入 → 双读校验 → 切换 → 保留回滚窗口。
- 全程不影响 SQLite 开发档。

---

## 6. 风险与注意事项

- **不要为"换库而换库"**：当前 MySQL 耦合浅、SQLite 默认跑得很好，纯换引擎的收益几乎为零；收益来自 pgvector/JSONB/检索质量，要绑定具体功能来做。
- **迁移幂等性纪律**：继续遵守现有约定（每步先 `sa.inspect()`；Boolean `server_default=sa.text("0")`；SQLite 加外键用 `batch_alter_table`），新增 PG 分支时要同步保证三种方言都幂等。
- **中文检索质量回归**：BM25 路径改动必须跑 `tests/test_kb_hybrid_retrieval.py` 的相关度断言（0~1、阈值 <=1.0），并用真实语料对比 ngram vs PG 方案。
- **pgvector 不是银弹**：中小规模（千万级以下）pgvector 足够；更大规模再评估专用向量库（Milvus 等）。当前项目远未到这个量级。
- **审计与记忆**：检索/审计相关改动要同步更新 `tests/test_audit.py::_AUDITED_MODULES`（若新增管理模块）。

---

## 7. 一句话建议

**把 PostgreSQL 定为生产推荐、未来默认的数据库方向，开发继续用 SQLite；现在就补 PG 的双轨测试与知识库检索的 PG 路径，但不要立即对存量 MySQL 生产库做物理迁移——等向量检索上规模或需要 JSONB/复杂查询时再迁，那时候收益才兑现。**

---

## 8. 调研来源（2026-11-17）

- 腾讯云《MySQL vs PostgreSQL：数据库选型完全指南》cloud.tencent.com/developer/article/2690614
- CSDN《AI 时代首先数据库—PostgreSQL 实战笔记》：PG vs MySQL 对比、pgvector/RAG 场景
- 夫子AI《为什么 AI 开发更喜欢用 postgres 而不是 mysql?》fuziai.com/841.html
- 夜雨聆风《AI 时代，该把数据库从 MySQL 换到 PostgreSQL 了！》yeyulingfeng.com/a/702467.html
- toolchew《Postgres vs MySQL 2026: default database for new projects》：JSONB、全文检索、pgvector、托管云、性能 benchmark 与反例
- techsy《PostgreSQL vs MySQL in 2026》：扩展生态与 pgvector/MySQL VECTOR 对比
- kunalganglani《PostgreSQL vs MySQL: Which to Pick for New Projects》：pgvector 0.8.0 / HNSW / 过滤性能、JSONB 成熟度
- 云栖网《MySQL 9.x 向量检索实战》：MySQL VECTOR vs pgvector vs 专用向量库的选型边界
- RottenWiFi《PostgreSQL vs MySQL for AI Agent Applications》：Agent 场景对事务/JSON/检索的要求
- 稀土掘金《从零搭建生产级 RAG》：中文全文检索方案分档（bigram / zhparser / ES）、pgvector + tsvector + HNSW + GIN 的推荐链路
