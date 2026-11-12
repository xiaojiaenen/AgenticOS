"""WCAG 对比度计算与主题审计。

来源背景：guanmo-ai/design-style 仓库给每个风格的 tokens.json 附了
**实测对比度**（黑字放五个底色上都 ≥7:1 这类），并把对比度写进了它的
设计哲学（"黑框让任何底色满足非文本对比 3:1"）。我们的 236 个主题此前
没有这层数据 —— 质量检查只管色彩预算，不管文字是否读得清。

本模块把对比度变成一等公民：

- ``audit_theme_tokens`` 给主题的固定组合（正文/背景、正文/卡片、强调/背景）
  出 AA / AAA 分级 —— ``apply_design_theme`` 返回给 AI、PPT 质量检查引用；
- ``contrast_ratio`` / ``relative_luminance`` 是 WCAG 2.1 标准实现，
  单测用官方样例值锁死。

分级口径（WCAG 2.1 SC 1.4.3 / 1.4.6）：

- ≥ 7.0  AAA（正文）
- ≥ 4.5  AA（正文）
- ≥ 3.0  AA-Large（≥18pt 大字 / 粗体，按钮与标题可用）
- < 3.0  FAIL（除装饰外不可接受）
"""

from __future__ import annotations

import re
from pathlib import Path

# 审计的固定组合：主题里这些搭配决定了「文字是否读得清」。
# --accent on --bg 用于按钮/强调（大字口径 3.0 即可），其余按正文 4.5。
DEFAULT_AUDIT_PAIRS: list[tuple[str, str, float]] = [
    ("--text-1", "--bg", 4.5),
    ("--text-1", "--surface", 4.5),
    ("--text-2", "--bg", 4.5),
    ("--accent", "--bg", 3.0),
    ("--bg", "--accent", 3.0),
]


def _clamp_channel(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 相对亮度（0-1）。"""
    r, g, b = _hex_to_rgb01(hex_color)
    return 0.2126 * _clamp_channel(r) + 0.7152 * _clamp_channel(g) + 0.0722 * _clamp_channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 对比度（1.0-21.0）。"""
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def grade(ratio: float) -> str:
    if ratio >= 7.0:
        return "AAA"
    if ratio >= 4.5:
        return "AA"
    if ratio >= 3.0:
        return "AA-Large"
    return "FAIL"


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"不是 6 位 hex 色值: {hex_color!r}")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def parse_theme_css(css_text: str) -> dict[str, str]:
    """从主题 css 抽 :root 变量 → {var: value}。

    与 convert_design_systems.parse_css_tokens 的差别：这里只取第一个
    ``:root`` 块、容忍注释行，且不处理 var() 引用（主题 css 本来就是纯值）。
    """
    out: dict[str, str] = {}
    m = re.search(r":root\s*\{([^}]*)\}", css_text, re.S)
    if not m:
        return out
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("/*") or ":" not in line:
            continue
        name, _, value = line.partition(":")
        name = name.strip()
        value = value.strip().rstrip(";").strip()
        if name.startswith("--") and value:
            out[name] = value
    return out


def audit_theme_tokens(tokens: dict[str, str]) -> dict[str, object]:
    """对主题 token 跑固定组合审计。

    返回 ``{"pairs": [...], "pass": bool, "summary": str}``。
    缺变量的组合跳过（旧主题可能没有 --surface）。
    """
    pairs = []
    ok = True
    for fg_var, bg_var, threshold in DEFAULT_AUDIT_PAIRS:
        fg, bgv = tokens.get(fg_var), tokens.get(bg_var)
        if not fg or not bgv:
            continue
        try:
            ratio = round(contrast_ratio(fg, bgv), 2)
        except ValueError:
            continue
        g = grade(ratio)
        if g == "FAIL" or ratio < threshold:
            ok = False
        pairs.append({
            "pair": f"{fg_var} on {bg_var}",
            "ratio": ratio,
            "threshold": threshold,
            "grade": g,
            "pass": ratio >= threshold,
        })
    worst = min((p["ratio"] for p in pairs), default=0)
    summary = f"最差组合 {worst}:1" + ("，全部达标" if ok else "，存在读不清的文字搭配")
    return {"pairs": pairs, "pass": ok, "summary": summary}


def audit_theme_css_file(css_path: Path) -> dict[str, object] | None:
    """读主题 css 文件并审计；文件不存在或没有 :root 返回 None。"""
    if not css_path.is_file():
        return None
    tokens = parse_theme_css(css_path.read_text(encoding="utf-8", errors="ignore"))
    if not tokens:
        return None
    return audit_theme_tokens(tokens)
