"""文字宽度估算与安全换行（给 agent 排版时自查用）。

**为什么需要**：SVG 里 ``<text>`` 不会自动换行，文字超出容器就压到别的
元素上；agent 靠"目测"估宽度经常翻车（长标题溢出、中文断行位置奇怪、
标点跑到行首）。上游 ppt-master 的 ``text_measure.py`` 有约 1000 行的
精确实现（多语种字宽标定、标点禁则、连字符处理），这里实现其中
**最影响观感的 80%**：

- CJK 字符按 1.0 em 估算，Latin 按字符类别分档（大写/小写/数字/窄字符）；
- 标点禁则：行首不能是逗号句号等收尾标点、行尾不能是左括号；
- 数字与单位（71%）不拆开；
- ``wrap_text`` 给出不超过给定宽度的换行建议。

估算误差约 ±5%，足够做"这行会不会溢出"的判断；不要用它做像素级对位。
"""
from __future__ import annotations

import unicodedata

#: Latin 字符相对 em 的宽度系数（按类别粗分，取自常见无衬线字体度量）
_LATIN_NARROW = frozenset("iljtfrI.,:;'!|()[]{}")
_LATIN_WIDE = frozenset("mMW@%")
_LATIN_CAPS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

#: 不能出现在行首的收尾标点
_NO_LINE_START = frozenset(",.;:!?)]}、，。；：！？）》」』】”’…·")
#: 不能出现在行尾的开头标点
_NO_LINE_END = frozenset("([{（《「『【“‘")
#: 与前面数字粘连的单位
_NUMBER_SUFFIXES = frozenset("%‰°℃")
#: Latin 词内允许的连字符
_LATIN_CONNECTORS = frozenset("'’._:/+%@#-")


def _is_cjk(ch: str) -> bool:
    """CJK 汉字 / 假名 / 全角标点（按全角处理，宽度约 1 em）。"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF      # CJK 统一汉字
        or 0x3400 <= code <= 0x4DBF   # 扩展 A
        or 0x3040 <= code <= 0x30FF   # 平假名 / 片假名
        or 0xFF00 <= code <= 0xFFEF   # 全角形式
        or 0x3000 <= code <= 0x303F   # CJK 标点
        or code in (0x2018, 0x2019, 0x201C, 0x201D)
    )


def char_width(ch: str, font_size: float) -> float:
    """单个字符的估算宽度（像素）。"""
    if ch == "\t":
        return font_size * 2
    if ch in ("\n", "\r"):
        return 0.0
    if _is_cjk(ch):
        return font_size * 1.0
    if ch == " ":
        return font_size * 0.28
    if ch in _LATIN_NARROW:
        return font_size * 0.32
    if ch in _LATIN_WIDE:
        return font_size * 0.88
    if ch in _LATIN_CAPS:
        return font_size * 0.66
    if ch.isdigit():
        return font_size * 0.56
    # 其他小写 / 希腊 / 西里尔 / 组合符
    cat = unicodedata.category(ch)
    if cat.startswith("M"):  # 组合标记，零宽
        return 0.0
    return font_size * 0.52


def measure_text(text: str, font_size: float) -> float:
    """单行文字的总宽度估算（像素）。含 ``\\n`` 时取最长行。"""
    if not text:
        return 0.0
    lines = text.split("\n")
    return max(sum(char_width(c, font_size) for c in line) for line in lines)


def _tokenize(text: str) -> list[str]:
    """切成不可再分的排版单元：CJK 单字、Latin 词、数字+单位。"""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if _is_cjk(ch) or ch == " ":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
            continue
        if ch in ".,;:!?)]}" and buf:
            # 收尾标点粘在前一个 token 上（避免被推到行首）
            buf += ch
            continue
        if ch in _LATIN_CONNECTORS:
            buf += ch
            continue
        if ch in _NUMBER_SUFFIXES and buf and buf[-1].isdigit():
            buf += ch
            continue
        if ch in _NO_LINE_END:
            # 左括号粘到后一个 token（避免被留在行尾）
            if buf:
                tokens.append(buf)
            buf = ch
            continue
        buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def wrap_text(text: str, font_size: float, max_width: float, max_lines: int = 0) -> list[str]:
    """按估算宽度换行，返回每行文本。

    ``max_lines > 0`` 时超出的部分合并到最后一行并加省略号 —— 调用方据此
    判断「这段文字在该宽度下放不下」。
    """
    if not text:
        return []
    tokens = _tokenize(text)
    lines: list[str] = []
    current = ""
    current_w = 0.0

    for tok in tokens:
        tok_w = sum(char_width(c, font_size) for c in tok)
        if tok == " " and not current:
            continue  # 行首空格丢弃
        if current_w + tok_w > max_width and current:
            # 标点禁则：若以收尾标点开头，把它放回上一行
            if tok and tok[0] in _NO_LINE_START:
                current += tok
                lines.append(current)
                current = ""
                current_w = 0.0
                continue
            lines.append(current)
            current = tok.lstrip()
            current_w = sum(char_width(c, font_size) for c in current)
        else:
            current += tok
            current_w += tok_w

    if current:
        lines.append(current)

    if max_lines and len(lines) > max_lines:
        head = lines[: max_lines - 1]
        tail = "".join(lines[max_lines - 1:])
        while tail and sum(char_width(c, font_size) for c in tail) > max_width - font_size:
            tail = tail[:-1]
        head.append(tail.rstrip() + "…")
        lines = head

    return lines


def fits(text: str, font_size: float, max_width: float, max_height: float | None = None,
         line_height: float = 1.4) -> tuple[bool, dict]:
    """判断一段文字在给定框内是否放得下，返回 (是否放得下, 明细)。"""
    lines = wrap_text(text, font_size, max_width)
    widest = max((measure_text(line, font_size) for line in lines), default=0.0)
    height = len(lines) * font_size * line_height
    detail = {
        "lines": len(lines),
        "widest": round(widest, 1),
        "height": round(height, 1),
        "max_width": max_width,
        "overflow_width": round(max(0.0, widest - max_width), 1),
        "overflow_height": round(max(0.0, height - max_height), 1) if max_height else 0.0,
    }
    ok = widest <= max_width and (max_height is None or height <= max_height)
    return ok, detail
