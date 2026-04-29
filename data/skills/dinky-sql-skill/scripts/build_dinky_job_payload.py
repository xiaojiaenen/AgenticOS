from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Dinky job payload draft.")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--sql-file", required=True)
    parser.add_argument("--database", default="")
    parser.add_argument("--folder-id", type=int, default=0)
    parser.add_argument("--cluster-id", type=int, default=0)
    parser.add_argument("--environment-id", type=int, default=0)
    parser.add_argument("--parallelism", type=int, default=2)
    parser.add_argument("--checkpoint-ms", type=int, default=300000)
    parser.add_argument("--target-env", default="test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sql = Path(args.sql_file).read_text(encoding="utf-8").strip()
    payload = {
        "job_name": args.job_name,
        "folder_id": args.folder_id,
        "dialect": "FlinkSQL",
        "type": "SQL",
        "cluster_id": args.cluster_id,
        "environment_id": args.environment_id,
        "database": args.database,
        "sql": sql,
        "config": {
            "parallelism": args.parallelism,
            "checkpoint_ms": args.checkpoint_ms,
            "savepoint_strategy": "latest",
        },
        "target_env": args.target_env,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
