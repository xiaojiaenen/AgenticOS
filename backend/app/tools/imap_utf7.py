"""IMAP modified UTF-7 编解码（RFC 3501 §5.1.3）。

为什么需要它：IMAP 协议里含非 ASCII 字符的邮箱名（中文自定义文件夹、
Coremail/Exchange 的「项目邮件」「已发送」等）必须用 modified UTF-7
传输 —— LIST 返回的是 ``&XfJT0ZAB-`` 这样的形式，SELECT 时服务器也只
认这个形式。Python 的 imaplib **不做任何转换**，直接 decode("utf-8")
得到乱码、直接把中文 encode("utf-8") 发出去会被服务器拒绝。

与标准 UTF-7 的差别（就是这两点，别用 UTF-7 codec 代替）：
- 移位字符用 ``&`` 而不是 ``+``（字面 ``&`` 写作 ``&-``）；
- Base64 字符表里用 ``,`` 代替 ``/``，且**不带 padding**。
"""

from __future__ import annotations

import base64

_PRINTABLE = frozenset(
    chr(c) for c in range(0x20, 0x7F)  # 可直接输出的 ASCII（& 与 / 除外，见下）
)


def decode(name: str) -> str:
    """modified UTF-7 → 原文。``&XfJT0ZAB-`` → 「项目邮件」。"""
    if "&" not in name:
        return name
    out: list[str] = []
    i = 0
    n = len(name)
    while i < n:
        ch = name[i]
        if ch != "&":
            out.append(ch)
            i += 1
            continue
        # &- 是字面 &
        if i + 1 < n and name[i + 1] == "-":
            out.append("&")
            i += 2
            continue
        end = name.find("-", i + 1)
        if end == -1:
            # 未闭合（服务器实现瑕疵）：把剩余部分尽量解出来
            segment = name[i + 1:]
            i = n
        else:
            segment = name[i + 1:end]
            i = end + 1
        if not segment:
            out.append("&")
            continue
        try:
            b64 = segment.replace(",", "/")
            padding = "=" * (-len(b64) % 4)
            out.append(base64.b64decode(b64 + padding).decode("utf-16-be"))
        except Exception:  # noqa: BLE001 -- 非法段原样保留，不让整条名字炸掉
            out.append(f"&{segment}-")
    return "".join(out)


def encode(name: str) -> str:
    """原文 → modified UTF-7。「项目邮件」→ ``&XfJT0ZAB-``。"""
    if all(c in _PRINTABLE and c not in "&" for c in name):
        return name
    out: list[str] = []
    buffer: list[str] = []

    def _flush() -> None:
        if not buffer:
            return
        b64 = base64.b64encode("".join(buffer).encode("utf-16-be")).decode("ascii")
        b64 = b64.rstrip("=").replace("/", ",")
        out.append(f"&{b64}-")
        buffer.clear()

    for ch in name:
        if ch in _PRINTABLE and ch != "&":
            _flush()
            out.append(ch)
        elif ch == "&":
            _flush()
            out.append("&-")
        else:
            buffer.append(ch)
    _flush()
    return "".join(out)
