# 输出结构

```json
{
  "task_type": "ds_workflow_generate",
  "summary": "Build a T+1 offline workflow from DWD to ADS",
  "artifacts": {
    "workflow_definition": {},
    "backfill_plan": {}
  },
  "schedule": {
    "cron": "",
    "timezone": "Asia/Shanghai",
    "retries": 1
  },
  "risks": [],
  "requires_approval": false,
  "next_actions": [
    "review_workflow",
    "publish_to_dolphinscheduler"
  ]
}
```
