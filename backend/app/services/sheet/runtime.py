"""Univer 无头表格运行时的 Python 侧驱动。

`backend/sheet-runtime/server.mjs` 是一个常驻 Node 进程，本模块负责拉起它、
按行 JSON 收发请求、并管理它出问题时重启。

为什么常驻而不是每次现起：agent 一轮对话会连续调用
「建表 → 写区域 → 设公式 → 构建」，工作簿状态必须跨调用保持，
而 Univer 的单元是无状态的（每次 createWorkbook 都是一张空表）。

并发模型：单进程 + 串行队列。Univer 的工作簿状态不是并发安全的，
而 agent 工具本来就是顺序调用的，用并发换不来吞吐。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.sheet.runtime")

# backend/app/services/sheet/runtime.py → backend/sheet-runtime
RUNTIME_DIR = Path(__file__).resolve().parents[3] / "sheet-runtime"
SERVER_SCRIPT = RUNTIME_DIR / "server.mjs"
NODE_MODULES = RUNTIME_DIR / "node_modules"

#: 单次请求超时。公式计算在超大表上可能偏慢，但 60s 足够覆盖正常体量。
REQUEST_TIMEOUT = float(os.environ.get("SHEET_RUNTIME_TIMEOUT", "60"))


class SheetRuntimeError(RuntimeError):
    """表格运行时不可用或调用失败。"""


class SheetRuntime:
    """一个常驻的 Node 表格运行时进程。"""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None
        self._counter = 0
        self._read_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    # ── 生命周期 ──────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """运行环境是否具备（node 可执行 + 依赖已安装）。"""
        if shutil.which("node") is None:
            return False
        return NODE_MODULES.is_dir()

    def _unavailable_reason(self) -> str:
        if shutil.which("node") is None:
            return (
                "未找到 node 可执行文件。表格模式需要 Node.js >= 20，"
                "请安装后重试，或改用其他模式。"
            )
        if not NODE_MODULES.is_dir():
            return (
                f"表格运行时依赖未安装：{NODE_MODULES} 不存在。"
                f"请在 {RUNTIME_DIR} 下执行 `npm install`。"
            )
        return "表格运行时不可用"

    def _stale(self) -> bool:
        """进程是否已经不可用（退出，或绑在另一个事件循环上）。

        子进程的管道与 reader task 都属于创建它们的那个 loop。生产环境全程
        单 loop 不会命中后半条；但测试里每个用例都是新 loop，跨用例复用就会
        让写入落进已关闭的循环、读端永不触发，表现为「第一次调用成功、
        之后全部超时」。所以要一并检测 loop 归属。
        """
        if self._process is None:
            return False
        if self._process.returncode is not None:
            return True
        return self._loop is not None and self._loop is not asyncio.get_running_loop()

    def _discard(self) -> None:
        """丢弃失效的进程句柄。不等待退出——旧 loop 已经死了，等不到。"""
        process, self._process, self._loop = self._process, None, None
        self._lock = None
        self._read_task = None
        self._pending.clear()
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass

    async def _ensure_started(self) -> asyncio.subprocess.Process:
        if self._stale():
            self._discard()
        if self._process is not None and self._process.returncode is None:
            return self._process
        if not self.available:
            raise SheetRuntimeError(self._unavailable_reason())
        if not SERVER_SCRIPT.is_file():
            raise SheetRuntimeError(f"表格运行时脚本缺失：{SERVER_SCRIPT}")

        self._loop = asyncio.get_running_loop()
        self._lock = asyncio.Lock()
        self._process = await asyncio.create_subprocess_exec(
            "node",
            str(SERVER_SCRIPT),
            cwd=str(RUNTIME_DIR),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # 大工作簿的快照 JSON 很容易超过 asyncio 默认的 64KB 行缓冲上限，
            # 超了 readline() 会抛 LimitOverrunError。这里放宽到 128MB。
            limit=128 * 1024 * 1024,
        )
        self._read_task = asyncio.create_task(self._pump_stdout())
        asyncio.create_task(self._pump_stderr())
        logger.info("表格运行时已启动 (pid=%s)", self._process.pid)
        return self._process

    async def _pump_stdout(self) -> None:
        """按行读取 stdout，把响应派发回等待中的调用方。

        必须用 readline() 而不是 read(n)：asyncio 的 read(n) 会等满 n 字节才
        返回，协议是小 JSON 行时永远等不到，直接把调用方挂死。
        """
        process = self._process
        assert process is not None and process.stdout is not None
        try:
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                self._dispatch(raw.decode("utf-8", errors="replace").strip())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - 进程异常退出
            logger.error("读取表格运行时输出失败: %s", exc)
        finally:
            self._fail_all(f"表格运行时已退出（code={process.returncode}）")

    async def _pump_stderr(self) -> None:
        """stderr 只做日志——第三方库的 console 输出都在这里，不会污染协议。"""
        process = self._process
        assert process is not None and process.stderr is not None
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            logger.debug("[univer] %s", line.decode("utf-8", errors="replace").rstrip())

    def _dispatch(self, line: str) -> None:
        if not line:
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("表格运行时输出了非 JSON 行：%s", line[:200])
            return
        future = self._pending.pop(str(message.get("id")), None)
        if future is not None and not future.done():
            future.set_result(message)

    def _fail_all(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(SheetRuntimeError(reason))
        self._pending.clear()

    async def shutdown(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()

    # ── 请求 ──────────────────────────────────────────────────────────────

    async def call(self, op: str, **args: Any) -> dict[str, Any]:
        """调用一个运行时操作，返回 result 字段。"""
        # 整个协议是串行的：Univer 状态非并发安全，且 agent 工具本就顺序调用。
        # 锁的创建在 _ensure_started 里（首次调用时才建），所以这里先起进程。
        if self._lock is None:
            await self._ensure_started()
        lock = self._lock
        if lock is None:  # pragma: no cover - _ensure_started 保证非空
            raise SheetRuntimeError("表格运行时未初始化")
        async with lock:
            # 拿锁期间可能跨了 loop（极少见），再确认一次句柄是活的
            process = await self._ensure_started()
            assert process.stdin is not None

            self._counter += 1
            request_id = f"r{self._counter}"
            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future

            payload = json.dumps(
                {"id": request_id, "op": op, "args": args}, ensure_ascii=False
            )
            try:
                process.stdin.write(payload.encode("utf-8") + b"\n")
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                self._pending.pop(request_id, None)
                self._process = None
                raise SheetRuntimeError(f"表格运行时已断开：{exc}") from exc

            try:
                message = await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
            except asyncio.TimeoutError as exc:
                self._pending.pop(request_id, None)
                raise SheetRuntimeError(
                    f"表格运行时操作 {op} 超时（>{int(REQUEST_TIMEOUT)}s）"
                ) from exc

        if message.get("ok"):
            return message.get("result") or {}
        raise SheetRuntimeError(str(message.get("error") or "未知错误"))


_runtime: SheetRuntime | None = None


def get_sheet_runtime() -> SheetRuntime:
    """获取全局表格运行时单例。进程在首次调用时才拉起。"""
    global _runtime
    if _runtime is None:
        _runtime = SheetRuntime()
    return _runtime


async def shutdown_sheet_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.shutdown()
        _runtime = None
