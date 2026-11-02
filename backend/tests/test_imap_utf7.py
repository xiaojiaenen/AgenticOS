"""IMAP modified UTF-7 codec + Chinese folder resolution regression."""
from __future__ import annotations

import imaplib
from unittest.mock import MagicMock

from app.tools.imap_utf7 import decode as utf7_decode
from app.tools.imap_utf7 import encode as utf7_encode


class TestCodec:
    def test_rfc3501_examples(self):
        assert utf7_decode("~peter/mail/&U,BTFw-/&ZeVnLIqe-") == "~peter/mail/台北/日本語"
        assert utf7_encode("~peter/mail/台北/日本語") == "~peter/mail/&U,BTFw-/&ZeVnLIqe-"

    def test_roundtrip_chinese(self):
        for name in ("项目邮件", "已发送", "2026年度-客户往来", "公司&部门"):
            assert utf7_decode(utf7_encode(name)) == name

    def test_ampersand_escape(self):
        assert utf7_encode("a&b") == "a&-b"
        assert utf7_decode("a&-b") == "a&b"

    def test_ascii_passthrough(self):
        assert utf7_encode("Sent Messages") == "Sent Messages"
        assert utf7_decode("INBOX") == "INBOX"


def _fake_imap(mailboxes):
    imap = MagicMock(spec=imaplib.IMAP4)
    imap.list.return_value = ("OK", [b'(\\HasNoChildren) "/" ' + m for m in mailboxes])

    def _select(name, readonly=False):
        # 真实服务器（Coremail 等）只认 modified UTF-7 的 ASCII 形式：
        # 把中文原名直接 utf-8 编码发过来会被拒绝（这正是旧代码的故障）
        if isinstance(name, str):
            try:
                target = name.encode("ascii")
            except UnicodeEncodeError:
                return ("NO", [b"unknown mailbox"])
        else:
            target = name
        stripped = target.strip(b'"')
        ok = any(stripped == m or stripped == m.strip(b'"') for m in mailboxes)
        return ("OK" if ok else "NO", [b"1"])

    imap.select.side_effect = _select
    return imap


class TestFolderResolution:
    def test_list_decodes_chinese_folders(self):
        from app.tools.email_tools import _list_mailboxes

        imap = _fake_imap([
            b"INBOX",
            b"&mHl27pCuTvY-",  # 项目邮件
            b"Sent Messages",
        ])
        out = _list_mailboxes(imap)
        displays = [d for _, d in out]
        assert "项目邮件" in displays
        assert "INBOX" in displays
        # display -> 原始 mailbox（bytes）映射
        raw = {display: rawbytes for rawbytes, display in out}
        assert raw["项目邮件"] == b"&mHl27pCuTvY-"

    def test_resolve_by_chinese_display_name(self):
        """核心回归：模型把列表里的中文名传回来，能解析到原始 mailbox。"""
        from app.tools.email_tools import _resolve_imap_folder

        imap = _fake_imap([b"INBOX", b"&mHl27pCuTvY-", b"Sent Messages"])
        target = _resolve_imap_folder(imap, "项目邮件")
        assert isinstance(target, bytes) and target == b"&mHl27pCuTvY-"

    def test_resolve_common_english_names_still_work(self):
        from app.tools.email_tools import _resolve_imap_folder

        imap = _fake_imap([b"INBOX", b"Sent Messages"])
        assert _resolve_imap_folder(imap, "sent") == b"Sent Messages"
        assert _resolve_imap_folder(imap, "inbox") == "INBOX"

    def test_resolve_raw_utf7_form_and_alias(self):
        from app.tools.email_tools import _resolve_imap_folder

        imap = _fake_imap([b"INBOX", b"&XfJT0ZAB-"])  # 已发送
        # 传入原始 modified UTF-7 形式：它本身是 ASCII，服务器接受原样名
        # （返回 str 或 bytes 均可 —— 语义等价，select 都成功了）
        assert _resolve_imap_folder(imap, "&XfJT0ZAB-") in ("&XfJT0ZAB-", b"&XfJT0ZAB-")
        # 传入解码后的中文名（真实服务器会拒绝 utf-8 编码名）：
        # 必须解析回原始 bytes 形式
        assert _resolve_imap_folder(imap, "已发送") == b"&XfJT0ZAB-"

    def test_resolve_case_insensitive_and_prefix(self):
        from app.tools.email_tools import _resolve_imap_folder

        imap = _fake_imap([b"INBOX", b"&mHl27pCuTvY-", b"Sent Messages"])
        assert _resolve_imap_folder(imap, "sent") == b"Sent Messages"
