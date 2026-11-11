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
#:
#: bullets / ordered / table / quote 是写文档的刚需——早先只放行标题和正文，
#: 模型想列要点或插表格时整块被拒，只能退回成一段散文，成品质量明显下降。
#: 现在这几种结构化块直接透传给运行时（它在 composeBlocks 里展开成多行）。
ALLOWED_BLOCK_TYPES = {
    "h1",
    "h2",
    "h3",
    "h4",
    "paragraph",
    "bullets",
    "ordered",
    "table",
    "quote",
    # 兼容模型常见的别名，避免它因为叫不出准确类型名而反复重试
    "list",
    "ul",
    "ol",
}

#: 需要「数组型内容」而不是 text 的块类型。
_ARRAY_BLOCK_TYPES = {"bullets", "ordered", "list", "ul", "ol"}


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

        # 列表块用 items[]，表格块用 header[]/rows[]，其余用 text
        if kind in _ARRAY_BLOCK_TYPES:
            items = block.get("items")
            if not isinstance(items, list) or not items:
                errors.append(f"第 {index + 1} 个块（{kind}）的 items 必须是非空数组")
                continue
            cleaned.append({"type": kind, "items": [str(i).strip() for i in items if str(i).strip()]})
            continue
        if kind == "table":
            header = block.get("header") or []
            rows = block.get("rows") or []
            if not header and not rows:
                errors.append(f"第 {index + 1} 个块（table）至少要有 header 或 rows")
                continue
            cleaned.append(
                {
                    "type": "table",
                    "header": [str(h).strip() for h in header] if isinstance(header, list) else [],
                    "rows": [
                        [str(c).strip() for c in row] if isinstance(row, list) else [str(row).strip()]
                        for row in rows
                    ]
                    if isinstance(rows, list)
                    else [],
                }
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
    async def create_document(title: str, blocks: str | list[dict[str, Any]]) -> str:
        """新建一份文档并一次性写入全部内容（覆盖式，整份交付）。

        文档不支持增量追加——它是给人读的整篇内容，所以**一次把全文写全**，
        包括所有标题和段落。要改内容就重新调用一次，写完整的新版本。

        **``blocks`` 同时接受数组和 JSON 字符串**：LLM 经常把整个数组序列化成
        一个字符串塞进来（实测 `blocks: "[{...}]"`），框架的 strict 参数校验
        会在进入本函数之前就抛 `Invalid tool arguments`，一行文档都写不出来。
        放宽类型后在内部解析，两种形态都能工作。

        参数:
          title: 文档标题，例如「2026 Q3 复盘纪要」
          blocks: 内容块数组，从上到下排列。每块形如：
                    {"type": "h1", "text": "一季度复盘"}
                    {"type": "h2", "text": "风险"}
                    {"type": "paragraph", "text": "本季度销售额同比增长 12%。"}
                    {"type": "bullets", "items": ["要点一", "要点二"]}
                    {"type": "ordered", "items": ["第一步", "第二步"]}
                    {"type": "quote", "text": "引用或强调的一句话"}
                    {"type": "table", "header": ["项目", "金额"], "rows": [["A", "100"]]}
                  type 可选 h1/h2/h3/h4（标题）、paragraph（正文）、
                  bullets（无序列表）、ordered（有序列表）、quote（引用）、
                  table（表格）。**不要把标题写成 paragraph 再加井号**，直接用 h1~h4；
                  要点请用 bullets 而不是塞进一段话；数据请用 table 而不是逐行念。

        返回:
          文档标识与块数
        """
        try:
            session_id = _session_id()
        except doc.DocumentServiceError as exc:
            return f"新建失败：{exc}"

        # 模型可能把整个数组序列化成字符串塞进来。框架的 strict 类型校验
        # 要求声明兼容，这里再在内部统一解析成 list[dict]。
        if isinstance(blocks, str):
            try:
                decoded = json.loads(blocks)
            except (json.JSONDecodeError, TypeError):
                return "新建失败：blocks 是无法解析的 JSON 字符串，请直接传数组"
            if not isinstance(decoded, list):
                return "新建失败：blocks 解析后不是数组"
            blocks = decoded

        if not isinstance(blocks, list) or not blocks:
            return "新建失败：blocks 必须是非空数组，至少包含一段正文"

        cleaned, errors = _normalize_blocks(blocks)
        if errors:
            return "新建失败：\n- " + "\n- ".join(errors[:6])
        # 早先要求必须含 paragraph 块，但模型经常用 h2/h3 承载正文小节、
        # 或用 bullets/table 交付要点，于是被这句校验反复打回（它再改一次还是同样写法）。
        # 真正的约束是「除了标题之外要有实质内容」，而不是「必须有 paragraph 类型」。
        body_kinds = {"paragraph", "bullets", "ordered", "list", "ul", "ol", "table", "quote"}
        if not any(b["type"] in body_kinds for b in cleaned):
            return "新建失败：全是标题没有正文，请补充 paragraph / bullets / table 等正文块"

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
