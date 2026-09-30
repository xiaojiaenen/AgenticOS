"""Start ARQ worker (foreground-safe script for Start-Process)."""
from arq import run_worker

from app.services.task_queue import WorkerSettings

if __name__ == "__main__":
    run_worker(WorkerSettings)
