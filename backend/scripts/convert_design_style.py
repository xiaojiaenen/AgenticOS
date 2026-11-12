#!/usr/bin/env python3
"""guanmo-ai/design-style 风格 tokens.json → AgenticOS 设计资产。

输入：/tmp/dstyle/<NNN-slug>.json（GitHub raw 拉取）
输出：
  1. data/design-systems/<slug>/tokens.css  —— open-design 命名（--bg/--fg/--accent…），
     供 convert_design_systems.py 转成 PPT 主题，也可被网站生成的 AI 直接引用；
  2. data/design-systems/<slug>/DESIGN.md   —— 人读的风格指南（含对比度实测）；
  3. data/design-systems/<slug>/motion.json —— 原始运动参数（bpm/beat/弹簧），
     现有主题都是静态的，这是动效系统的第一批输入。

映射策略：design-style 的 color 键名每个风格都不同（paper/ink/gold/onyx…），
两种形态（rich dict / flat string）。用启发式归一：
  - --bg        键名含 paper/background/bg/canvas，或「面积最大的浅色」
  - --fg        键名含 ink/onyx/foreground/black，或亮度最低的深色
  - --accent    键名含 accent/primary，或饱和度 × 面积加权最高的彩色
  - accent-2/3  其余彩色按面积 × 饱和度排序
  - good/warn/danger 语义键名匹配（green/success、yellow/orange、red/danger）
  - 其余中性色（text-2/meta/border/surface 阶梯）从 fg/bg 插值派生
"""

from __future__ import annotations

import colorsys
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\code\AgenticOS")
SRC_DIR = Path(subprocess.check_output(["cygpath", "-w", "/tmp/dstyle"], text=True).strip())
OUT_DIR = ROOT / "data" / "design-systems"

# design-style 风格号 → AgenticOS slug（与 design-themes 现有命名风格一致）
SLUG_MAP = {
    "003-constructivism": "constructivism",
    "008-risograph": "risograph",
    "013-art-deco": "art-deco",
    "015-futurism": "futurism",
    "017-mid-century-modern": "mid-century-modern",
    "018-diorama": "diorama",
    "019-low-poly": "low-poly",
    "020-ascii-art": "ascii-art",
    "021-generative-art": "generative-art",
    "022-point-cloud": "point-cloud",
    "023-liquid-chrome": "liquid-chrome",
    "024-ink-wash": "ink-wash",
    "025-plush": "plush",
    "026-art-nouveau": "art-nouveau",
}

FONT_FALLBACK_CJK = "'Noto Sans SC',sans-serif"


# ── 颜色工具 ──────────────────────────────────────────────────────────


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _rel_luminance(hex_color: str) -> float:
    """WCAG 2.1 相对亮度。"""

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = _rel_luminance(fg), _rel_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _saturation(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    hls = colorsys.rgb_to_hls(r, g, b)
    return hls[2]


def _is_light(hex_color: str) -> bool:
    return _rel_luminance(hex_color) >= 0.5


def _mix(a: str, b: str, t: float) -> str:
    """线性插值两个 hex（t=0 → a）。"""
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    def m(x: float, y: float) -> int:
        return round((x + (y - x) * t) * 255)

    return "#{:02x}{:02x}{:02x}".format(m(ra, rb), m(ga, gb), m(ba, bb))


def _fmt(h: str) -> str:
    return h.lower()


# ── token 归一化 ──────────────────────────────────────────────────────

_BG_KEYS = ("paper", "background", "bg", "canvas", "cream", "bone")
_FG_KEYS = ("ink", "onyx", "foreground", "fg", "black", "charcoal")
_ACCENT_KEYS = ("accent", "primary", "red", "gold", "hero", "signature")
_GOOD_KEYS = ("green", "success", "good", "teal", "turq", "lime", "mint")
_WARN_KEYS = ("yellow", "warn", "warning", "amber", "sun", "orange")
_DANGER_KEYS = ("red", "danger", "bad", "crimson", "alarm")


def _flatten_color(color: dict) -> dict[str, tuple[str, str, float]]:
    """归一 color 字段 → {key: (hex, 中文名, area)}。area 缺省按顺序衰减。"""
    out: dict[str, tuple[str, str, float]] = {}
    colors = color.get("color") if isinstance(color.get("color"), (dict, list)) else color
    # tokens.json 顶层叫 color；兼容 {"color": {...}}
    entries: list[tuple[str, str, str, float | None]] = []
    for key, val in colors.items():
        if isinstance(val, dict) and isinstance(val.get("hex"), str) and val["hex"].startswith("#"):
            entries.append((key, val["hex"], str(val.get("name") or key), val.get("area")))
        elif isinstance(val, dict) and isinstance(val.get("rgb"), (list, tuple)) and len(val["rgb"]) == 3:
            r, g, b = val["rgb"]
            entries.append((key, "#{:02x}{:02x}{:02x}".format(r, g, b), str(val.get("name") or key), val.get("area")))
        elif isinstance(val, str) and val.startswith("#") and len(val) in (4, 7):
            entries.append((key, val, key, None))
        # 其余形态（渐变串 / 关键字如 "on"）跳过 —— 不是单一色值
    n = len(entries)
    for i, (key, hexv, name, area) in enumerate(entries):
        if area is None:
            area = round(max(0.03, 0.5 - 0.4 * (i / max(1, n - 1))), 3) if n > 1 else 0.5
        out[key.lower()] = (_fmt(hexv), name, float(area))
    return out


def _pick(colors, keys, *, pred=None) -> str | None:
    for k in keys:
        for name, (hexv, _n, _a) in colors.items():
            if k in name:
                if pred is None or pred(hexv):
                    return hexv
    return None


def _is_chromatic(hexv: str) -> bool:
    return _saturation(hexv) >= 0.15


def build_tokens(data: dict) -> dict[str, str]:
    colors = _flatten_color(data)

    # ── 背景与前景：按面积定基调，按对比度定正文 ──
    #
    # 「背景必须是浅色」的假设是错的 —— art-deco 是黑底金线（onyx 面积
    # 0.6），risograph 是米白纸荧光粉。设计里面积最大的颜色就是基调，
    # 强行翻浅色会毁掉风格。正确做法：
    #   bg = 面积最大的颜色（键名含 paper/background 时优先）；
    #   fg = 与 bg 对比度最高的候选（优先键名含 ink/foreground 的）。
    entries = sorted(colors.items(), key=lambda kv: -kv[1][2])
    bg = _pick(colors, _BG_KEYS) or entries[0][1][0]

    fg_candidates = []
    for name, (hexv, _label, area) in colors.items():
        if hexv == bg:
            continue
        fg_candidates.append((_contrast(hexv, bg), name, hexv))
    fg_candidates.sort(key=lambda x: -x[0])
    fg = _pick(colors, _FG_KEYS) or (fg_candidates[0][2] if fg_candidates else "#111111")
    # 键名匹配的 fg 若对比度反而不及候选，用候选（对比度优先于命名直觉）
    if fg_candidates and _contrast(fg, bg) < fg_candidates[0][0] - 0.5:
        fg = fg_candidates[0][2]

    # 彩色（非 bg/fg）
    chromatics: list[tuple[str, str, float]] = []
    for _name, (hexv, label, area) in colors.items():
        if hexv in (bg, fg) or not _is_chromatic(hexv):
            continue
        chromatics.append((_name, hexv, area * (0.5 + _saturation(hexv))))
    chromatics.sort(key=lambda x: -x[2])

    accent = _pick(colors, _ACCENT_KEYS) or (chromatics[0][1] if chromatics else "#3b82f6")
    # accent 主要用于大字与按钮：与背景至少要 AA-Large（3:1）。
    # 不达标时从候选里换对比度最高的彩色，仍不达标就在原色上加深/提亮。
    if _contrast(accent, bg) < 3.0:
        better = sorted(
            (c for c in chromatics if c[1] != accent and _contrast(c[1], bg) >= 3.0),
            key=lambda c: -c[2],
        )
        if better:
            accent = better[0][1]
        else:
            accent = _mix(accent, fg, 0.35) if _contrast(_mix(accent, fg, 0.35), bg) > _contrast(accent, bg) else _mix(accent, bg, 0.35)
    accent_rest = [h for _k, h, _a in chromatics if h != accent and _contrast(h, bg) >= 2.0][:2]
    while len(accent_rest) < 2:
        accent_rest.append(_mix(accent, fg, 0.35 * (len(accent_rest) + 1)))

    # 语义色：优先键名匹配，其次从彩色里借
    def _usable(h: str) -> bool:
        return _contrast(h, bg) >= 2.5

    good = _pick(colors, _GOOD_KEYS) or next(
        (h for _k, h, _a in chromatics if _usable(h) and 110 <= _hue(h) <= 180), None
    ) or _mix("#16a34a", bg, 0.15 if _is_light(bg) else 0.35)
    warn = _pick(colors, _WARN_KEYS) or next(
        (h for _k, h, _a in chromatics if _usable(h) and 35 <= _hue(h) <= 70), None
    ) or _mix("#eab308", bg, 0.15 if _is_light(bg) else 0.35)
    danger = _pick(colors, _DANGER_KEYS) or next(
        (h for _k, h, _a in chromatics if _usable(h) and (_hue(h) <= 20 or _hue(h) >= 340)), None
    ) or _mix("#dc2626", bg, 0.15 if _is_light(bg) else 0.35)

    # 字体
    font = data.get("font") or {}
    display_fam = _font_family(font, ("display", "title", "headline", "latin", "cn"))
    ui_fam = _font_family(font, ("ui", "text", "body", "cn")) or display_fam
    mono_fam = _font_family(font, ("mono", "code")) or "'JetBrains Mono',monospace"
    serif_fam = "'Playfair Display','Noto Serif SC',serif"

    # 形状
    shape = data.get("shape") or {}
    radius = _extract_radius(shape)
    shadow = _extract_shadow(shape, fg)

    # open-design 命名（convert_design_systems 的 A 路径直接映射 → PPT 主题；
    # 同时是网站生成侧 lint 强制的标准命名，AI 照 :root 原样引用即可）
    return {
        "--bg": bg,
        "--surface": _mix(bg, fg, 0.06),
        "--surface-warm": _mix(bg, "#ffffff", 0.55) if _is_light(bg) else _mix(bg, fg, 0.18),
        "--fg": fg,
        "--fg-2": _mix(fg, bg, 0.35),
        "--meta": _mix(fg, bg, 0.60),
        "--border": _mix(fg, bg, 0.82),
        "--border-soft": _mix(fg, bg, 0.55),
        "--accent": accent,
        "--accent-hover": accent_rest[0],
        "--accent-active": accent_rest[1],
        "--success": good,
        "--warn": warn,
        "--danger": danger,
        "--font-sans": f"{ui_fam},{FONT_FALLBACK_CJK}",
        "--font-display": f"{display_fam},{FONT_FALLBACK_CJK}",
        "--font-mono": mono_fam if mono_fam.endswith(("monospace", "Mono")) else f"{mono_fam},monospace",
        "--font-serif": serif_fam,
        "--radius": f"{radius}px",
        "--radius-sm": f"{max(0, radius - 4)}px",
        "--radius-lg": f"{radius + 8}px",
        "--shadow": shadow,
        "--shadow-lg": shadow.replace(" 0 ", " 12px ") if "px" in shadow else shadow,
    }


def _hue(hexv: str) -> float:
    r, g, b = _hex_to_rgb(hexv)
    h, _l, _s = colorsys.rgb_to_hls(r, g, b)
    return h * 360


def _font_family(font: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        val = font.get(k)
        if isinstance(val, dict):
            fam = val.get("family")
            if fam:
                return f"'{fam.split('（')[0].strip()}'"
        elif isinstance(val, str) and val.strip():
            # "Anton（转轮廓后手剪）" / "Jost（Futura 的开源替代）" / "Noto Sans SC Black / Bold"
            fam = val.split("（")[0].split("/")[0].strip()
            return f"'{fam}'"
    return None


def _extract_radius(shape: dict) -> int:
    for container in (shape.get("ui") or {}, shape):
        val = container.get("radius")
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, list) and val:
            return int(val[0])
    return 8


def _extract_shadow(shape: dict, fg: str) -> str:
    ui = shape.get("ui") or {}
    sh = ui.get("shadow") or shape.get("shadow")
    blur = shape.get("shadowBlur", 4)
    if isinstance(sh, (list, tuple)) and sh:
        offs = " ".join(str(int(x)) for x in sh[:2])
        if not blur:
            return f"{offs}px 0 {fg}"
        return f"{offs}px rgba(0,0,0,0.35)"
    return "0 2px 8px rgba(0,0,0,0.10)"


def contrast_report(tokens: dict[str, str]) -> list[dict[str, object]]:
    """关键前景/背景组合的 WCAG 对比度（AA 正文 ≥4.5 / 大字 ≥3.0）。"""
    pairs = [
        ("--fg", "--bg"),
        ("--fg", "--surface"),
        ("--fg-2", "--bg"),
        ("--accent", "--bg"),
        ("--bg", "--accent"),
    ]
    out = []
    for fgp, bgp in pairs:
        fg, bgv = tokens.get(fgp, "#111"), tokens.get(bgp, "#fff")
        ratio = round(_contrast(fg, bgv), 2)
        out.append({
            "pair": f"{fgp} on {bgp}",
            "ratio": ratio,
            "grade": "AAA" if ratio >= 7 else "AA" if ratio >= 4.5 else "AA-Large" if ratio >= 3 else "FAIL",
        })
    return out


def render_tokens_css(slug: str, title: str, tokens: dict[str, str]) -> str:
    lines = [
        f"/* design-systems/{slug}/tokens.css — converted from guanmo-ai/design-style",
        f" * 风格：{title}。所有色值经 WCAG 对比度启发式映射，参见 DESIGN.md 的实测表。",
        " */",
        ":root {",
    ]
    for k, v in tokens.items():
        lines.append(f"  {k}: {v};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_design_md(slug: str, data: dict, title: str, tokens: dict[str, str], report: list) -> str:
    colors = _flatten_color(data)
    rows = "\n".join(
        f"| {r['pair']} | {r['ratio']}:1 | {r['grade']} |" for r in report
    )
    color_rows = "\n".join(
        f"| `{k}` | `{hexv}` | {label} | {area} |" for k, (hexv, label, area) in colors.items()
    )
    years = data.get("years", "")
    return f"""# {title}（{slug}）

> 来源：[guanmo-ai/design-style](https://github.com/guanmo-ai/design-style)（{years}）。
> 由 `scripts/convert_design_style.py` 从该仓库的 tokens.json 自动转换；
> 色彩映射是启发式的，人工校色欢迎直接改 `tokens.css`。

## 色板

| 键 | 值 | 含义 | 面积 |
|---|---|---|---|
{color_rows}

## WCAG 对比度实测

| 组合 | 比值 | 等级 |
|---|---|---|
{rows}

## 运动（motion.json）

原始 bpm / 节拍 / 弹簧参数保留在 `motion.json`，供未来的动效系统引用。
"""


def main() -> int:
    report_lines = []
    for src_slug, slug in SLUG_MAP.items():
        src = SRC_DIR / f"{src_slug}.json"
        if not src.is_file():
            print(f"SKIP {src_slug}（源文件缺失）")
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        title = str(data.get("name") or slug)
        tokens = build_tokens(data)
        report = contrast_report(tokens)
        fails = [r for r in report if r["grade"] == "FAIL"]

        out_dir = OUT_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "tokens.css").write_text(
            render_tokens_css(slug, title, tokens), encoding="utf-8"
        )
        (out_dir / "DESIGN.md").write_text(
            render_design_md(slug, data, title, tokens, report), encoding="utf-8"
        )
        motion = data.get("motion") or {}
        if motion:
            (out_dir / "motion.json").write_text(
                json.dumps(motion, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        worst = min(report, key=lambda r: r["ratio"])
        report_lines.append(
            f"{slug:<22} bg={tokens['--bg']} fg={tokens['--fg']} accent={tokens['--accent']}"
            f"  最差对比 {worst['ratio']}:1（{worst['grade']}）{'  FAIL×%d' % len(fails) if fails else ''}"
        )

    print("\n".join(report_lines))
    print(f"\n完成：{len(report_lines)} 个风格写入 {OUT_DIR}")
    print("下一步：python scripts/convert_design_systems.py 生成 design-themes/*.css")
    return 0


if __name__ == "__main__":
    sys.exit(main())
