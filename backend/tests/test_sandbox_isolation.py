"""沙箱真隔离后端回归（docs/design/系统改造总方案.md 5.2「安全底线」）。

三层防御契约：
1. 命令黑名单在**所有模式**（含真隔离）下都先于执行生效（纵深防御）；
2. ``SANDBOX_BACKEND`` 解析：auto 探测 / none 显式关闭 / 显式后端缺失时
   安全退档 + 告警（绝不裸跑在更高权限下）；
3. 真隔离 argv 构造：bwrap 根只读 + 工作区可写 + 环境逐项回灌；
   nsjail rlimits + 系统目录只读绑定。
真 jail 的运行时行为属 Linux 容器/CI 范畴（本机 macOS 无法执行），由
argv 构造正确性 + 退档逻辑锁定。
"""

from __future__ import annotations

import platform
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.sandbox import (
    Sandbox,
    build_isolation_argv,
    detect_available_backend,
    resolve_backend,
)


@pytest.fixture()
def workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".tmp").mkdir(parents=True)
    return ws


# ── 后端解析 ──────────────────────────────────────────────────────────


def test_resolve_auto_on_macos_falls_back_to_none():
    with patch("app.services.sandbox.platform.system", return_value="Darwin"):
        assert resolve_backend("auto") == "none"


def test_resolve_none_is_explicit():
    assert resolve_backend("none") == "none"


def test_resolve_explicit_backend_missing_binary_degrades_safely(monkeypatch):
    """显式指定 nsjail 但二进制缺失 → 安全退档 none + 告警，绝不裸跑。"""
    monkeypatch.setattr("app.services.sandbox.platform", SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setattr("app.services.sandbox.shutil.which", lambda name: None)
    assert resolve_backend("nsjail") == "none"
    assert resolve_backend("bubblewrap") == "none"


def test_resolve_unknown_backend_falls_back():
    assert resolve_backend("firecracker") == "none"  # 未知值按 none 处理


def test_detect_available_backend_non_linux(monkeypatch):
    monkeypatch.setattr("app.services.sandbox.platform", SimpleNamespace(system=lambda: "Darwin"))
    assert detect_available_backend() is None


def test_detect_available_backend_linux_prefers_nsjail(monkeypatch):
    monkeypatch.setattr("app.services.sandbox.platform", SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setattr("app.services.sandbox.shutil.which", lambda name: "/usr/bin/whatever")
    assert detect_available_backend() == "nsjail"


# ── 真隔离 argv 构造 ──────────────────────────────────────────────────


def test_bwrap_argv_root_readonly_workspace_writable(tmp_path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    argv, exec_env = build_isolation_argv("bubblewrap", tmp_path, env)
    assert argv[0] == "bwrap"
    assert "--unshare-all" in argv and "--share-net" in argv  # 隔离进程，保留 npm 网络
    # 根整体只读 + 工作区可写
    assert argv[argv.index("--ro-bind") + 1] == "/"
    ws_bind = argv[argv.index("--bind") + 1]
    assert str(tmp_path.resolve()) == ws_bind
    # 环境变量逐项回灌（--clearenv 后）
    assert argv[argv.index("--clearenv") + 1] == "--setenv"
    assert exec_env == env
    # 最终落到 sh -c
    assert argv[-3:] == ["--", "/bin/sh", "-c"]


def test_nsjail_argv_rlimits_and_readonly_binds(tmp_path):
    argv, exec_env = build_isolation_argv("nsjail", tmp_path, {"PATH": "/bin"})
    assert argv[0] == "nsjail"
    assert "--disable_clone_newnet" in argv  # 保留网络（npm install 需要）
    # rlimits 限制资源
    for flag in ("--rlimit_as", "--rlimit_nofile", "--rlimit_fsize"):
        assert flag in argv
    # 系统目录只读绑定、工作区读写绑定
    from app.services.sandbox import _SYSTEM_RO_DIRS

    ro_positions = [i for i, a in enumerate(argv) if a == "-R"]
    assert {argv[i + 1] for i in ro_positions} == set(_SYSTEM_RO_DIRS)
    ws_pos = argv.index("-B")
    assert argv[ws_pos + 1] == str(tmp_path.resolve())
    assert exec_env == {"PATH": "/bin"}
    assert argv[-3:] == ["--", "/bin/sh", "-c"]


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        build_isolation_argv("firecracker", __import__("pathlib").Path("/tmp"), {})


# ── 黑名单在所有模式都先生效 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_blocklist_applies_even_with_isolation_backend(workspace, monkeypatch):
    """真隔离模式下危险命令仍被黑名单拒绝（第一层防线不因后端而豁免）。"""
    # macOS 上显式 nsjail 会被 resolve 退档；这里直接钉住后端以单测黑名单分层
    monkeypatch.setattr(Sandbox, "__init__", Sandbox.__init__)
    sandbox = Sandbox(workspace, backend="none")
    sandbox.backend = "nsjail"
    result = await sandbox.execute("sudo rm -rf / --no-preserve-root")
    assert result.success is False
    assert "Blocked" in result.stderr
    assert result.backend == "nsjail"  # 声明了后端，但黑名单先行拦截


@pytest.mark.asyncio
async def test_none_backend_executes_and_reports_backend(workspace):
    sandbox = Sandbox(workspace, backend="none")
    result = await sandbox.execute("echo ok")
    assert result.success is True
    assert result.stdout.strip() == "ok"
    assert result.backend == "none"


@pytest.mark.asyncio
async def test_default_backend_resolution_on_this_host(workspace):
    """默认构造在 macOS 上自动落到 none 档（真隔离在 Linux CI 生效）。"""
    sandbox = Sandbox(workspace)
    expected = "none" if platform.system() != "Linux" else sandbox.backend
    assert sandbox.backend == expected
