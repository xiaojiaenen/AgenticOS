---
name: ds-workflow-skill
description: 用于生成和审查 DolphinScheduler 工作流、补数方案、任务依赖和调度配置。适用于把离线数仓需求转成工作流 DAG、设计补数方案、安排任务顺序，或输出结构化的 DolphinScheduler 发布草稿。
---

生成适合审阅、审批，并可在后续通过受控 API 发布的离线工作流草稿。

在设计工作流前，先补齐这些输入：

- 工作流目标
- 上下游表
- 调度周期
- 如果有补数，补数日期范围
- 失败处理和重试要求
- 环境和负责人

默认按下面顺序输出：

1. 工作流目标
2. 前提假设
3. 节点列表
4. 依赖关系
5. 调度和重试配置
6. 如有需要，补充补数策略
7. 工作流发布草稿
8. 校验清单
9. 审批建议

当需要确定任务顺序、重试策略、补数策略时，参考 `references/workflow-checklist.md`。

当用户需要结构化 DAG 或发布草稿时，参考 `references/output-schema.md`。

可以用 `templates/workflow-definition.json` 作为基础结构模板。

只有在确实需要生成 payload 文件时，才运行 `scripts/build_workflow_payload.py`。

除非外部 API 真正调用成功，否则不要声称工作流已经创建、发布或启动。

发布、上线、重跑、补数等动作默认都应进入审批。
