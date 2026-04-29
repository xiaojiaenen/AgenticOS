---
name: paimon-model-skill
description: 用于设计面向 ODS、DWD、DWS 的 Paimon 表和分层模型。适用于确定主键、分区、bucket、merge 策略、schema 演进规则，或把业务需求转成 Paimon 的表设计与 DDL。
---

设计 Paimon 数据模型时，要明确分层、写入语义和下游使用方式。

在给出 DDL 前，先补齐这些输入：

- 业务粒度
- primary key 或 unique key
- append 还是 upsert 语义
- 分区策略
- 下游消费方
- 预期的 schema 变更频率

默认按下面顺序输出：

1. 业务目标
2. 推荐分层
3. 表粒度
4. 主键和分区设计
5. Paimon DDL
6. 写入和 merge 策略
7. schema 演进建议
8. 数据质量检查项
9. 风险提示

在决定主键、分区和演进策略时，参考 `references/modeling-checklist.md`。

当用户需要可落库、可执行的结构化产物时，参考 `references/output-schema.md`。

可以用 `templates/paimon-table-ddl.sql` 作为 DDL 基础模板。

不要凭空补太多无法从需求中推导出的属性。

如果用户把明细层存储诉求和 ADS 服务层诉求混在一起，要明确提醒。
