from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Doris ADS publish payload draft.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--ddl-file", required=True)
    parser.add_argument("--refresh-mode", default="incremental")
    parser.add_argument("--owner", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = {
        "database": args.database,
        "table_name": args.table_name,
        "ddl": Path(args.ddl_file).read_text(encoding="utf-8").strip(),
        "refresh_mode": args.refresh_mode,
        "owner": args.owner,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
