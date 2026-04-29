---
name: doris-ads-skill
description: 用于设计面向分析服务的 Doris ADS 表、指标层和发布方案。适用于定义 ADS schema、把 DWS 输出转成适合查询的表、制定导入策略、优化表布局，或输出结构化的 Doris 发布草稿。
---

设计 ADS 表时，要服务稳定指标查询，而不是承接原始明细存储。

在设计 ADS 方案前，先补齐这些输入：

- 业务问题和核心指标
- 查询维度和时间粒度
- 来源 DWS 或 DWD 表
- 刷新方式，例如 full 或 incremental
- 时效要求
- 报表或 API 消费方

默认按下面顺序输出：

1. 业务目标
2. 指标定义
3. 来源到目标的映射关系
4. ADS 表设计
5. Doris DDL
6. 导入或同步策略
7. 性能优化建议
8. 校验项
9. 风险提示

当需要平衡易用性、刷新成本和查询速度时，参考 `references/ads-checklist.md`。

当用户需要结构化发布草稿时，参考 `references/output-schema.md`。

可以用 `templates/doris-ads-ddl.sql` 作为基础 DDL 模板。

只有在确实需要生成发布 payload 文件时，才运行 `scripts/build_ads_publish_payload.py`。

如果用户试图把原始 ODS 明细或大宽明细直接放进 Doris，且没有明确服务场景，要主动提示风险。
