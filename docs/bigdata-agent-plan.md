# AgenticOS 通用平台下的大数据专用 Agent 落地方案

## 1. 目标与前提

这次的目标不是把 `AgenticOS` 做成一个“大数据开发平台”，而是：

- 保持 `AgenticOS` 作为通用智能体平台
- 在平台内新增一组面向数据开发人员的专用 Agent
- 用这些 Agent 承接 `Dinky + Paimon + DolphinScheduler + Doris` 的研发场景

也就是说：

> `AgenticOS` 依旧通用，大数据能力作为其中一个或多个专用 Agent 套件存在。

结合当前代码，平台已经具备这些真实能力：

- 智能体会话与流式响应：`POST /api/v1/agent/stream`
- 人工审批：`POST /api/v1/agent/approvals/{approval_id}/decision`
- Skill 管理：`GET/POST/PATCH/DELETE /api/v1/skills`、`POST /api/v1/skills/upload`
- 智能体配置：`GET/POST/PATCH/DELETE /api/v1/agent-profiles`
- 智能体市场与安装：`GET /api/v1/agent-store`、`POST/DELETE /api/v1/agent-store/{profile_id}/install`
- 管理后台审计与统计：`GET /api/v1/dashboard/stats`、`GET /api/v1/dashboard/conversations`
- 工具开关与审批策略：`GET /api/v1/tool-config`、`PUT /api/v1/tool-config/modes/{mode}`

这意味着当前项目非常适合承载“垂类 Agent 套件”，而不需要改变平台定位。

## 2. 适用场景

这组专用 Agent 只面向数据开发相关人群，例如：

- 实时数仓开发
- 离线数仓开发
- 补数与调度运维
- ADS 指标发布
- 数据异常排查

典型技术栈：

- 实时开发：`Dinky` 编写 / 调试 / 提交 `Flink SQL`
- 数据分层：`ODS / DWD / DWS` 主要写入 `Paimon`
- 离线调度：`DolphinScheduler` 编排任务、补数、依赖
- 服务输出：`ADS` 写入 `Doris`

## 3. 核心痛点

1. 开发入口分散  
   实时 SQL、离线调度、湖仓存储、服务查询分散在不同平台，切换成本高。

2. 经验依赖重  
   Flink SQL、Paimon 建模、ADS 设计、补数流程严重依赖资深同学经验。

3. 变更风险高  
   发布、补数、DDL 调整、资源变更都可能影响下游，需要统一控制。

4. 知识沉淀弱  
   同类 SQL、同类 DAG、同类排障手法不断重复，没有沉淀到系统。

5. 审计视角不统一  
   “谁发起、AI 生成了什么、最后执行了什么、是否审批通过”缺少统一回溯。

## 4. 项目定位

### 4.1 平台定位

推荐继续把 `AgenticOS` 定位为：

> 通用 Agent 平台

平台层负责：

- 自然语言入口
- Agent 与 Skill 编排
- 审批与权限控制
- 会话记录与操作审计
- 通用前后端体验

### 4.2 数开能力定位

这次新增的能力应定位为：

> 面向数据开发团队的专用 Agent 套件

它负责：

- 把数据开发知识封装成专用 Agent / Skill
- 对接 Dinky、DolphinScheduler、Doris 等外部平台
- 只对指定用户或团队开放

### 4.3 不建议的方向

不建议让当前项目：

- 自己实现 SQL IDE
- 自己替代调度系统
- 自己替代湖仓引擎
- 自己承担大规模任务执行引擎职责

原因是：这些平台本身已经足够成熟，`AgenticOS` 最有价值的位置是“智能入口、受控集成、审批审计”。

## 5. 总体架构

```text
普通用户 / 业务用户 / 数据开发用户
                |
                v
AgenticOS（通用平台：会话 / Agent / Skill / 审批 / 审计）
                |
                +------------------> 通用 Agent
                |
                +------------------> 数开专用 Agent 套件
                                         |
                                         +-------> Dinky ------------------> Flink SQL / 作业执行
                                         |               |
                                         |               v
                                         |            Paimon（ODS / DWD / DWS）
                                         |
                                         +-------> DolphinScheduler -------> 离线工作流 / 补数 / 依赖编排
                                         |               |
                                         |               v
                                         |            Paimon / Doris
                                         |
                                         +-------> Doris ------------------> ADS 查询服务 / BI / API
```

推荐数据流向：

- `ODS -> DWD -> DWS`：优先沉淀到 `Paimon`
- `ADS`：优先写入 `Doris`
- 实时链路：通过 `Dinky/Flink SQL` 写入 `Paimon`
- 离线链路：通过 `DolphinScheduler` 编排读取 `Paimon`，结果写入 `Doris`

重要边界：

- `Paimon` 更适合作为数仓中间层和明细层主存储
- `Doris` 更适合作为 ADS 服务层和查询层
- `Doris` 可以查询 `Paimon`，但不应替代 `Paimon` 成为主写入底座

## 6. 为什么当前项目适合承接

### 6.1 Skill 已经具备扩展能力

后端已有：

- `backend/app/services/skill_service.py`
- `backend/app/api/v1/endpoints/skills.py`

当前能力支持：

- 后台创建 Skill
- 上传 zip Skill 包
- Skill 落本地目录
- Skill 绑定到 Agent Profile
- 运行时由 `SkillManager + FileSystemSkillProvider` 注入 Agent

这非常适合承接：

- Dinky SQL Skill
- Paimon 建模 Skill
- DolphinScheduler 工作流 Skill
- Doris ADS Skill

### 6.2 Agent Profile 已经具备角色隔离能力

后端已有：

- `backend/app/services/agent_service.py`
- `backend/app/services/agent_profile_service.py`
- `backend/app/schemas/agent_profiles.py`

当前能力支持：

- 每个 Agent 绑定独立系统提示词
- 每个 Agent 绑定不同工具集
- 每个 Agent 绑定多个 Skill
- 每个用户安装和使用不同 Agent

这很适合把数开能力做成“只对指定人群开放”的专用 Agent。

### 6.3 审批机制已经适合生产控制

后端已有：

- `backend/app/services/approval_manager.py`
- `backend/app/services/tool_config_service.py`
- `POST /api/v1/agent/approvals/{approval_id}/decision`

当前能力支持：

- 按工具维度控制审批
- Skill Python 脚本接入审批
- 管理员通过后台控制审批策略

这对大数据场景非常关键，因为下面这些动作必须受控：

- 提交生产 Flink SQL
- 发布 DolphinScheduler 工作流
- 执行补数
- 覆盖写入 ADS
- 删除表、删分区、删数据

### 6.4 会话与统计适合做审计

当前项目已经可以沉淀：

- 对话明细
- 工具调用过程
- Token 使用量
- 模型分布、工具分布、会话分布
- 管理后台会话查看

这天然适合扩展成“大数据开发操作审计”。

## 7. 产品能力设计

建议第一阶段提供 6 类能力：

1. Flink SQL 生成与修正
2. Paimon 分层建模建议
3. DolphinScheduler 工作流生成
4. Doris ADS 设计与发布建议
5. 运行状态查询与异常归因
6. 发布审批与操作审计

## 8. Skill 不应只输出内容

你提的这个判断是对的。

如果 Skill 只是“输出内容”，价值会停留在顾问型助手；但当前项目其实可以进一步做成“生成 + 受控执行”。

建议把能力拆成两层：

- 生成层：生成 SQL、DDL、DAG、补数方案、发布方案
- 执行层：在审批通过后，对接外部平台 API 真正执行

也就是说：

> Skill 可以先做生成器，再逐步升级成受控执行入口。

### 8.1 生成型 Skill

职责：

- 输出 SQL / DDL / DAG / 参数模板
- 风险相对低
- 最适合第一阶段上线

### 8.2 执行型 Skill

职责：

- 输出结构化执行请求
- 经审批后由后端集成层调用外部平台
- 回写执行结果、任务编号、错误信息

这里有一个重要工程建议：

- 不建议把所有外部系统调用散落在 Skill 脚本里
- 更建议由 Skill 产出结构化请求，再由后端统一 `integration client` 执行

这样更容易做：

- 统一鉴权
- 统一限流
- 统一重试
- 统一审计
- 统一回滚策略

## 9. 推荐的 Skill 设计

### Skill 1：`dinky_sql_skill`

职责：

- 根据业务需求生成 Flink SQL
- 输出建表 SQL、清洗 SQL、Join SQL、聚合 SQL
- 根据报错日志修复 SQL
- 给出并行度、状态 TTL、checkpoint 建议

可进阶能力：

- 生成 Dinky 提交请求草稿
- 调试前做参数检查
- 发布前做风险提示

### Skill 2：`paimon_model_skill`

职责：

- 设计 ODS / DWD / DWS 分层方案
- 输出 Paimon DDL
- 推荐主键、分区、bucket、merge-engine
- 提示 schema 演进风险

### Skill 3：`ds_workflow_skill`

职责：

- 生成 DolphinScheduler 工作流定义
- 生成补数方案
- 生成依赖关系和调度周期建议
- 生成失败重跑与告警建议

可进阶能力：

- 生成工作流发布请求草稿
- 生成补数执行请求草稿

### Skill 4：`doris_ads_skill`

职责：

- 设计 ADS 宽表 / 聚合表
- 输出 Doris 建表语句
- 设计导入或同步策略
- 给出查询优化建议

## 10. 推荐的 Agent 设计

### Agent 1：实时数仓开发助手

绑定：

- `dinky_sql_skill`
- `paimon_model_skill`

职责：

- 需求转 Flink SQL
- 实时模型设计
- Dinky 提交前检查

### Agent 2：离线调度助手

绑定：

- `ds_workflow_skill`
- `paimon_model_skill`

职责：

- 生成离线 DAG
- 生成补数方案
- 生成依赖与调度建议

### Agent 3：ADS 发布助手

绑定：

- `doris_ads_skill`
- `paimon_model_skill`

职责：

- 指标层方案设计
- ADS 表设计
- 发布前校验

### Agent 4：数据故障排查助手

绑定：

- `dinky_sql_skill`
- `ds_workflow_skill`
- `doris_ads_skill`

职责：

- 看日志定位问题
- 看失败任务判断环节
- 给出补数、回滚、重跑建议

## 11. 只给数据开发人员使用的控制方式

既然 `AgenticOS` 保持通用，这组 Agent 就要按“专用能力包”来控制开放范围。

### 11.1 建议的控制方式

- 数开 Agent 默认不对全站公开
- 只对指定用户、团队、角色开放
- 普通用户不展示这些 Agent

### 11.2 结合当前系统的实现方式

可以基于现有能力做控制：

- `agent-profiles`：定义数开专用 Agent
- `agent-store`：控制哪些 Agent 可被安装
- `my-agents`：只让目标用户看到和使用

如果后续要更严格，可以继续补：

- 用户组
- 角色标签
- Agent 可见范围
- Agent 授权关系

### 11.3 推荐权限层级

- 普通开发者：可生成方案、查看结果、发起执行申请
- 数据负责人：可审批发布、补数、回滚
- 平台管理员：可管理 Skill、Agent、策略和高风险动作

## 12. 核心逻辑流

### 12.1 开发类链路

1. 用户选择数开专用 Agent
2. 输入自然语言需求
3. Agent 调用对应 Skill 生成 SQL / DDL / DAG / 发布方案
4. 先向用户展示结构化草稿
5. 用户确认后，若需要真实执行，则发起审批
6. 审批通过后，由后端集成层调用外部平台
7. 执行结果回写会话、审批记录和后台审计

### 12.2 生产执行类链路

1. 用户要求“提交到 Dinky”或“发布工作流”或“执行补数”
2. Agent 生成结构化执行请求
3. 系统生成审批摘要
4. 管理员或负责人审批
5. 审批通过后，调用外部平台接口
6. 返回 job id / workflow id / instance id / 错误信息

### 12.3 多 Agent 协作建议

第一阶段不建议把体系做得太复杂。

更稳妥的路线是：

- 先采用“单 Agent + 多 Skill”
- 后续再演进为“主 Agent + 子 Agent”

原因：

- 当前代码已经稳定支持 Skill 注入
- 审批、审计、权限更容易先做扎实
- 成本更低，验证更快

## 13. 与当前项目后端接口的结合

### 13.1 当前真实可复用的接口

Skill 管理：

- `GET /api/v1/skills`
- `POST /api/v1/skills`
- `POST /api/v1/skills/upload`
- `PATCH /api/v1/skills/{skill_id}`
- `DELETE /api/v1/skills/{skill_id}`

Agent 管理：

- `GET /api/v1/agent-profiles`
- `POST /api/v1/agent-profiles`
- `PATCH /api/v1/agent-profiles/{profile_id}`
- `DELETE /api/v1/agent-profiles/{profile_id}`

对话执行：

- `POST /api/v1/agent/stream`

审批：

- `POST /api/v1/agent/approvals/{approval_id}/decision`

审计与统计：

- `GET /api/v1/dashboard/stats`
- `GET /api/v1/dashboard/conversations`
- `GET /api/v1/dashboard/conversations/{session_id}`

### 13.2 建议新增的后端集成层

建议新增：

- `backend/app/services/integrations/dinky_client.py`
- `backend/app/services/integrations/dolphinscheduler_client.py`
- `backend/app/services/integrations/doris_client.py`

建议新增统一任务编排层：

- `backend/app/services/bigdata_task_service.py`

职责：

- 接收 Skill 生成结果
- 生成结构化执行请求
- 触发审批
- 调用外部平台 client
- 回写执行结果与审计信息

## 14. Dinky 与 DolphinScheduler 的开发接法

### 14.1 Dinky：可以直接按官方 OpenAPI 集成

这部分非常适合直接做。

推荐方式：

1. Skill 生成 SQL 与作业参数
2. 后端 `dinky_client.py` 封装 Dinky OpenAPI
3. Agent 先给用户看 SQL 草稿和发布摘要
4. 用户确认后发起“提交到 Dinky”
5. 审批通过后，后端调用 Dinky OpenAPI
6. 将返回结果写入会话和后台审计

建议优先支持的能力：

- 创建或更新 SQL 草稿
- 提交测试作业
- 发布作业
- 查询作业状态
- 拉取日志与报错信息

### 14.2 DolphinScheduler：可以接，但建议做成受控发布链路

这部分也完全可以开发，但建议不要一开始就做成“聊天里直接随手发工作流”。

更合理的链路：

1. Skill 先生成工作流结构化定义
2. 用户确认工作流、依赖、补数参数
3. 后端统一调用 DolphinScheduler 接口或网关
4. 审批通过后再发布、上线或补数

### 14.3 DolphinScheduler 的两种可落地接法

#### 方式 A：基于官方 Python SDK / API Server

如果你更希望工程实现稳一点，推荐优先考虑：

- `PyDolphinScheduler`
- 官方的远程提交 / API Server 方式

适合：

- 在后端把工作流定义转换成统一 payload
- 再通过 SDK 或远程服务提交

#### 方式 B：如果你们环境已开放 REST/OpenAPI，则直接封装 client

如果你们线上已经有统一可调用的 DolphinScheduler REST/OpenAPI 服务，也可以直接封装：

- 创建工作流
- 更新工作流
- 上线工作流
- 启动工作流
- 发起补数
- 查询实例状态

工程上推荐这样理解：

- `Dinky`：优先按官方 OpenAPI 直接集成
- `DolphinScheduler`：根据你们现网部署，在 REST/OpenAPI 与 Python SDK / API Server 之间选一个统一入口

## 15. 建议新增的业务接口

如果后续希望不完全依赖聊天文本解析，建议补一组结构化接口：

- `POST /api/v1/bigdata/dinky/sql/generate`
- `POST /api/v1/bigdata/dinky/jobs/submit`
- `POST /api/v1/bigdata/paimon/ddl/generate`
- `POST /api/v1/bigdata/ds/workflows/generate`
- `POST /api/v1/bigdata/ds/workflows/publish`
- `POST /api/v1/bigdata/ds/backfill/create`
- `POST /api/v1/bigdata/doris/ads/generate`
- `POST /api/v1/bigdata/doris/publish`
- `GET /api/v1/bigdata/tasks/{task_id}`

建议分工：

- `generate`：生成草稿
- `submit/publish/create`：真实执行
- 所有真实执行接口默认走审批

## 16. Skill 实现建议

### 16.1 第一阶段继续走本地版

沿用你前面已经确定的方向：

- Skill 存在后端本地目录
- 默认目录：`backend/data/skills/`
- 后台上传 / 创建 Skill
- Agent Profile 绑定可用 Skill

这样做的好处：

- 与当前代码完全一致
- 上线最快
- 不引入额外对象存储依赖
- 方便快速试错

### 16.2 推荐的 Skill 目录结构

```text
skill-name/
├─ SKILL.md
├─ templates/
│  ├─ ddl.sql.j2
│  ├─ flink.sql.j2
│  └─ workflow.json.j2
├─ examples/
│  └─ sample_cases.md
└─ scripts/
   ├─ validate_sql.py
   ├─ build_workflow_payload.py
   └─ submit_job.py
```

建议用途：

- `SKILL.md`：能力说明、输入要求、输出格式、约束
- `templates/`：SQL / DDL / JSON 模板
- `examples/`：最佳实践与 few-shot 示例
- `scripts/`：确实需要执行的辅助脚本

### 16.3 Skill 输出尽量结构化

推荐让 Skill 输出：

```json
{
  "task_type": "dinky_sql_generate",
  "summary": "为订单流生成 DWD 宽表 Flink SQL",
  "artifacts": {
    "sql": "...",
    "ddl": "...",
    "workflow_json": null
  },
  "risk_level": "medium",
  "requires_approval": false,
  "next_actions": [
    "review_sql",
    "submit_to_dinky"
  ]
}
```

这样更适合：

- 前端展示
- 进入审批
- 转成外部 API 请求

## 17. 审批与权限方案

### 17.1 高风险动作清单

建议默认要求审批的动作：

- 提交生产 Flink SQL 作业
- 停止 / 重启生产流任务
- 发布 DolphinScheduler 工作流
- 执行补数
- 覆盖写 Doris ADS 表
- 删表、删分区、删数据
- 执行 Skill 中的 Python 脚本

当前项目中的 `run_skill_python_script` 已经很适合作为审批入口，应继续保持默认审批开启。

### 17.2 审批摘要建议

审批时建议展示：

- 发起人
- 目标环境
- 动作类型
- 涉及平台
- 目标表 / 工作流
- SQL / DDL / DAG 摘要
- 风险提示
- 回滚建议

## 18. 审计与可观测性

建议把当前后台扩展成“数开 Agent 审计中心”。

建议记录：

- 发起人
- Agent 名称
- Skill 名称
- 请求摘要
- 生成的 SQL / DDL / DAG 摘要
- 是否进入审批
- 审批人和审批结果
- 外部平台返回结果
- 执行耗时
- 输入 Token / 输出 Token / 总 Token

建议新增统计维度：

- 按业务域统计任务量
- 按平台统计调用量：Dinky / DS / Doris
- 按动作统计：生成、发布、补数、回滚
- 按审批结果统计通过率与拒绝率
- 按失败原因做聚类统计

## 19. 分阶段实施方案

### 19.1 第一阶段：专用 Agent MVP

目标：

- 平台继续保持通用
- 上线一组只给数开团队使用的 Agent
- 跑通“生成 + 审批 + 审计”

范围：

- 新增 4 个 Skill
- 新增 3 到 4 个 Agent Profile
- 聊天中输出结构化 SQL / DDL / DAG 方案
- Dinky 可优先对接测试环境 OpenAPI
- DolphinScheduler 可先做到工作流定义生成与审批前置

### 19.2 第二阶段：测试环境可执行

目标：

- 数开 Agent 套件接入 Dinky、DolphinScheduler、Doris 测试环境

范围：

- 新增 integration clients
- 新增提交、发布、补数接口
- 审批通过后真实执行
- 后台沉淀外部平台返回结果

### 19.3 第三阶段：生产灰度

目标：

- 限制团队、限制环境、限制动作类型，灰度接入生产

范围：

- 仅部分团队可用
- 仅部分动作可达生产
- 高风险动作全量审批
- 增加回滚模板、操作保护和频控

## 20. 最值得优先做的三个场景

### 场景 1：实时数仓开发助手

输入：

- “帮我把订单 CDC 加工成 DWD 宽表，并输出 Flink SQL”

输出：

- Paimon DWD 表 DDL
- Flink SQL 草稿
- 字段说明
- 提交到 Dinky 的下一步动作

### 场景 2：补数与调度助手

输入：

- “帮我把 4 月份这条链路做补数方案，并生成 DolphinScheduler DAG”

输出：

- 补数范围
- 工作流节点
- 依赖关系
- 风险提示
- 审批单

### 场景 3：ADS 发布助手

输入：

- “把交易成功金额、支付转化率做成 ADS，供运营日报查询”

输出：

- ADS 表设计
- Doris 建表建议
- 导入策略
- 指标口径说明

## 21. 对当前项目的具体改造建议

后端建议优先改造：

- `backend/app/services/skill_service.py`
  - 增强 Skill 元数据，如 `domain`、`task_type`、`risk_level`
- `backend/app/services/agent_service.py`
  - 增强结构化结果识别与执行动作路由
- `backend/app/services/tool_config_service.py`
  - 增加大数据执行动作的审批配置
- `backend/app/api/v1/endpoints/`
  - 新增 `bigdata.py` 或拆分为 `dinky.py`、`dolphinscheduler.py`、`doris.py`

前端建议优先改造：

- 智能体配置页：支持数开 Agent 配置与 Skill 绑定
- 审批中心：支持查看结构化发布单、补数单、回滚单
- 会话详情页：支持查看 SQL / DDL / DAG 等产物
- Agent 可见范围控制：只让目标用户看到这组 Agent

## 22. 风险与边界

1. AI 生成 SQL 不等于可直接生产发布  
   必须有人审阅，至少前期如此。

2. 平台保持通用，不要为单一行业能力污染全局设计  
   数开能力应作为 Agent 套件接入，而不是改写整个产品定位。

3. 外部平台调用要尽量收敛到后端集成层  
   不建议让 Skill 脚本直接分散调用生产系统。

4. 当前项目适合做控制层与集成层，不适合做执行引擎  
   不要把重型执行逻辑塞进 AgenticOS 内部。

5. Skill 脚本执行依旧是高风险点  
   必须默认审批，并限制执行范围。

## 23. 最终建议

最推荐的路线是：

1. 保持 `AgenticOS` 的通用平台定位不变
2. 以 Agent 套件形式新增数开专用 Agent
3. 第一阶段先做本地 Skill + 结构化生成 + 审批审计
4. `Dinky` 优先按官方 OpenAPI 对接，尽快做成可执行链路
5. `DolphinScheduler` 根据你们现网情况，在 REST/OpenAPI 与 Python SDK / API Server 之间选一个统一入口
6. 所有生产动作继续纳入审批和审计
7. 优先做实时 SQL 生成、补数流程生成、ADS 发布建议三个场景

## 24. 参考资料

以下资料用于确认平台能力边界与推荐接法：

- Dinky 官方站点：https://www.dinky.org.cn/
- Dinky OpenAPI 概览：https://www.dinky.org.cn/docs/1.0/openapi/openapi_overview/
- Apache Paimon 官方文档：https://paimon.apache.org/docs/
- Paimon Flink CDC Ingestion：https://paimon.apache.org/docs/master/flink/cdc-ingestion/overview/
- Apache DolphinScheduler 官方站点：https://dolphinscheduler.apache.org/
- DolphinScheduler Python Task / SDK 文档：https://dolphinscheduler.apache.org/python/main/tasks/index.html
- DolphinScheduler 远程提交 / API Server 文档：https://dolphinscheduler.apache.org/python/stable/howto/remote-submit.html
- Apache Doris 官方文档：https://doris.apache.org/docs/
- Doris Paimon Catalog：https://doris.apache.org/docs/lakehouse/catalogs/paimon-catalog/
- Doris + Paimon 最佳实践：https://doris.apache.org/docs/lakehouse/best-practices/doris-paimon/
