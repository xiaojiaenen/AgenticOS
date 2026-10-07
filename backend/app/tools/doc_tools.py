"""文档工具 — 办公智能体的 Word 能力。

模型给的是结构化块（标题/正文），运行时转成 Univer 的富文本文档。
排版细节（字号、对齐、加粗）交给浏览器编辑器，模型只负责内容和层级——
这正是它擅长的部分，也是它最容易把 JSON 写炸的部分。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from wuwei.tools import ToolRegistry

from app.core.data_path import get_current_session_id, get_current_user_id
from app.services.office import document_service as doc

logger = logging.getLogger("agent.office.doc.tools")

#: 允许的块类型。超出直接报错，让模型改，而不是悄悄当成正文。
ALLOWED_BLOCK_TYPES = {"h1", "h2", "h3", "h4", "paragraph"}


def _session_id() -> str:
    session_id = get_current_session_id()
    if not session_id:
        raise doc.DocumentServiceError("缺少会话 ID，无法操作文档")
    return session_id


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_blocks(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """校验块结构，返回 (合法块, 错误列表)。"""
    errors: list[str] = []
    cleaned: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(f"第 {index + 1} 个块不是对象")
            continue
        kind = str(block.get("type") or "paragraph")
        if kind not in ALLOWED_BLOCK_TYPES:
            errors.append(
                f"第 {index + 1} 个块的 type 是 {kind!r}，"
                f"可选：{', '.join(sorted(ALLOWED_BLOCK_TYPES))}"
            )
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            errors.append(f"第 {index + 1} 个块的 text 为空")
            continue
        cleaned.append({"type": kind, "text": text})
    return cleaned, errors


def register_doc_tools(registry: ToolRegistry) -> None:
    """注册文档工具。由 tool_config_service 在 office 模式下自动发现。"""

    @registry.tool(display_name="新建文档")
    async def create_document(title: str, blocks: list[dict[str, Any]]) -> str:
        """新建一份文档并一次性写入全部内容（覆盖式，整份交付）。

        文档不支持增量追加——它是给人读的整篇内容，所以**一次把全文写全**，
        包括所有标题和段落。要改内容就重新调用一次，写完整的新版本。

        参数:
          title: 文档标题，例如「2026 Q3 复盘纪要」
          blocks: 内容块数组，从上到下排列。每块形如：
                    {"type": "h1", "text": "一季度复盘"}
                    {"type": "h2", "text": "风险"}
                    {"type": "paragraph", "text": "本季度销售额同比增长 12%。"}
                  type 可选 h1/h2/h3/h4（标题）和 paragraph（正文）。
                  **不要把标题写成 paragraph 再加井号**，直接用 h1~h4。

        返回:
          文档标识与块数
        """
        try:
            session_id = _session_id()
        except doc.DocumentServiceError as exc:
            return f"新建失败：{exc}"

        if not isinstance(blocks, list) or not blocks:
            return "新建失败：blocks 必须是非空数组，至少包含一段正文"

        cleaned, errors = _normalize_blocks(blocks)
        if errors:
            return "新建失败：\n- " + "\n- ".join(errors[:6])
        if not any(b["type"] == "paragraph" for b in cleaned):
            return "新建失败：全是标题没有正文，请补充 paragraph 块"

        try:
            result = await doc.create_document(session_id, get_current_user_id(), title, cleaned)
        except doc.DocumentServiceError as exc:
            return f"新建失败：{exc}"
        return _json(result)

    @registry.tool(display_name="读取文档")
    async def read_document() -> str:
        """读回当前文档的结构与内容，用于核对。

        返回:
          标题与内容块列表
        """
        try:
            result = await doc.read_document(_session_id())
        except doc.DocumentServiceError as exc:
            return f"读取失败：{exc}"
        return _json(result)

    @registry.tool(display_name="完成文档")
    async def build_document() -> str:
        """完成文档并产出预览。内容写好后必须调用一次，否则用户看不到成果。

        产出会作为可编辑的文档展示在对话右侧，用户可以直接改。

        返回:
          文档标识与字数
        """
        try:
            result = await doc.build_document(_session_id())
        except doc.DocumentServiceError as exc:
            return f"完成失败：{exc}"
        # 快照本体不进返回值：它会占满模型上下文，产物展示走 artifact 事件。
        return _json(
            {
                "document_id": result["document_id"],
                "title": result["title"],
                "char_count": result["char_count"],
            }
        )
