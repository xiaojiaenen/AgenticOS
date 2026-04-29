from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a DolphinScheduler workflow payload draft.")
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--tasks-file", required=True)
    parser.add_argument("--cron", default="")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--target-env", default="test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tasks = json.loads(Path(args.tasks_file).read_text(encoding="utf-8"))
    payload = {
        "workflow_name": args.workflow_name,
        "tenant": args.tenant,
        "target_env": args.target_env,
        "schedule": {
            "cron": args.cron,
            "timezone": "Asia/Shanghai",
            "retries": args.retries,
        },
        "tasks": tasks,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
