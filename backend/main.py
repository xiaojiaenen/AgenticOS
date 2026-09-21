import os
import sys
from pathlib import Path

import uvicorn

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# Let uvicorn reload workers import app.main correctly
os.environ.setdefault("PYTHONPATH", str(BACKEND_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Change cwd to project root so that wuwei file tools resolve
# data/websites/ paths correctly.
os.chdir(str(PROJECT_ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    # 支持通过环境变量配置 worker 数量（高并发场景）
    # 注意：多 worker 需要 Redis 支持（审批 pub/sub 等）
    workers = int(os.environ.get("UVICORN_WORKERS", "1"))
    reload = workers == 1  # 多 worker 时禁用 reload
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8001"))
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if workers > 1 else None,
        timeout_keep_alive=300,
    )


if __name__ == "__main__":
    main()
