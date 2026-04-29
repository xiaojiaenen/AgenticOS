---
name: dinky-sql-skill
description: 用于生成、审查和修正面向 Dinky 的 Flink SQL 任务。适用于把业务需求转成可执行的 Flink SQL、设计 DWD 或 DWS 实时任务、排查 SQL 报错、整理运行参数，或输出结构化的 Dinky 任务提交草稿。
---

生成面向 Dinky 的 Flink SQL，并让结果适合后续审阅、审批和 API 执行。

在写 SQL 前，先补齐缺失信息：

- 来源表和关键字段
- 目标分层，例如 ODS、DWD、DWS
- 事件时间字段和乱序容忍范围
- upsert 还是 append 语义
- sink 目标以及预期分区方式
- 环境信息，例如 dev、test、prod

默认按下面顺序输出：

1. 任务目标
2. 前提假设
3. 来源表和目标表
4. 如有需要，补充目标表 DDL
5. Flink SQL
6. 运行参数建议
7. Dinky 提交草稿
8. 校验清单
9. 风险与审批建议

当涉及窗口、join、去重、迟到数据时，优先参考 `references/realtime-patterns.md`。

当用户需要结构化 JSON 输出或执行草稿时，参考 `references/output-schema.md`。

后续如果要对接后端执行，可使用 `templates/dinky-job-payload.json` 作为 payload 结构参考。

只有在确实需要生成 payload 文件时，才运行 `scripts/build_dinky_job_payload.py`。脚本执行应视为受控动作，因为可能需要审批。

除非外部 API 真正调用成功，否则不要声称任务已经提交、发布或重启。

凡是涉及生产写入、运行参数变更、任务重发或重新发布，都应进入审批。
