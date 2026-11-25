"""进程沙箱：跑不可信命令的隔离执行层（战线 B / 总方案 5.2「安全底线」）。

三层防御（按序生效，缺一不可）：

1. **命令黑名单**（所有模式都保留，纵深防御）—— 危险模式直接拒绝；
2. **真隔离后端**（可选，Linux 生效）—— ``SANDBOX_BACKEND`` 声明式选择：
   - ``nsjail``：进程级 jail（mount namespace + rlimits），系统目录只读，
     仅工作区可写；
   - ``bubblewrap``：bwrap 用户态沙箱（unshare 进程/IPC/mount，保留网络
     供 npm install 使用）；
   - ``auto``（默认）：Linux 上检测到任一可用后端即启用，否则退到第 3 层；
   - ``none``：显式关闭（macOS 开发机无上述工具时 auto 自然落到此档）。
3. **轻量遏制**（永远生效）—— 工作区路径遏制、超时 + 进程组击杀、输出
   截断、敏感环境变量剥离。

为什么网络保留：沙箱的唯一生产用途是 ``npm install && npm run build``
（website_tools），断网会让构建必败；网络策略属于网络层防线（出站白名单
是独立议题），这里隔离的是**文件系统与进程**。
"""

import asyncio
import logging
import os
import platform
import re
import shutil
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
    backend: str = "none"
    """实际使用的隔离后端（"none" = 仅正则黑名单 + 轻量遏制）。"""


# ── 真隔离后端（战线 B）────────────────────────────────────────────────

#: 系统目录以只读方式挂进沙箱（npm/node 与其依赖需要读这些路径）
_SYSTEM_RO_DIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/ssl", "/etc/resolv.conf")


def detect_available_backend() -> Optional[str]:
    """探测本机可用的真隔离后端；仅 Linux 生效，返回 None = 无可用后端。"""
    if platform.system() != "Linux":
        return None
    for name in ("nsjail", "bwrap"):
        if shutil.which(name):
            return "nsjail" if name == "nsjail" else "bubblewrap"
    return None


def resolve_backend(explicit: Optional[str] = None) -> str:
    """把 ``SANDBOX_BACKEND`` 配置解析成实际后端。

    - ``auto``：Linux 上检测到 nsjail/bwrap 用之，否则 ``none``；
    - ``none``：仅正则黑名单 + 轻量遏制；
    - ``nsjail`` / ``bubblewrap``：显式指定；二进制缺失时告警并退回 ``none``
      （绝不因隔离层配置错误而让命令裸跑在更高权限下 —— 退档 + 显眼告警）。
    """
    from app.core.config import get_settings

    backend = (explicit or getattr(get_settings(), "sandbox_backend", "auto") or "auto").lower()
    if backend == "auto":
        return detect_available_backend() or "none"
    if backend == "none":
        return "none"
    if backend in {"nsjail", "bubblewrap"}:
        binary = "nsjail" if backend == "nsjail" else "bwrap"
        if platform.system() != "Linux":
            _logger.warning(
                "SANDBOX_BACKEND=%s 仅支持 Linux（当前 %s），退回 none 档；"
                "生产环境请把后端部署在 Linux 容器中以启用真隔离",
                backend, platform.system(),
            )
            return "none"
        if not shutil.which(binary):
            _logger.warning(
                "SANDBOX_BACKEND=%s 但 %s 未安装，退回 none 档；请安装后重启服务",
                backend, binary,
            )
            return "none"
        return backend
    _logger.warning("未知 SANDBOX_BACKEND=%r，按 none 处理", backend)
    return "none"


def build_isolation_argv(backend: str, workspace: Path, env: dict) -> tuple[list[str], dict]:
    """构造真隔离后端的命令前缀。

    Returns:
        (argv_prefix, exec_env) —— argv_prefix 拼在 ``sh -c <command>`` 之前；
        exec_env 是实际传给子进程的环境变量（bwrap --clearenv 后逐项回灌）。
    """
    workspace = str(workspace.resolve())
    if backend == "bubblewrap":
        # bwrap：unshare 进程/IPC/mount（保留网络供 npm install），根文件系统
        # 整体只读、工作区读写、/tmp 独立 tmpfs、环境变量逐项回灌。
        argv = ["bwrap", "--unshare-all", "--share-net", "--die-with-parent", "--new-session"]
        argv += ["--ro-bind", "/", "/"]
        argv += ["--bind", workspace, workspace]
        argv += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
        argv += ["--clearenv"]
        for key, value in env.items():
            argv += ["--setenv", key, value]
        argv += ["--", "/bin/sh", "-c"]
        return argv, env
    if backend == "nsjail":
        # nsjail：-Mo 一次性模式；mount namespace 隔离文件系统（系统目录只读、
        # 工作区可写）；保留网络（--disable_clone_newnet）；rlimits 限制资源。
        argv = ["nsjail", "-Mo", "--quiet", "--disable_clone_newnet"]
        argv += ["--rlimit_as", "4096", "--rlimit_nofile", "512", "--rlimit_fsize", "2048"]
        argv += ["--rlimit_cpu", "3600"]
        argv += ["--chroot", "/"]
        for ro in _SYSTEM_RO_DIRS:
            argv += ["-R", ro]
        argv += ["-B", workspace]  # 工作区读写
        argv += ["-B", "/tmp"]     # 临时目录读写
        argv += ["--", "/bin/sh", "-c"]
        return argv, env
    raise ValueError(f"unknown sandbox backend: {backend}")


class Sandbox:
    """进程沙箱（三层防御，见模块 docstring）。

    Runs commands in an isolated working directory with:
    - Command blocklist (dangerous commands rejected, all modes)
    - Optional real isolation backend (nsjail / bubblewrap, Linux)
    - Path containment (can't escape workspace)
    - Timeout enforcement + process-group kill
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
        backend: Optional[str] = None,
    ):
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self.max_output = max_output
        self.block_commands = block_commands
        # 额外环境变量。npm 等工具需要共享缓存目录，否则每个项目目录
        # 都是一份独立缓存 → 每次构建都要重新下载全部依赖。
        self.extra_env = dict(extra_env or {})
        # 真隔离后端（none = 仅正则黑名单 + 轻量遏制）
        self.backend = resolve_backend(backend)

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
                exit_code=-1, timed_out=False, backend=self.backend,
            )

        # Ensure tmp dir exists
        tmp_dir = self.workspace / ".tmp"
        tmp_dir.mkdir(exist_ok=True)

        env = self._sanitize_env()

        try:
            # 真隔离后端（nsjail/bwrap）：exec 前缀包住 ``sh -c <command>``，
            # 系统目录只读、仅工作区可写。后端缺失/非 Linux 时 resolve_backend
            # 已安全退档为 none。
            if self.backend != "none":
                argv_prefix, exec_env = build_isolation_argv(self.backend, self.workspace, env)
                cmd_argv = [*argv_prefix, command]
                _logger.info("sandbox backend=%s cmd=%r", self.backend, command[:120])
                proc = await asyncio.create_subprocess_exec(
                    *cmd_argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.workspace),
                    env=exec_env,
                    start_new_session=True,
                )
            else:
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
                # 不能用 `proc.returncode or -1`：`0` 是合法的退出码（成功），
                # `or` 会把 0 当成假值改写成 -1，于是「npm install 成功」被报成
                # 「失败（退出码 -1）」，调用方据此清 node_modules 反复重来。
                # returncode 为 None 只出现在进程没有正常退出时，那才是 -1。
                exit_code=proc.returncode if proc.returncode is not None else -1,
                timed_out=timed_out,
                backend=self.backend,
            )

        except Exception as e:
            return SandboxResult(
                success=False, stdout="", stderr=str(e),
                exit_code=-1, timed_out=False, backend=self.backend,
            )
