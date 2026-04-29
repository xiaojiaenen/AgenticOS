# 实时开发模式

## CDC 到 DWD

- 保留业务主键。
- 明确 sink 是 append 还是 upsert。
- 对删除和更新语义要明确说明。
- 脏数据处理方式要清楚可见。

## 维表 join

- 写清 join key 和时间语义。
- 说明维表是 lookup、broadcast，还是来自 CDC。
- 如果 join 可能造成数据膨胀，要主动提示风险。

## 窗口聚合

- 写清时间字段。
- 写清窗口大小和 watermark 假设。
- 说明迟到数据如何处理。

## 交付检查清单

- 确认目标表 DDL。
- 确认 sink 语义。
- 确认 checkpoint 和 parallelism 默认值。
- 确认任务面向的是 dev、test 还是 prod。
