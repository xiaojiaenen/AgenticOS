"""
cdgfs —— 透明加密环境下读写加密 Office/PDF 文件的 Python 客户端。

用法：把你的 open() / save() 换成 cdgfs 的等价调用即可，排版零损失，
因为搬的是完整原始文件字节，不是抽出来的内容。

    import cdgfs
    raw = cdgfs.read_bytes(r'D:\\Data\\排班表.xlsx')
    wb  = openpyxl.load_workbook(io.BytesIO(raw))
    ...
    buf = io.BytesIO(); wb.save(buf)
    cdgfs.write_bytes(r'D:\\Data\\排班表.xlsx', buf.getvalue())

要求：rundll32.exe 已加载 bridge.dll（见 start_bridge.py 或 README）。
"""

from __future__ import annotations

import io
import os
import struct
import subprocess
import sys
import time
import uuid

PIPE_NAME = os.environ.get("CDG_BRIDGE_PIPE", "cdgbridge")


class BridgeError(OSError):
    """桥返回 ERR，或管道不可用。"""


# --------------------------------------------------------------------------- 低层

def _pipe_path(name: str) -> str:
    return "\\\\.\\pipe\\" + name


def _connect(name: str, timeout: float = 5.0):
    """打开管道连接，带重试（宿主刚启动时可能还没建好管道）。"""
    import time as _t

    deadline = _t.time() + timeout
    last = None
    while _t.time() < deadline:
        try:
            return open(_pipe_path(name), "r+b", buffering=0)
        except (FileNotFoundError, OSError) as e:
            last = e
            _t.sleep(0.05)
    raise BridgeError(
        f"连不上管道 {name!r}：{last}\n"
        f"先确认 bridge.dll 已加载："
        f"rundll32.exe \"<path>\\bridge.dll\",Start"
    )


def _readline(f) -> str:
    buf = bytearray()
    while True:
        c = f.read(1)
        if not c:
            raise BridgeError("管道在读行时断开")
        if c == b"\n":
            break
        if c != b"\r":
            buf += c
    return buf.decode("utf-8")


def _expect_ok(hdr: str):
    if hdr.startswith("OK"):
        parts = hdr.split("\t")
        return parts
    if hdr.startswith("ERR"):
        parts = hdr.split("\t")
        code = parts[1] if len(parts) > 1 else "?"
        msg = parts[2] if len(parts) > 2 else "error"
        raise BridgeError(f"桥返回错误 code={code}: {msg}")
    raise BridgeError(f"协议错误，收到：{hdr!r}")


def _read_exact(f, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        c = f.read(n - len(buf))
        if not c:
            raise BridgeError(f"数据被截断：期望 {n} 字节，收到 {len(buf)}")
        buf += c
    return bytes(buf)


def _send_line(f, s: str):
    f.write(s.encode("utf-8") + b"\n")


# --------------------------------------------------------------------------- 公共 API

def ping(name: str = PIPE_NAME) -> dict:
    """检查桥是否在线，返回 {pid, exe}。"""
    with _connect(name) as f:
        _send_line(f, "PING")
        parts = _expect_ok(_readline(f))
        return {"pid": int(parts[2]), "exe": parts[3]}


def info(name: str = PIPE_NAME) -> dict:
    with _connect(name) as f:
        _send_line(f, "INFO")
        parts = _expect_ok(_readline(f))
        out = {}
        for kv in parts[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                out[k] = v
        return out


def read_bytes(path: str | os.PathLike, name: str = PIPE_NAME) -> bytes:
    """读取完整明文原始文件字节（排版 100% 保留）。"""
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"READ\t{p}")
        parts = _expect_ok(_readline(f))
        n = int(parts[1])
        return _read_exact(f, n)


def read_chunk(path, offset: int, length: int, name: str = PIPE_NAME) -> bytes:
    """分块读取，适合超大文件。"""
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"READCHUNK\t{p}\t{offset}\t{length}")
        parts = _expect_ok(_readline(f))
        n = int(parts[1])
        return _read_exact(f, n)


def write_bytes(path, data: bytes, name: str = PIPE_NAME) -> None:
    """写回目标路径。落在加密目录时驱动会自动加密成合法密文。"""
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"WRITE\t{p}\t{len(data)}")
        f.write(data)
        _expect_ok(_readline(f))


def head(path, n: int = 16, name: str = PIPE_NAME) -> bytes:
    """读文件头，用于判定明文/密文。返回 hex 字符串。"""
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"HEAD\t{p}\t{n}")
        parts = _expect_ok(_readline(f))
        return parts[1]


def stat(path, name: str = PIPE_NAME) -> dict:
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"STAT\t{p}")
        parts = _expect_ok(_readline(f))
        return {
            "size": int(parts[1]),
            "atime": int(parts[2]),
            "mtime": int(parts[3]),
            "ctime": int(parts[4]),
            "attr": int(parts[5]),
        }


def listdir(directory, pattern: str = "*", name: str = PIPE_NAME) -> list[dict]:
    p = os.path.abspath(os.fspath(directory))
    with _connect(name) as f:
        _send_line(f, f"LIST\t{p}\t{pattern}")
        parts = _expect_ok(_readline(f))
        n = int(parts[1])
        out = []
        for _ in range(n):
            row = _readline(f).split("\t")
            out.append({
                "name": row[0],
                "size": int(row[1]),
                "mtime": int(row[2]),
                "attr": int(row[3]),
            })
        return out


def copy(src, dst, name: str = PIPE_NAME) -> None:
    s = os.path.abspath(os.fspath(src))
    d = os.path.abspath(os.fspath(dst))
    with _connect(name) as f:
        _send_line(f, f"COPY\t{s}\t{d}")
        _expect_ok(_readline(f))


def remove(path, name: str = PIPE_NAME) -> None:
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"DEL\t{p}")
        _expect_ok(_readline(f))


def mkdir(path, name: str = PIPE_NAME) -> None:
    p = os.path.abspath(os.fspath(path))
    with _connect(name) as f:
        _send_line(f, f"MKDIR\t{p}")
        _expect_ok(_readline(f))


def quit_bridge(name: str = PIPE_NAME) -> None:
    with _connect(name) as f:
        _send_line(f, "QUIT")
        try:
            _readline(f)
        except BridgeError:
            pass


# --------------------------------------------------------------------------- 判定

_PLAIN_MAGIC = {
    "50 4B 03 04": "OOXML/zip plain (xlsx/docx/pptx)",
    "D0 CF 11 E0": "OLE2 plain (xls/doc/ppt)",
    "25 50 44 46": "PDF plain",
    "50 4B 05 06": "zip empty archive",
}


def classify(path, name: str = PIPE_NAME) -> tuple[str, str]:
    """
    判定文件是明文还是密文。返回 (kind, detail)，kind ∈ {plain, cipher, unknown}。
    """
    h = head(path, 16, name).upper()
    for magic, desc in _PLAIN_MAGIC.items():
        if h.startswith(magic):
            return "plain", desc
    if h in ("", "<empty>"):
        return "unknown", "empty or unreadable"
    return "cipher", f"unknown magic: {h}"


# --------------------------------------------------------------------------- 便捷封装

class File(io.RawIOBase):
    """
    像普通文件一样用：

        with cdgfs.File(r'D:\\Data\\a.xlsx', 'rb') as f:
            raw = f.read()

        with cdgfs.File(r'D:\\Data\\a.xlsx', 'wb') as f:
            f.write(buf.getvalue())
    """

    def __init__(self, path, mode: str = "rb", name: str = PIPE_NAME):
        self.path = os.path.abspath(os.fspath(path))
        self.mode = mode
        self._pipe = name
        self._closed = False
        if "r" in mode:
            self._data = read_bytes(self.path, name)
            self._pos = 0
        elif "w" in mode:
            self._data = bytearray()
            self._pos = 0
        else:
            raise ValueError("mode 只支持 r / w")

    def readable(self) -> bool:
        return "r" in self.mode

    def writable(self) -> bool:
        return "w" in self.mode

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            out = self._data[self._pos:]
            self._pos = len(self._data)
            return bytes(out)
        out = self._data[self._pos:self._pos + n]
        self._pos += len(out)
        return bytes(out)

    def readinto(self, b) -> int:
        chunk = self.read(len(b))
        b[:len(chunk)] = chunk
        return len(chunk)

    def write(self, b) -> int:
        self._data += b
        self._pos += len(b)
        return len(b)

    def seek(self, pos: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = pos
        elif whence == 1:
            self._pos += pos
        elif whence == 2:
            self._pos = len(self._data) + pos
        return self._pos

    def tell(self) -> int:
        return self._pos

    def close(self):
        if self._closed:
            return
        self._closed = True
        if "w" in self.mode:
            write_bytes(self.path, bytes(self._data), self._pipe)
        super().close()


# --------------------------------------------------------------------------- 启动宿主

DEFAULT_HOSTS = [
    "rundll32.exe",
    "dllhost.exe",
    "explorer.exe",
]


def start(dll_path: str, pipe_name: str = PIPE_NAME, host: str = "rundll32.exe") -> int:
    """
    启动宿主进程并加载 bridge.dll。返回进程 PID。

        cdgfs.start(r'D:\\Tools\\cdg-bridge\\bin\\bridge.dll')
    """
    dll = os.path.abspath(dll_path)
    if not os.path.isfile(dll):
        raise FileNotFoundError(dll)

    # rundll32 的参数必须是「<dll>,<入口> <额外参数>」整体一个字符串，
    # 用 shell 形式拼接最稳（列表形式会让引号被吃掉）
    cmdline = f'{host} "{dll}",Start {pipe_name}'
    p = subprocess.Popen(cmdline, shell=False, close_fds=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         executable=None)

    # 等管道就绪
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            ping(pipe_name)
            return p.pid
        except BridgeError:
            time.sleep(0.1)
    raise BridgeError(f"{host} 启动后管道 {pipe_name!r} 一直没就绪，pid={p.pid}")


def ensure(dll_path: str, pipe_name: str = PIPE_NAME) -> int:
    """已在线就直接返回，否则启动。"""
    try:
        return ping(pipe_name)["pid"]
    except BridgeError:
        return start(dll_path, pipe_name)
