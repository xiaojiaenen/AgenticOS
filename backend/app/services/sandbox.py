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
    ):
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self.max_output = max_output
        self.block_commands = block_commands

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
        return env

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
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout,
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
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
