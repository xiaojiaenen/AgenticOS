"""PPT Anti-AI-Slop Checker

Detects common AI-generated design mistakes in PPT SVGs.
Inspired by open-design's lint-artifact.ts P0 checks.

Usage:
    from app.services.ppt.anti_slop_checker import check_anti_slop
    findings = check_anti_slop(svg_content)
    # findings = [{"severity": "P0", "code": "indigo_accent", "message": "..."}]
"""

import re
from typing import NamedTuple


class Finding(NamedTuple):
    severity: str  # "P0" or "P1"
    code: str      # e.g. "indigo_accent"
    message: str   # human-readable description


# P0 checks — auto-block artifact creation
P0_PATTERNS = [
    {
        "code": "indigo_accent",
        "pattern": r'(?:fill|stroke)="#(?:6366f1|4f46e5|8b5cf6|7c3aed|6d28d9|5b21b6|4c1d95)"',
        "message": "禁止使用 Tailwind Indigo/紫色作为 accent，应使用 var(--accent)",
    },
    {
        "code": "trust_gradient",
        "pattern": r'(?:linear|radial)Gradient.*?(?:stop-color="(#[0-9a-fA-F]{6})".*?stop-color="(#[0-9a-fA-F]{6})")',
        "message": "避免紫蓝/蓝青双色渐变背景（AI 指纹）",
        "exclude_colors": True,  # skip if stops are var() references
    },
    {
        "code": "emoji_icon",
        "pattern": r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F]',
        "message": "禁止使用 Emoji 作为功能图标，应使用 search_icons 搜索真实图标",
    },
    {
        "code": "lorem_ipsum",
        "pattern": r'Lorem ipsum|占位文字|placeholder text|示例文字',
        "message": "禁止使用 Lorem Ipsum 或占位文字",
    },
    {
        "code": "fake_metric",
        "pattern": r'(?:10|100|1000)x\s*(?:faster|提升|效率|性能)|99\.9%\s*(?:可用|uptime|available)',
        "message": "禁止捏造数据（如 '10x 提升'、'99.9% 可用'）",
    },
    {
        "code": "rounded_left_border",
        "pattern": r'rx="\d{8,30}".*?fill="var\(--accent\)"',
        "message": "避免'圆角卡片+左侧 accent 竖条'模式（典型 AI dashboard）",
        "min_gap": 200,  # characters between rx and fill
    },
    # --- huashu-design 增强 ---
    {
        "code": "bento_overuse",
        "pattern": r'<svg[^>]*>.*?<g\s+id="card-\d+".*?<g\s+id="card-\d+".*?<g\s+id="card-\d+"',
        "message": "避免 Bento Grid 滥用（每页 >3 个相同结构的卡片）",
        "dotall": True,
    },
]

# P1 checks — warn but don't block
P1_PATTERNS = [
    {
        "code": "sans_display",
        "pattern": r'font-family="Inter[^"]*".*?font-size="([4-7]\d)"',
        "message": "展示文本（大字号）建议使用衬线字体（Playfair Display）",
        "note": "仅当 font-size >= 40px 时触发",
    },
    {
        "code": "no_notes",
        "pattern": None,  # special check
        "message": "缺少演讲者备注 <!-- notes: ... -->",
    },
    {
        "code": "no_groups",
        "pattern": None,  # special check
        "message": "<svg> 根下可能有裸元素，应使用 <g id='...'> 分组",
    },
    {
        "code": "hardcoded_color",
        "pattern": r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8})"',
        "message": "使用了硬编码颜色值，应使用 var(--token)",
        "allowed_colors": {
            "#FFFFFF", "#FFFFFE", "#F8FAFC", "#FAFBFC", "#F5F5F5",
            "#000000", "#0F172A", "#1E293B", "#334155", "#111827",
            "#1A1A2E", "#0D1117", "#161B22",
        },
    },
]


def check_anti_slop(svg_content: str) -> list[Finding]:
    """Check SVG for anti-AI-slop violations.

    Returns a list of Finding objects, sorted by severity (P0 first).
    """
    findings: list[Finding] = []

    # Run P0 checks
    for rule in P0_PATTERNS:
        if rule.get("exclude_colors"):
            # Skip if gradient stops use var() references
            if 'stop-color="var(' in svg_content:
                continue
        if rule.get("min_gap"):
            # Special handling for pattern that needs character gap
            matches = re.finditer(rule["pattern"], svg_content, re.DOTALL)
            for m in matches:
                if len(m.group(0)) > rule["min_gap"]:
                    findings.append(Finding("P0", rule["code"], rule["message"]))
                    break
        elif rule["pattern"]:
            flags = re.DOTALL if rule.get("dotall") else 0
            if re.search(rule["pattern"], svg_content, flags):
                findings.append(Finding("P0", rule["code"], rule["message"]))

    # Run P1 checks
    for rule in P1_PATTERNS:
        if rule["code"] == "no_notes":
            if "<!-- notes:" not in svg_content:
                findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "no_groups":
            # Check if <svg> root has direct non-<g> children
            svg_inner = re.search(r'<svg[^>]*>(.*)</svg>', svg_content, re.DOTALL)
            if svg_inner:
                inner = svg_inner.group(1).strip()
                inner_no_comment = re.sub(r'<!--.*?-->', '', inner, flags=re.DOTALL).strip()
                if inner_no_comment and not re.match(r'<g[\s>]', inner_no_comment):
                    findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "hardcoded_color":
            allowed = rule.get("allowed_colors", set())
            hex_colors = re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8})"', svg_content)
            for color in set(hex_colors):
                if color.upper() not in {c.upper() for c in allowed}:
                    findings.append(Finding("P1", rule["code"], f"{rule['message']}: {color}"))
                    break  # only report once
        elif rule["pattern"]:
            m = re.search(rule["pattern"], svg_content)
            if m:
                if rule["code"] == "sans_display":
                    font_size = int(m.group(1))
                    if font_size >= 40:
                        findings.append(Finding("P1", rule["code"], rule["message"]))
                else:
                    findings.append(Finding("P1", rule["code"], rule["message"]))

    # Sort: P0 first
    findings.sort(key=lambda f: (0 if f.severity == "P0" else 1))
    return findings


def has_critical_slops(svg_content: str) -> bool:
    """Quick check: does the SVG have any P0 violations?"""
    findings = check_anti_slop(svg_content)
    return any(f.severity == "P0" for f in findings)
