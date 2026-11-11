"""图片附件的多模态输入链路。

用户报障：上传图片后模型说「无法查看图片」——此前图片只被描述成
一个路径字符串（还引导模型去 file_to_md 读二进制）。修复后图片读成
data URL 塞进 wuwei 的 ImagePart，序列化为 OpenAI 的 image_url 块，
支持视觉的模型即可真的看图。
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-1234567890abcdef")

import pytest  # noqa: E402
from wuwei.core.message import HumanMessage, ImagePart  # noqa: E402

from app.schemas.agent import AgentStreamRequest, FileAttachment  # noqa: E402
from app.services.agent.orchestrator import StreamOrchestrator, _MAX_IMAGES_PER_TURN  # noqa: E402

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "h6FO1AAAAABJRU5ErkJggg=="
)


def _make_orchestrator() -> StreamOrchestrator:
    """_build_user_input 只用到 self 上的方法，最小桩即可。"""
    return StreamOrchestrator.__new__(StreamOrchestrator)


def _request(files: list[FileAttachment] | None, message: str = "看看这张图") -> AgentStreamRequest:
    return AgentStreamRequest(message=message, response_mode="general", files=files)


def _attach(tmp_path: Path, name: str, data: bytes) -> FileAttachment:
    p = tmp_path / name
    p.write_bytes(data)
    return FileAttachment(filename=name, file_path=str(p))


class TestImageMultimodalInput:
    def test_image_becomes_human_message_with_image_part(self, tmp_path):
        att = _attach(tmp_path, "chart.png", PNG_1PX)
        result = _make_orchestrator()._build_user_input("看看这张图", _request([att]))

        assert isinstance(result, HumanMessage)
        assert result.content == "看看这张图"
        assert len(result.content_parts) == 1
        part = result.content_parts[0]
        assert isinstance(part, ImagePart)
        assert part.url.startswith("data:image/png;base64,")

    def test_mixed_files_image_plus_text(self, tmp_path):
        img = _attach(tmp_path, "photo.jpg", PNG_1PX)
        doc = _attach(tmp_path, "notes.txt", "正文".encode("utf-8"))
        result = _make_orchestrator()._build_user_input("两个都看下", _request([img, doc]))

        assert isinstance(result, HumanMessage)
        # 文本：文件描述块（只描述非图片）+ 原消息
        assert "notes.txt" in result.content
        assert "photo.jpg" not in result.content
        # 一张图片 part
        assert len([p for p in result.content_parts if isinstance(p, ImagePart)]) == 1

    def test_no_files_returns_plain_str(self):
        result = _make_orchestrator()._build_user_input("你好", _request(None))
        assert result == "你好"

    def test_oversized_image_is_skipped_with_note(self, tmp_path):
        big = _attach(tmp_path, "big.png", b"x" * (9 * 1024 * 1024))
        result = _make_orchestrator()._build_user_input("看图", _request([big]))

        # 全部图片被跳过 → 退回纯文本（没有可用图片就不发空的多模态消息），
        # 但必须告知用户哪些图没能发送。
        assert isinstance(result, str)
        assert "big.png" in result and "8MB" in result

    def test_corrupt_file_is_skipped_not_fatal(self, tmp_path):
        att = FileAttachment(filename="gone.png", file_path=str(tmp_path / "missing.png"))
        result = _make_orchestrator()._build_user_input("看图", _request([att]))
        assert isinstance(result, str)
        assert "gone.png" in result

    def test_image_count_is_capped(self, tmp_path):
        files = [_attach(tmp_path, f"p{i}.png", PNG_1PX) for i in range(_MAX_IMAGES_PER_TURN + 2)]
        result = _make_orchestrator()._build_user_input("多图", _request(files))
        parts = [p for p in result.content_parts if isinstance(p, ImagePart)]
        assert len(parts) == _MAX_IMAGES_PER_TURN

    def test_serialization_produces_openai_image_url(self, tmp_path):
        """端到端契约：HumanMessage 序列化后必须是 OpenAI 的 image_url 块。"""
        att = _attach(tmp_path, "shot.png", PNG_1PX)
        msg = _make_orchestrator()._build_user_input("看", _request([att]))
        payload = msg.to_openai()
        assert payload["role"] == "user"
        assert isinstance(payload["content"], list)
        kinds = [b["type"] for b in payload["content"]]
        assert "image_url" in kinds
