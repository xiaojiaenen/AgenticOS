"""Lightweight process sandbox for running untrusted commands.

Provides path containment, command blocklisting, timeout enforcement,
output truncation, and environment sanitization.

Usage:
    sandbox = Sandbox(workspace="/path/to/project")
    result = await sandbox.execute("npm install", timeout=120)
    if result.success:
        print(result.stdout)
    else:
        print(result.stderr)
"""

import asyncio
import logging
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("sandbox")

# Commands that are never allowed
_BLOCKED_COMMANDS = [
    r"\brm\s+-rf\s+/",           # rm -rf /
    r"\brm\s+-rf\s+~",           # rm -rf ~
    r"\bcurl\s+.*\|\s*sh",       # curl | sh
    r"\bwget\s+.*\|\s*sh",       # wget | sh
    r"\bpip\s+install\s+--user",  # pip install --user
    r"\bsudo\s+",                 # sudo
    r"\bchmod\s+777",             # chmod 777
    r"\bkill\s+-9\s+1",           # kill init
    r"\bshutdown\s+",             # shutdown
    r"\breboot\s+",               # reboot
    r"\bmkfs\s+",                 # format disk
    r"\bdd\s+if=",                # dd raw write
    r"\bnc\s+-l",                 # netcat listener
    r"\bpython\s+-c\s+.*import\s+os.*system",  # os.system injection
]

# Environment variables to strip (sensitive)
_SENSITIVE_ENV = {
    "OPENAI_API_KEY", "AUTH_SECRET_KEY", "DATABASE_URL",
    "REDIS_URL", "EMAIL_PASSWORD", "DOUBAO_API_KEY",
    "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "GITLAB_TOKEN",
}


@dataclass
class SandboxResult:
    """Result of a sandboxed command execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


class Sandbox:
    """Lightweight process sandbox.

    Runs commands in an isolated working directory with:
    - Path containment (can't escape workspace)
    - Command blocklist (dangerous commands rejected)
    - Timeout enforcement
    - Output truncation
    - Environment sanitization
    """

    def __init__(
        self,
        workspace: str | Path,
        timeout: int = 120,
        max_output: int = 12000,
        block_commands: bool = True,
        extra_env: dict[str, str] | None = None,
    ):
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self.max_output = max_output
        self.block_commands = block_commands
        # 额外环境变量。npm 等工具需要共享缓存目录，否则每个项目目录
        # 都是一份独立缓存 → 每次构建都要重新下载全部依赖。
        self.extra_env = dict(extra_env or {})

    def _validate_path(self, path: str) -> str:
        """Ensure resolved path stays within workspace."""
        resolved = (self.workspace / path).resolve()
        if self.workspace not in resolved.parents and resolved != self.workspace:
            raise ValueError(f"Path traversal blocked: {path} resolves outside workspace")
        return str(resolved)

    def _check_blocked(self, command: str) -> Optional[str]:
        """Check if command matches any blocked pattern."""
        if not self.block_commands:
            return None
        for pattern in _BLOCKED_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Blocked command pattern: {pattern}"
        return None

    def _sanitize_env(self) -> dict:
        """Create a clean environment without sensitive variables."""
        env = os.environ.copy()
        for key in _SENSITIVE_ENV:
            env.pop(key, None)
        # Add basic safety
        env["HOME"] = str(self.workspace)
        env["TMPDIR"] = str(self.workspace / ".tmp")
        # 调用方显式传入的环境变量（共享 npm 缓存等）
        env.update(self.extra_env)
        return env

    @staticmethod
    async def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
        """杀掉整个进程组（不只是 shell），避免子进程继续写文件。

        ``npm install`` 派生的子进程在 shell 被杀后仍会继续往 node_modules
        里写 —— 等它自己结束时，磁盘上留下的是**半截**的原生二进制
        （实测 rollup 的 ``.node`` 文件被截断，dlopen 报
        ``segment '__TEXT' extends beyond end of file``）。
        npm 之后会认为包已装好而跳过重装，于是项目永久构建失败。
        """
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            # 进程组已消失或不允许操作 —— 退回杀单个进程
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
        try:
            await proc.wait()
        except Exception:  # pragma: no cover —— wait 极少抛错
            pass

    async def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        max_output: Optional[int] = None,
    ) -> SandboxResult:
        """Execute a command in the sandbox.

        Args:
            command: Shell command to execute
            timeout: Override timeout (seconds)
            max_output: Override max output chars

        Returns:
            SandboxResult with stdout, stderr, exit_code
        """
        timeout = timeout or self.timeout
        max_output = max_output or self.max_output

        # Block check
        blocked = self._check_blocked(command)
        if blocked:
            return SandboxResult(
                success=False, stdout="", stderr=blocked,
                exit_code=-1, timed_out=False,
            )

        # Ensure tmp dir exists
        tmp_dir = self.workspace / ".tmp"
        tmp_dir.mkdir(exist_ok=True)

        env = self._sanitize_env()

        try:
            # start_new_session=True 让子进程自成进程组 —— 超时时才能连
            # npm 一起杀掉。原先只 kill shell 的话，npm 子进程会继续在后台
            # 往 node_modules 里写文件，等它被 kill 时已经留下半截的二进制。
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=env,
                start_new_session=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout,
                )
                timed_out = False
            except asyncio.TimeoutError:
                await self._kill_process_group(proc)
                timed_out = True
                stdout = b""
                stderr = f"Command timed out after {timeout} seconds".encode()

            stdout_str = stdout.decode("utf-8", errors="replace")[:max_output]
            stderr_str = stderr.decode("utf-8", errors="replace")[:max_output]

            return SandboxResult(
                success=(proc.returncode == 0),
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=proc.returncode or -1,
                timed_out=timed_out,
            )

        except Exception as e:
            return SandboxResult(
                success=False, stdout="", stderr=str(e),
                exit_code=-1, timed_out=False,
            )
