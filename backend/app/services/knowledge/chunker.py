"""Markdown 感知的段级切块器。

为什么不按固定字数硬切
----------------------
编译产物是 Markdown，硬切会把一个表格或一组步骤拦腰截断，两段的向量都不
再代表任何完整含义。这里按「块的语义边界」优先：

    空行 / 标题行  →  超长块再退到句子边界  →  仍然超长才硬切

同时记录每段所在的最近一级标题（``heading``），向量化时前置到文本里——
这是 Contextual Retrieval 的简化版：仅靠段正文，「端口是 8080」这类句子
脱离标题后语义是悬空的，补上「部署规范 / 常见问题」之后召回明显变好。

overlap 的做法是「上一段末尾若干字的整句回带」，而不是按字数截断回带：
从半句话开始的前缀对向量只有噪声，不贡献语义。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 块边界：空行，或紧邻标题行之前
_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n|\n(?=#{1,6}\s)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
# 句子/行终止符（中英文都覆盖）
_BREAK_CHARS = "。！？；!?;\n"


@dataclass(slots=True)
class TextChunk:
    """一个切片及其在原文中的位置。"""

    index: int
    text: str
    heading: str | None
    char_start: int
    char_end: int


def normalize_text(content: str) -> str:
    """统一换行符，保证 char 偏移与源文本一一对应。"""
    return (content or "").replace("\r\n", "\n").replace("\r", "\n")


def chunk_markdown(
    content: str,
    *,
    max_chars: int = 400,
    overlap: int = 80,
    min_chars: int = 40,
    max_chunks: int | None = 60,
) -> list[TextChunk]:
    """把 Markdown 正文切成若干段。

    Args:
        content: 页面正文
        max_chars: 单段目标长度上限
        overlap: 段间回带的字符数（0 表示不重叠）
        min_chars: 单段最短长度，低于此长度的尾段并入前一段
        max_chunks: 段数上限，超出的部分丢弃（极端长页保护）

    Returns:
        list[TextChunk]，按原文顺序排列，``char_start``/``char_end`` 指向
        ``normalize_text(content)`` 的下标区间。
    """
    text = normalize_text(content)
    if not text.strip():
        return []

    max_chars = max(40, max_chars)
    overlap = max(0, min(overlap, max_chars // 2))

    units = _build_units(text, max_chars)
    if not units:
        return []

    chunks: list[TextChunk] = []
    parts: list[str] = []
    cur_len = 0
    cur_start: int | None = None
    cur_end = 0
    cur_heading: str | None = None

    for u_start, u_end, u_text, u_heading in units:
        # 两种换段时机：
        #   1. 长度到顶（正常装箱）；
        #   2. 跨小节了，且当前段已经攒够最小长度 —— 段级切片的意义就是
        #      「一段对应一个小节」，跨节合并会让 heading 失去指代意义。
        #      攒得还不够长时允许跨节，避免标题自己成为一个 3 字碎片段。
        hits_limit = cur_len + 1 + len(u_text) > max_chars
        crosses_section = bool(parts) and u_heading != cur_heading and cur_len >= min_chars
        if parts and (hits_limit or crosses_section):
            chunks.append(
                _finalize(chunks, cur_start, cur_end, parts, cur_heading, overlap)
            )
            parts, cur_len, cur_start, cur_heading = [], 0, None, None
        if not parts:
            cur_start = u_start
            cur_heading = u_heading
        parts.append(u_text)
        cur_len += len(u_text) + (1 if len(parts) > 1 else 0)
        cur_end = u_end

    if parts:
        chunks.append(_finalize(chunks, cur_start, cur_end, parts, cur_heading, overlap))

    # 尾段过短：并入前一段，避免出现「只有一句 12 字」的碎片段落
    if len(chunks) >= 2 and len(chunks[-1].text) < min_chars:
        tail = chunks.pop()
        prev = chunks[-1]
        merged = f"{prev.text}\n{tail.text}".strip()
        chunks[-1] = TextChunk(
            index=prev.index,
            text=merged,
            heading=prev.heading,
            char_start=prev.char_start,
            char_end=max(prev.char_end, tail.char_end),
        )

    # 重新编号，并在截断时保持顺序
    result: list[TextChunk] = []
    limit = max_chunks if max_chunks and max_chunks > 0 else len(chunks)
    for i, chunk in enumerate(chunks[:limit]):
        chunk.index = i
        result.append(chunk)
    return result


def chunk_embedding_text(title: str | None, heading: str | None, body: str) -> str:
    """段 → 待向量化文本：标题与段所属小节名前置。"""
    prefix = " / ".join(p.strip() for p in (title, heading) if p and p.strip())
    return f"{prefix}\n{body}" if prefix else body


def _build_units(text: str, max_chars: int) -> list[tuple[int, int, str, str | None]]:
    """拆成不可再分的语义单元，并记录每个单元所处的标题。"""
    blocks = _split_blocks(text)
    units: list[tuple[int, int, str, str | None]] = []
    heading: str | None = None

    for start, end, raw in blocks:
        stripped = raw.lstrip()
        match = _HEADING_RE.match(stripped)
        if match:
            heading = match.group(2).strip() or heading
        for piece_start, piece_end, piece_text in _split_oversized(start, end, raw, max_chars):
            unit_text = piece_text.strip()
            if not unit_text:
                continue
            units.append((piece_start, piece_end, unit_text, heading))
    return units


def _split_blocks(text: str) -> list[tuple[int, int, str]]:
    """按空行与标题边界切块，保留原始偏移。"""
    blocks: list[tuple[int, int, str]] = []
    pos = 0
    for match in _BLOCK_SPLIT_RE.finditer(text):
        if match.start() > pos:
            seg = text[pos:match.start()]
            if seg.strip():
                blocks.append((pos, match.start(), seg))
        pos = match.end()
    if pos < len(text):
        seg = text[pos:]
        if seg.strip():
            blocks.append((pos, len(text), seg))
    return blocks


def _split_oversized(
    start: int, end: int, seg: str, max_chars: int
) -> list[tuple[int, int, str]]:
    """把超长块按句子边界拆开；找不到句子边界才硬切。"""
    if len(seg) <= max_chars:
        return [(start, end, seg)]

    pieces: list[tuple[int, int, str]] = []
    pos = 0
    total = len(seg)
    while pos < total:
        remaining = total - pos
        if remaining <= max_chars:
            pieces.append((start + pos, start + total, seg[pos:]))
            break
        window = seg[pos:pos + max_chars]
        cut = 0
        for match in re.finditer(f"[{_BREAK_CHARS}]", window):
            # 太靠前的断点会让本段过短，宁可继续找
            if match.end() >= max_chars * 0.4:
                cut = match.end()
        if cut == 0:
            cut = len(window)
        pieces.append((start + pos, start + pos + cut, seg[pos:pos + cut]))
        pos += cut
    return pieces


def _finalize(
    previous: list[TextChunk],
    start: int | None,
    end: int,
    parts: list[str],
    heading: str | None,
    overlap: int,
) -> TextChunk:
    """组装一个切片，并把上一段的尾部整句回带进来。"""
    body = "\n".join(parts).strip()
    char_start = start if start is not None else 0

    if previous and overlap > 0:
        prev = previous[-1]
        tail = _tail_whole_sentences(prev.text, overlap)
        if tail and not body.startswith(tail):
            body = f"{tail}\n{body}"
            # 回带内容来自上一段末尾，起点向前回退对应长度
            char_start = max(0, prev.char_end - len(tail))

    return TextChunk(
        index=len(previous),
        text=body,
        heading=heading,
        char_start=char_start,
        char_end=end,
    )


def _tail_whole_sentences(text: str, limit: int) -> str:
    """取文本末尾 limit 字符内的整句部分（从句子边界之后开始）。"""
    tail = text[-limit:]
    for i, ch in enumerate(tail):
        if ch in _BREAK_CHARS:
            candidate = tail[i + 1:].strip()
            if candidate:
                return candidate
    return tail.strip()
