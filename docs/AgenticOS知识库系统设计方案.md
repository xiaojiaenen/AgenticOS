# AgenticOS 知识库系统设计方案

## 1. 背景与目标

### 1.1 问题陈述

AgenticOS 平台当前具备 per-user 的分层记忆系统（L0→L1→L2→L3 蒸馏管线 + BM25/向量/RRF 混合检索），但缺少**组织级知识管理能力**。企业内部存在大量需要共享、检索、持续维护的知识资产——制度文档、技术规范、产品手册、FAQ、最佳实践等。这些知识目前散落在各处，Agent 无法在对话中有效利用。

### 1.2 设计目标

- **LLM-native**：知识以 LLM 可消费的结构化格式存储，而非仅供人类浏览的传统文档库
- **编译优于检索**：知识预先由 LLM 从原始文档中"编译"为 Wiki 页面，而非每次查询时从原文临时提取（RAG）
- **分层共享**：支持组织级、团队级、个人级三层知识归属
- **矛盾显式化**：不静默覆盖矛盾信息，而是标记、排序、提供解决流程
- **Agent 原生集成**：知识库作为 Agent 的工具存在，检索结果自动注入上下文，用户无感
- **可溯源**：每条知识可追溯到原始文档，支持权威性分级

### 1.3 参考项目

| 项目 | 借鉴点 |
|------|--------|
| **llm_wiki** (nashsu) | 文档→Wiki 编译管线、`purpose.md` 目标声明、`[[wikilinks]]` 互链、异步 review 队列、SHA256 增量编译、4 信号图扩展检索 |
| **TencentDB Agent Memory** | 四层记忆蒸馏管线（L0→L1→L2→L3）、三维隔离模型（team+user+agent）、MemoryProxy 透明注入、Pipeline Manager 异步调度、MemoryKnowledge Wiki 引擎 |

### 1.4 与现有系统的关系

AgenticOS 已有的记忆系统（`memories`、`memory_conversations`、`memory_scenarios`、`memory_personas` 表 + BM25/向量/RRF 检索管线）是 **per-user 的个人记忆**，本方案在此基础上扩展 **per-org 的组织知识**。两者共存，检索时合并注入 Agent 上下文。

---

## 2. 整体架构

### 2.1 三层知识架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent 对话层                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ 个人记忆  │  │ 知识库检索    │  │ 外部系统检索（已有能力） │  │
│  │ (现有)   │  │ (新增)       │  │                          │  │
│  └────┬─────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│       │               │                        │                │
│       └───────────────┼────────────────────────┘                │
│                       ▼                                         │
│            ┌─────────────────────┐                              │
│            │ 统一上下文注入       │                              │
│            │ (Context Injector)  │                              │
│            └─────────┬───────────┘                              │
├──────────────────────┼──────────────────────────────────────────┤
│                      │                                          │
│   ┌──────────────────▼──────────────────────────────────────┐   │
│   │              第二层：Wiki 编译层                          │   │
│   │                                                          │   │
│   │  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │   │
│   │  │Wiki 页面  │  │知识图谱   │  │ 冲突标记 & Review 队列│  │   │
│   │  │(结构化    │  │(wikilinks│  │                       │  │   │
│   │  │ Markdown) │  │ 互链)    │  │                       │  │   │
│   │  └──────────┘  └──────────┘  └───────────────────────┘  │   │
│   └──────────────────────────┬───────────────────────────────┘   │
│                              │                                   │
│   ┌──────────────────────────▼───────────────────────────────┐   │
│   │              第一层：原始文档层 (Document Store)            │   │
│   │                                                           │   │
│   │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────────┐  │   │
│   │  │  PDF   │  │  Word  │  │   MD   │  │ 网页剪藏/其他  │  │   │
│   │  └────────┘  └────────┘  └────────┘  └────────────────┘  │   │
│   └───────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

**第一层：原始文档层**——存储用户上传的原始文档（PDF、Word、Markdown、HTML、网页剪藏等），保持原文不变。核心用途是**溯源**和**治理**。每条文档有版本管理、权限控制、状态标记（待编译/已编译/编译失败）。

**第二层：Wiki 编译层**——原始文档经过 LLM 驱动的编译管线，转化为结构化的 Wiki 页面。每个页面有 YAML frontmatter（title、type、sources、tags）、`[[wikilinks]]` 互链、`sources` 字段指向原始文档。这是 Agent 检索的**主要来源**。

**第三层：Agent 对话层**——Agent 在对话中通过 `search_knowledge_base` 工具检索知识，结果与个人记忆检索合并后注入上下文。用户无需感知知识库的存在，Agent 自动完成检索和引用。

### 2.2 知识流转路径

```
用户上传文档 ──→ 文档解析 ──→ LLM 分析提取 ──→ 冲突检测
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                               全新知识        补充已有知识       矛盾知识
                                    │               │               │
                                    ▼               ▼               ▼
                              创建新 Wiki 页面  合并到已有页面   创建 Review 任务
                                    │               │               │
                                    ▼               ▼               ▼
                              生成 embedding    更新 embedding    等待人工审核
                                    │               │
                                    ▼               ▼
                              建立 wikilinks   更新 wikilinks
                                    │               │
                                    └───────┬───────┘
                                            ▼
                                    Agent 检索时消费
```

---

## 3. 数据模型设计

### 3.1 新增表

在现有 22 张表基础上新增以下表：

#### knowledge_bases（知识库定义）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| name | String(200) | 知识库名称 |
| slug | String(200) unique | URL 友好标识 |
| description | Text | 描述 |
| purpose | Text | **目标声明**（借鉴 llm_wiki 的 purpose.md）——定义知识库关注什么、不关注什么，LLM 编译和检索时参考 |
| scope | String(20) | 归属层级：`org` / `team` / `personal` |
| owner_id | Integer FK→users | 创建者 |
| team_id | Integer nullable | scope=team 时关联的团队 |
| visibility | String(20) | `public` / `restricted` / `private` |
| settings_json | Text | 编译参数（LLM 模型、chunk 大小、是否需审核等） |
| is_active | Boolean | 是否启用 |
| created_at | AppDateTime | 创建时间 |
| updated_at | AppDateTime | 更新时间 |

`purpose` 字段是核心设计。它用自然语言告诉 LLM："这个知识库是为了解决什么问题"。例如："本知识库包含公司后端服务的部署运维规范，关注 Docker 部署、监控告警、故障排查，不包含前端代码相关内容。" LLM 在编译时会据此决定哪些信息值得提取，在检索时会据此判断相关性。

#### kb_documents（原始文档）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| knowledge_base_id | Integer FK | 所属知识库 |
| title | String(500) | 文档标题 |
| file_path | String(1000) | 文件存储路径 |
| file_type | String(20) | pdf / docx / md / html / epub |
| file_size | Integer | 文件大小（字节） |
| content_hash | String(64) | SHA256 哈希，用于增量编译 |
| version | Integer | 版本号（同一文档多次上传递增） |
| status | String(20) | pending / compiling / compiled / failed |
| compiled_at | AppDateTime | 最近一次成功编译的时间 |
| error_message | Text | 最近一次编译失败的错误信息 |
| uploaded_by | Integer FK→users | 上传者 |
| created_at | AppDateTime | 上传时间 |
| updated_at | AppDateTime | 更新时间 |

#### kb_wiki_pages（Wiki 编译产物）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| knowledge_base_id | Integer FK | 所属知识库 |
| title | String(500) | 页面标题 |
| slug | String(500) | URL 友好标识 |
| page_type | String(30) | 页面类型（见下方枚举） |
| content | Text | Markdown 正文 |
| frontmatter_json | Text | YAML frontmatter 结构化存储 |
| sources_json | Text | 溯源：`["kb_document:3", "kb_document:7"]` |
| embedding | Text | 向量 embedding（或存独立向量表） |
| authority_level | String(10) | 权威性分级：L3 / L2 / L1 / L0 |
| conflicts_json | Text | 冲突标记（详见第 6 节） |
| is_active | Boolean | 是否有效 |
| created_at | AppDateTime | 创建时间 |
| updated_at | AppDateTime | 更新时间 |

**page_type 枚举**：

| 类型 | 含义 | 示例 |
|------|------|------|
| entity | 实体（人、组织、产品） | "AgenticOS 平台"、"张三" |
| concept | 概念（理论、方法、技术） | "上下文压缩"、"HITL 审批" |
| source_summary | 单个来源的摘要 | "2024-Q3 压测报告摘要" |
| synthesis | 跨来源综合分析 | "各环境部署配置对比" |
| comparison | 对比分析 | "SQLite vs MySQL 选型" |
| faq | 问答对 | "如何重置用户密码？" |
| procedure | 操作流程 | "生产环境部署步骤" |

#### kb_wiki_links（页面间链接关系）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| source_page_id | Integer FK→kb_wiki_pages | 链接来源页面 |
| target_page_id | Integer FK→kb_wiki_pages | 链接目标页面 |
| link_type | String(20) | reference / related / contradicts / extends |
| context | String(500) | 链接上下文（为什么建立这个链接） |

`contradicts` 类型的链接专门标记矛盾关系，与 `conflicts_json` 配合使用。

#### kb_ingest_tasks（编译任务队列）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| knowledge_base_id | Integer FK | 所属知识库 |
| document_id | Integer FK→kb_documents | 目标文档 |
| task_type | String(20) | compile / recompile / delete |
| status | String(20) | pending / running / completed / failed / retrying |
| progress | Float | 0.0 ~ 1.0 |
| retry_count | Integer | 已重试次数 |
| max_retries | Integer | 最大重试次数（默认 3） |
| error_message | Text | 错误信息 |
| started_at | AppDateTime | 开始时间 |
| completed_at | AppDateTime | 完成时间 |
| created_at | AppDateTime | 创建时间 |

#### kb_review_items（人工审核队列）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| knowledge_base_id | Integer FK | 所属知识库 |
| review_type | String(30) | 审核类型（见下方枚举） |
| title | String(500) | 审核标题 |
| description | Text | 审核描述（LLM 生成，说明为什么需要审核） |
| options_json | Text | 可选操作列表 |
| related_page_ids_json | Text | 关联的 Wiki 页面 ID |
| related_document_ids_json | Text | 关联的原始文档 ID |
| status | String(20) | pending / approved / rejected / resolved |
| resolved_by | Integer FK→users | 审核人 |
| resolved_at | AppDateTime | 审核时间 |
| resolution_note | Text | 审核备注 |
| created_at | AppDateTime | 创建时间 |

**review_type 枚举**：

| 类型 | 含义 |
|------|------|
| conflict_resolution | 矛盾解决——两条知识互相矛盾，需要人工判断 |
| page_creation | 新页面创建确认——LLM 不确定是否应该创建这个页面 |
| page_merge | 页面合并——LLM 认为两个页面应该合并 |
| page_delete | 页面删除——LLM 认为某个页面已过时或重复 |
| authority_upgrade | 权威性提升——请求将 L1 内容提升为 L2 |

#### kb_access_control（知识库访问控制）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| knowledge_base_id | Integer FK | 所属知识库 |
| principal_type | String(10) | user / team |
| principal_id | Integer | user_id 或 team_id |
| role | String(20) | admin / editor / viewer |
| granted_by | Integer FK→users | 授权人 |
| created_at | AppDateTime | 创建时间 |

### 3.2 现有表扩展

#### memories 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| scope | String(10) | `user`（默认）/ `org`——标记记忆归属 |
| knowledge_base_id | Integer FK nullable | 关联到知识库（scope=org 时使用） |
| authority_level | String(10) | 权威性分级，默认 L1 |

这样个人记忆可以"晋升"为组织知识——将 scope 从 user 改为 org，关联到知识库，经审核后提升 authority_level。

---

## 4. 文档编译管线（Ingest Pipeline）

### 4.1 管线流程

```
文档上传
  │
  ▼
[1] 文档解析 (Document Parser)
  │  PDF  → 文本 + 表格 + 图片位置 (pdfium)
  │  Word → 文本 + 样式结构 (python-docx)
  │  MD   → 直接读取
  │  HTML → 正文提取 + 转 Markdown (readability + turndown)
  │
  ▼
[2] 增量检查
  │  SHA256(content) == 已存储的 content_hash？
  │  是 → 跳过编译，标记为 compiled
  │  否 → 继续
  │
  ▼
[3] LLM 分析 (Analysis Phase)
  │  输入：文档内容 + 知识库 purpose
  │  输出：结构化分析结果
  │    {
  │      entities: [{name, type, description}],
  │      concepts: [{name, description, key_points}],
  │      facts: [{claim, evidence, confidence}],
  │      procedures: [{name, steps}],
  │      faqs: [{question, answer}],
  │      contradictions: [{claim, existing_page_id, nature}]
  │    }
  │
  ▼
[4] 冲突检测 (Conflict Detection)
  │  将分析结果中的 facts/concepts 与已有 Wiki 页面比对
  │  方法：embedding 相似度初筛 + LLM 精确判断
  │    完全一致 → 标记"已有，跳过"
  │    补充信息 → 标记"合并到已有页面"
  │    矛盾     → 标记"冲突"，创建 review 任务
  │    全新     → 标记"创建新页面"
  │
  ▼
[5] Wiki 页面生成 (Generation Phase)
  │  LLM 根据分析结果生成 Markdown 页面
  │  每个页面包含：
  │    - YAML frontmatter (title, type, sources, tags)
  │    - 正文内容（自包含，不依赖上下文即可理解）
  │    - [[wikilinks]] 指向相关页面
  │    - sources 指向原始文档
  │
  ▼
[6] 链接建立 (Linking Phase)
  │  解析所有 [[wikilinks]]
  │  写入 kb_wiki_links 表
  │  更新知识图谱
  │
  ▼
[7] Embedding 生成
  │  对每个页面生成向量 embedding
  │  存入向量索引
  │
  ▼
[8] 更新文档状态
     kb_documents.status = "compiled"
     kb_documents.content_hash = SHA256
     kb_documents.compiled_at = now()
```

### 4.2 增量编译

借鉴 llm_wiki 的 SHA256 缓存机制。每次文档上传或更新时，先计算内容哈希，与已存储的 `content_hash` 比对。如果内容未变，跳过编译。这避免了大量文档时的全量重跑。

对于"合并到已有页面"的情况，采用增量更新策略：LLM 读取已有页面内容和新文档的分析结果，生成合并后的新版本。合并时在 frontmatter 的 `sources` 中追加新的来源。

### 4.3 编译参数配置

每个知识库可在 `settings_json` 中配置编译参数：

```json
{
  "llm_model": "gpt-4o",
  "chunk_size": 4000,
  "chunk_overlap": 200,
  "max_pages_per_document": 50,
  "auto_compile": true,
  "require_review_for_creation": false,
  "require_review_for_update": false,
  "conflict_detection_threshold": 0.85,
  "embedding_model": "text-embedding-3-small"
}
```

`require_review_for_creation` 和 `require_review_for_update` 控制编译产物是否直接进入知识库，还是先进 review 队列等待人工确认。对于组织级权威知识库，建议开启。

### 4.4 编译任务调度

借鉴 TencentDB 的 Pipeline Manager 设计，编译任务异步执行，不阻塞用户操作：

- 文档上传后创建 `kb_ingest_tasks` 记录，状态为 pending
- 后台 worker 按 FIFO 顺序取任务执行
- 串行处理（避免并发 LLM 调用导致混乱），可配置并发数
- 失败自动重试，最多 `max_retries` 次
- 支持手动触发重编译（重新上传文档或点击"重新编译"按钮）

---

## 5. 知识检索与 Agent 上下文注入

### 5.1 检索管线

```
用户提问
  │
  ▼
[1] 查询理解
  │  LLM 提取查询意图和关键词
  │  结合知识库 purpose 判断相关性
  │
  ▼
[2] 多路检索（并行）
  │
  ├─ BM25 全文检索
  │    搜索 kb_wiki_pages.content + title
  │    中文使用 bigram 分词，英文使用标准分词
  │    title 命中加权 +10
  │
  ├─ 向量语义检索
  │    query embedding 与 kb_wiki_pages.embedding 做余弦相似度
  │    取 top-K（默认 K=10）
  │
  └─ 知识图谱扩展
       取前两路 top 结果作为种子节点
       在 kb_wiki_links 上做 2-hop 遍历
       4 信号相关性评分：
         - 直接链接 ×3.0
         - 来源重叠 ×4.0
         - Adamic-Adar 指数 ×1.5
         - 类型亲和度 ×1.0
  │
  ▼
[3] 结果融合
  │  Reciprocal Rank Fusion (RRF, k=60)
  │  文件名精确匹配 bonus +200
  │  短语出现在标题中 bonus +50
  │  按 authority_level 加权：L3 ×2.0, L2 ×1.5, L1 ×1.0, L0 ×0.8
  │
  ▼
[4] 冲突标注
  │  检查 top 结果中是否有 conflicts_json 非空的页面
  │  如果有，附加冲突信息到检索结果
  │
  ▼
[5] Token 预算控制
     总预算 = context_window × 0.3（知识库占 30%）
     按相关性得分从高到低填充
     超出预算时截断
```

### 5.2 Agent 工具接口

新增 `knowledge_tools.py`，提供以下工具：

```python
@registry.tool()
def search_knowledge_base(
    query: str,
    knowledge_base_id: int = None,     # 不指定则搜索所有有权限的知识库
    page_type: str = None,             # 过滤页面类型
    max_results: int = 5,
) -> list[KnowledgeSearchResult]:
    """搜索知识库，返回匹配的 Wiki 页面"""

@registry.tool()
def read_wiki_page(page_id: int) -> WikiPageContent:
    """读取指定 Wiki 页面的完整内容"""

@registry.tool()
def list_knowledge_bases() -> list[KnowledgeBaseInfo]:
    """列出当前用户可访问的知识库"""
```

### 5.3 上下文注入策略

在 `AgentService` 构建 Agent 时，通过中间件或系统提示注入知识库上下文。注入格式：

```
## 知识库上下文

以下是与当前对话相关的知识库内容：

### [页面标题] (来源: [原始文档名], 权威性: [L2])
[页面内容摘要，控制在 500 token 以内]

### [页面标题] (来源: [原始文档名], 权威性: [L1])
[页面内容摘要]

注意：
- 以上信息来自公司知识库，优先于你的训练数据
- 如果知识库内容与用户说法矛盾，以知识库为准，但告知用户
- 如果多条知识库内容互相矛盾，告知用户并列出不同版本
- 引用知识库内容时，标注来源
```

### 5.4 与个人记忆的合并

检索时，知识库检索和个人记忆检索并行执行，结果合并后注入上下文。合并策略：

- 知识库结果占上下文预算的 30%
- 个人记忆结果占 15%
- 最近 N 轮对话保持原样
- 系统提示占 10%

如果知识库和个人记忆返回了关于同一主题的内容，优先展示知识库的（权威性更高），个人记忆的作为补充。

---

## 6. 冲突检测与解决

矛盾处理是本方案的核心设计之一。原则是：**不消除矛盾，而是标记矛盾、权威性排序、提供解决流程**。

### 6.1 冲突检测时机

冲突检测发生在两个阶段：

**编译阶段**——新文档编译时，分析结果与已有 Wiki 页面比对。如果发现矛盾（LLM 判断 + embedding 相似度 > 阈值），创建 `KBReviewItem`（type=conflict_resolution），同时在相关页面的 `conflicts_json` 中记录冲突。

**定期巡检**——后台定时任务，对知识库内的页面做两两比对（通过 embedding 聚类），发现潜在的隐性矛盾。这可以捕获随着时间推移、不同文档之间产生的不一致。

### 6.2 冲突数据结构

```json
{
  "conflict_id": "c_abc123",
  "claim_a": {
    "content": "系统最大并发数为 1000",
    "source_document": "产品规格说明书 v2.3",
    "source_page_id": 42,
    "authority_level": "L2",
    "created_at": "2024-10-15"
  },
  "claim_b": {
    "content": "系统最大并发数为 800（压测实测）",
    "source_document": "2024-Q3 压测报告",
    "source_page_id": 87,
    "authority_level": "L1",
    "created_at": "2024-11-20"
  },
  "nature": "数值矛盾",
  "detected_at": "2024-12-01",
  "resolved_by": null,
  "resolution": null
}
```

### 6.3 权威性分级

```
L3 - 系统/管理员锁定
  不可被 LLM 修改，只能由管理员手动编辑
  适用于：公司核心制度、合规要求、安全规范

L2 - 审核通过
  经过 review 流程确认的内容
  适用于：产品文档、技术方案、操作手册

L1 - 自动编译
  LLM 从文档中直接提取，未经人工审核
  适用于：一般性知识、FAQ、信息汇总

L0 - 用户贡献
  个人提交的未审核内容
  适用于：个人笔记、经验分享、待确认信息
```

权威性在检索时的权重：L3 ×2.0 > L2 ×1.5 > L1 ×1.0 > L0 ×0.8。

当 Agent 遇到矛盾内容时，优先采用权威性更高的版本。如果权威性相同，则告知用户存在矛盾。

### 6.4 Agent 侧矛盾处理策略

Agent 在系统提示中注入矛盾处理规则：

```
当知识库中存在关于同一主题的多条矛盾信息时：

1. 权威性差异大（如 L2 vs L0）：
   → 采用高权威性版本，无需特别告知用户

2. 权威性相同但内容矛盾（如 L1 vs L1）：
   → 主动告知用户："知识库中关于这个问题有两种说法"
   → 列出两个版本及各自来源
   → 让用户根据实际情况判断

3. 低权威性但更新时间：
   → 倾向采用更新的信息
   → 标注"该信息尚未经过审核"

4. 被标记为 L3（锁定）的内容：
   → 无论其他来源如何，以 L3 为准
   → 如果与其他来源矛盾，简要说明"根据公司规定..."
```

### 6.5 审核解决流程

审核队列在前端管理后台的"知识库管理"标签页中展示。审核人可以看到：

```
┌─────────────────────────────────────────────────────────┐
│  冲突 #c_abc123                                          │
│                                                          │
│  说法 A（权威性 L2，已审核）                               │
│  来源：产品规格说明书 v2.3                                 │
│  内容：系统最大并发数为 1000                                │
│                                                          │
│  说法 B（权威性 L1，自动编译）                              │
│  来源：2024-Q3 压测报告                                    │
│  内容：系统最大并发数为 800（压测实测）                      │
│                                                          │
│  请选择：                                                 │
│  [采纳 A]  [采纳 B]  [两者都对，区分场景]  [需要补充信息]     │
│                                                          │
│  备注：________________________________                   │
│                                                          │
│                    [提交审核结果]                          │
└─────────────────────────────────────────────────────────┘
```

审核结果会更新相关页面的 `authority_level` 和 `conflicts_json`（resolved_by 和 resolution 字段），并触发受影响页面的重新编译。

---

## 7. 权限与共享模型

### 7.1 三层权限架构

```
组织级知识库（scope=org）
  ├── 管理员：可以编辑知识库设置、审核内容、管理权限
  ├── 编辑者：可以上传文档、触发编译
  └── 查看者：可以搜索和浏览（Agent 对话中自动引用）

团队级知识库（scope=team）
  ├── 团队管理员：管理本团队知识库
  ├── 团队成员：上传、搜索、浏览
  └── 其他团队：无权限（除非显式共享）

个人级知识库（scope=personal）
  └── 仅创建者可见
```

### 7.2 知识晋升机制

知识可以从低层级向高层级"晋升"：

**个人 → 团队**：员工在个人知识库中积累了一条有价值的经验，通过"分享到团队"操作，将其复制到团队知识库。此时 `authority_level` 重置为 L0，等待团队审核。

**团队 → 组织**：团队负责人认为某条团队知识应该成为公司级知识，通过"提交到组织知识库"操作，触发组织级知识库管理员的审核。

晋升过程中，原始来源链保持不断——晋升后的页面 `sources` 中会记录"由 [团队/个人] 知识库晋升，原始来源：[原始文档]"。

### 7.3 Agent 可见范围

Agent 在检索知识库时，自动过滤当前用户无权限的知识库。过滤逻辑在 `search_knowledge_base` 工具内部完成，对 Agent 透明——Agent 只看到有权限的结果。

```python
def _get_visible_knowledge_bases(user_id: int) -> list[KnowledgeBase]:
    """获取用户可见的知识库"""
    return db.query(KnowledgeBase).filter(
        or_(
            KnowledgeBase.scope == "org",  # 组织级全部可见
            and_(
                KnowledgeBase.scope == "team",
                KnowledgeBase.team_id.in_(user_team_ids(user_id))
            ),
            and_(
                KnowledgeBase.scope == "personal",
                KnowledgeBase.owner_id == user_id
            ),
        ),
        KnowledgeBase.is_active == True,
    ).all()
```

---

## 8. 后端模块设计

### 8.1 新增模块

```
app/services/knowledge/
  __init__.py
  document_parser.py        # 多格式文档解析
  ingest_pipeline.py        # 编译管线编排
  wiki_compiler.py          # LLM 驱动的 Wiki 页面生成
  wiki_linker.py            # wikilinks 解析和知识图谱维护
  conflict_detector.py      # 冲突检测（embedding 相似度 + LLM 判断）
  review_queue.py           # 审核队列管理
  retrieval.py              # 知识库检索（BM25 + 向量 + 图扩展 + RRF）
  context_injector.py       # 检索结果注入 Agent 上下文
  access_control.py         # 权限检查和过滤
```

### 8.2 新增 API 端点

```
POST   /api/v1/knowledge/bases                    # 创建知识库
GET    /api/v1/knowledge/bases                    # 列出知识库
GET    /api/v1/knowledge/bases/{id}               # 知识库详情
PUT    /api/v1/knowledge/bases/{id}               # 更新知识库
DELETE /api/v1/knowledge/bases/{id}               # 删除知识库

POST   /api/v1/knowledge/bases/{id}/documents     # 上传文档
GET    /api/v1/knowledge/bases/{id}/documents     # 文档列表
DELETE /api/v1/knowledge/bases/{id}/documents/{doc_id}  # 删除文档
POST   /api/v1/knowledge/bases/{id}/documents/{doc_id}/recompile  # 重新编译

GET    /api/v1/knowledge/bases/{id}/wiki/pages    # Wiki 页面列表
GET    /api/v1/knowledge/bases/{id}/wiki/pages/{page_id}  # 页面详情
PUT    /api/v1/knowledge/bases/{id}/wiki/pages/{page_id}  # 手动编辑页面
GET    /api/v1/knowledge/bases/{id}/wiki/graph    # 知识图谱数据

POST   /api/v1/knowledge/bases/{id}/search        # 搜索知识库
GET    /api/v1/knowledge/bases/{id}/reviews       # 审核队列
PATCH  /api/v1/knowledge/bases/{id}/reviews/{review_id}  # 处理审核

POST   /api/v1/knowledge/bases/{id}/access        # 添加访问控制
DELETE /api/v1/knowledge/bases/{id}/access/{ac_id} # 移除访问控制
POST   /api/v1/knowledge/bases/{id}/promote       # 知识晋升
```

### 8.3 关键类设计

#### DocumentParser

```python
class DocumentParser:
    """多格式文档解析，统一输出为 Markdown + 结构化信息"""

    async def parse(self, file_path: str, file_type: str) -> ParsedDocument:
        """
        ParsedDocument:
          - text: str              # 纯文本内容（Markdown 格式）
          - tables: list[Table]    # 表格数据
          - images: list[Image]    # 图片位置和描述
          - metadata: dict         # 文档元数据（作者、创建时间等）
          - sections: list[Section] # 章节结构
        """

    # 各格式解析实现
    def _parse_pdf(self, path) -> ParsedDocument: ...
    def _parse_docx(self, path) -> ParsedDocument: ...
    def _parse_markdown(self, path) -> ParsedDocument: ...
    def _parse_html(self, path) -> ParsedDocument: ...
```

#### WikiCompiler

```python
class WikiCompiler:
    """LLM 驱动的 Wiki 页面生成"""

    def __init__(self, llm: LLMGateway, knowledge_base: KnowledgeBase):
        self.llm = llm
        self.purpose = knowledge_base.purpose

    async def analyze(self, document: ParsedDocument) -> AnalysisResult:
        """
        分析阶段：LLM 阅读文档，输出结构化分析
        使用 purpose 引导 LLM 关注知识库的目标领域
        """

    async def generate_pages(self, analysis: AnalysisResult) -> list[WikiPageDraft]:
        """
        生成阶段：根据分析结果生成 Wiki 页面
        每个页面必须是自包含的（不依赖上下文即可理解）
        每个页面包含 [[wikilinks]] 和 sources 引用
        """

    async def detect_conflicts(
        self, pages: list[WikiPageDraft], existing_pages: list[KBWikiPage]
    ) -> list[Conflict]:
        """
        冲突检测：新页面与已有页面比对
        使用 embedding 相似度初筛 + LLM 精确判断
        """
```

#### KnowledgeRetrieval

```python
class KnowledgeRetrieval:
    """知识库检索，复用现有混合检索基础设施"""

    async def search(
        self,
        query: str,
        knowledge_base_ids: list[int],
        user_id: int,
        max_results: int = 10,
    ) -> list[SearchResult]:

        # 1. 并行执行多路检索
        bm25_results, vector_results = await asyncio.gather(
            self._bm25_search(query, knowledge_base_ids),
            self._vector_search(query, knowledge_base_ids),
        )

        # 2. RRF 融合
        fused = self._reciprocal_rank_fusion(bm25_results, vector_results, k=60)

        # 3. 知识图谱扩展
        expanded = self._graph_expand(fused[:5], hops=2)

        # 4. 权威性加权排序
        ranked = self._authority_weight(expanded)

        # 5. 权限过滤
        visible = self._filter_by_access(ranked, user_id)

        # 6. 冲突标注
        annotated = self._annotate_conflicts(visible[:max_results])

        return annotated
```

---

## 9. 前端设计

### 9.1 管理后台新增"知识库管理"标签页

在现有 `AdminDashboard.tsx` 的标签页列表中新增 `knowledge` 标签，对应 `KnowledgeManagement.tsx` 组件。

主要功能区域：

**知识库列表视图**——展示所有知识库，按 scope 分组（组织/团队/个人），显示文档数量、Wiki 页面数量、最近编译时间、状态。

**知识库详情视图**——进入某个知识库后，包含以下子标签：

- **文档管理**：文档列表、上传、删除、重新编译触发、编译状态监控
- **Wiki 浏览**：Wiki 页面的树形/列表视图，支持搜索和过滤，点击可查看页面内容和 frontmatter
- **知识图谱**：可视化展示页面间的链接关系（可参考 llm_wiki 的 sigma.js 实现）
- **编译任务**：编译队列状态、失败任务重试、编译日志
- **审核队列**：待审核项列表、冲突解决界面
- **权限管理**：成员和角色管理
- **设置**：知识库 purpose 编辑、编译参数配置、LLM 模型选择

### 9.2 聊天界面集成

聊天界面的改动很小——知识库检索对用户是透明的。Agent 调用 `search_knowledge_base` 工具时，前端以现有的 tool_calls 展示方式呈现（可折叠的工具调用详情）。

唯一的新增 UI 是：当 Agent 的回答引用了知识库内容时，在消息底部显示"知识库引用"卡片，展示引用的页面标题和来源文档，点击可跳转到 Wiki 页面详情。

### 9.3 知识晋升入口

在 Wiki 页面详情页增加"分享到..."按钮：

- 个人知识库 → 选择目标团队知识库
- 团队知识库 → 提交到组织知识库（触发审核）

---

## 10. 与现有系统的集成

### 10.1 Agent 工具注册

在 `tool_config_service.py` 的 `TOOL_CATALOG` 中新增知识库工具组：

```python
"knowledge_search": {
    "label": "知识库搜索",
    "description": "搜索组织/团队知识库",
    "sub_tools": [...],
    "is_concurrency_safe": True,
},
```

在 `agent_service.py` 的 `_build_tool_registry()` 中，根据 Agent 的 mode 决定是否加载知识库工具。建议所有 mode 都可用（与 decision_tools、memory_tools 同级）。

### 10.2 中间件扩展

新增 `KnowledgeInstructionMiddleware`，在 Agent 的系统提示中注入知识库使用指引：

```
你可以访问公司知识库。当用户的问题可能涉及公司制度、产品知识、
技术方案等组织知识时，主动使用 search_knowledge_base 工具检索。
引用知识库内容时，标注来源。遇到矛盾内容时，按权威性排序并告知用户。
```

### 10.3 复用现有基础设施

| 现有组件 | 复用方式 |
|---------|---------|
| `memory_bm25.py` | BM25 检索逻辑直接复用，索引范围扩展到 Wiki 页面 |
| `memory_vector_store.py` | 向量存储复用，新增 Wiki 页面的 embedding |
| `memory_retriever.py` | RRF 融合逻辑复用 |
| `session_storage.py` | 数据库会话管理复用 |
| `skill_service.py` | 技能管理的设计模式参考（CRUD + zip 上传） |
| `approval_manager.py` | 审核队列可参考审批流程设计 |
| 前端 `ChatMessage.tsx` | 工具调用展示复用，新增知识库引用卡片 |
| 前端 `AdminDashboard.tsx` | 管理后台框架复用，新增知识库管理标签 |

---

## 11. 实施计划

### 第一阶段：基础能力（2-3 周）

目标：跑通"文档上传 → Wiki 编译 → Agent 检索"的核心链路。

- 数据库表创建和迁移
- 文档解析器（先支持 PDF、Markdown、Word）
- Wiki 编译器（LLM 分析 + 页面生成）
- 基础检索（BM25 + 向量，不做图扩展）
- Agent 工具注册（`search_knowledge_base`）
- 管理后台：知识库 CRUD + 文档上传 + Wiki 浏览
- 仅支持组织级知识库，不做权限细分

### 第二阶段：冲突与审核（1-2 周）

目标：冲突检测、审核流程、权威性分级。

- 冲突检测器（embedding 相似度 + LLM 判断）
- 审核队列（创建、展示、处理）
- 权威性分级和检索加权
- Agent 侧矛盾处理策略（系统提示注入）
- 管理后台：审核队列 UI、冲突解决界面

### 第三阶段：分层与图谱（1-2 周）

目标：团队/个人知识库、知识图谱、知识晋升。

- 团队级和个人级知识库
- 访问控制和权限过滤
- 知识图谱构建和可视化
- 图扩展检索
- 知识晋升流程
- 管理后台：权限管理、图谱可视化

### 第四阶段：优化与打磨（持续）

- 增量编译优化（SHA256 缓存）
- 定期巡检任务（隐性矛盾发现）
- 编译质量评估指标
- 检索质量 A/B 测试
- 性能优化（大量文档时的编译和检索性能）

---

## 12. 关键设计决策记录

**Q: 为什么选择"编译"模式而非传统 RAG？**

传统 RAG 每次查询都从原文检索和拼接，质量依赖于分块策略和检索精度。编译模式预先让 LLM 理解文档、提取知识、建立链接，查询时检索的是已经结构化的 Wiki 页面。好处是：检索质量更高（编译产物是 LLM-friendly 的自包含内容）、支持知识图谱扩展、天然去重和冲突检测。代价是编译需要额外的 LLM 调用成本，但对于企业内部知识库（更新频率低、准确性要求高），这个代价是值得的。

**Q: 为什么不直接用 llm_wiki 或 TencentDB Agent Memory？**

llm_wiki 是桌面应用（Tauri/Rust），数据在本地文件系统，不适合企业多人协作场景。TencentDB Agent Memory 是 TypeScript 技术栈，与 AgenticOS 的 Python 后端不兼容。但两者的设计思想——llm_wiki 的编译管线和 review 队列、TencentDB 的四层蒸馏和透明注入——被充分吸收到本方案中。

**Q: 为什么 Wiki 页面而非直接存 embedding？**

Wiki 页面是人类可读的 Markdown，支持浏览、编辑、溯源。embedding 只是检索索引，不可读。两者都需要——Wiki 页面是"源"，embedding 是从 Wiki 页面生成的"索引"。

**Q: 为什么冲突不自动解决？**

自动解决矛盾风险太高。如果 LLM 自动选择了"正确"的版本，可能引入错误。企业内部知识需要人类判断——哪个来源更权威、哪个数据更新、是否适用场景不同。系统的职责是发现矛盾、呈现矛盾、辅助人类做决策，而非替代人类决策。

**Q: 编译成本如何控制？**

三个控制手段：一是增量编译（SHA256 缓存，只编译变更文档）；二是可配置 LLM 模型（组织级权威知识库用高质量模型如 GPT-4o，团队级用性价比模型如 GPT-4o-mini）；三是异步队列（不阻塞用户操作，后台串行处理，避免并发 LLM 调用）。
