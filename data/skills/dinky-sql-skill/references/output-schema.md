# 输出结构

当用户要求输出可复用草稿时，返回结构化结果。

## 推荐结构

```json
{
  "task_type": "dinky_sql_generate",
  "summary": "Build a DWD realtime order wide-table job",
  "artifacts": {
    "target_ddl": "",
    "flink_sql": "",
    "dinky_job_payload": {}
  },
  "runtime": {
    "parallelism": 2,
    "checkpoint_ms": 300000,
    "state_ttl": "7 d"
  },
  "risks": [],
  "requires_approval": false,
  "next_actions": [
    "review_sql",
    "submit_to_dinky"
  ]
}
```

## 说明

- SQL 要尽量可执行，不要输出伪代码式 SQL。
- DDL 和 DML 最好分开输出。
- `dinky_job_payload` 只作为草稿，不代表已经执行。
- 如果涉及生产发布、重启等动作，`requires_approval` 应标记为 `true`。
