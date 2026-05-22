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
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)


if __name__ == "__main__":
    main()
