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
    {
        "code": "bento_overuse",
        "pattern": r'<svg[^>]*>.*?<g\s+id="card-\d+".*?<g\s+id="card-\d+".*?<g\s+id="card-\d+".*?<g\s+id="card-\d+"',
        "message": "避免 Bento Grid 滥用（每页 >3 个相同结构的卡片）",
        "dotall": True,
    },
    # --- 新增 P0 规则 ---
    {
        "code": "shadow_overuse",
        "pattern": r'filter="drop-shadow.*?drop-shadow',
        "message": "禁止同一页使用多个投影效果（AI 生成感）",
        "dotall": True,
    },
    {
        "code": "gradient_abuse",
        "pattern": None,  # special check
        "message": "禁止超过 2 种渐变（AI 生成感）",
    },
    {
        "code": "icon_style_mix",
        "pattern": None,  # special check
        "message": "禁止混用不同风格图标库（如 chunk-filled + tabler-outline）",
    },
    {
        "code": "suspicious_numbers",
        "pattern": r'(?:42|87|93|97|99|100)%',
        "message": "包含疑似捏造的百分比数据，请使用真实数据或标注来源",
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
    {
        "code": "emoji_as_icon",
        "pattern": None,  # special check
        "message": "使用 emoji 代替图标，应使用 <use data-icon=\"库名/图标名\" .../> 语法",
    },
    # --- 新增 P1 规则 ---
    {
        "code": "whitespace_imbalance",
        "pattern": None,  # special check
        "message": "留白不均匀（左右或上下边距差异过大）",
    },
    {
        "code": "alignment_drift",
        "pattern": None,  # special check
        "message": "元素未对齐到网格（建议对齐到 8px 网格）",
    },
    {
        "code": "font_size_variety",
        "pattern": None,  # special check
        "message": "字号种类过多（建议每页 <= 5 种字号）",
    },
    {
        "code": "accent_overuse",
        "pattern": None,  # special check
        "message": "accent 颜色使用过多（建议每页 <= 3 处）",
    },
    {
        "code": "no_image",
        "pattern": None,  # special check
        "message": "缺少图片（封面和章节页必须有图片）",
    },
    {
        "code": "no_animation_markers",
        "pattern": None,  # special check
        "message": "缺少动画标记（data-animate 属性）",
    },
]


def _count_gradients(svg_content: str) -> int:
    """统计渐变数量"""
    linear = len(re.findall(r'<linearGradient', svg_content))
    radial = len(re.findall(r'<radialGradient', svg_content))
    return linear + radial


def _check_icon_consistency(svg_content: str) -> bool:
    """检查图标风格一致性"""
    # 检查是否混用了不同图标库
    chunk_filled = 'data-icon="chunk-filled/' in svg_content
    tabler_filled = 'data-icon="tabler-filled/' in svg_content
    tabler_outline = 'data-icon="tabler-outline/' in svg_content
    phosphor = 'data-icon="phosphor-duotone/' in svg_content

    # 如果同时使用了 chunk-filled 和 tabler 系列，视为混用
    if chunk_filled and (tabler_filled or tabler_outline):
        return False
    # 如果同时使用了 tabler-filled 和 tabler-outline，允许（同系列）
    # 如果同时使用了 phosphor 和其他，视为混用
    if phosphor and (chunk_filled or tabler_filled or tabler_outline):
        return False

    return True


def _check_whitespace_balance(svg_content: str) -> bool:
    """检查留白是否均匀"""
    # 提取 viewBox 尺寸
    viewBox_match = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg_content)
    if not viewBox_match:
        return True  # 无法检查

    width = int(viewBox_match.group(1))
    height = int(viewBox_match.group(2))

    # 提取所有元素的 x, y 坐标
    x_coords = [int(x) for x in re.findall(r'x="(\d+)"', svg_content)]
    y_coords = [int(y) for y in re.findall(r'y="(\d+)"', svg_content)]

    if not x_coords or not y_coords:
        return True

    # 计算左右边距
    min_x = min(x_coords)
    max_x = max(x_coords)
    left_margin = min_x
    right_margin = width - max_x

    # 边距差异超过 50% 视为不均匀
    if left_margin > 0 and right_margin > 0:
        ratio = max(left_margin, right_margin) / min(left_margin, right_margin)
        if ratio > 1.5:
            return False

    return True


def _check_alignment(svg_content: str) -> bool:
    """检查元素是否对齐到 8px 网格"""
    # 提取所有 x, y 坐标
    coords = re.findall(r'[xy]="(\d+)"', svg_content)
    if not coords:
        return True

    # 检查是否有坐标不是 8 的倍数
    misaligned = 0
    for coord in coords:
        val = int(coord)
        if val % 8 != 0 and val != 0:  # 0 除外
            misaligned += 1

    # 如果超过 30% 的坐标未对齐，视为问题
    if misaligned > len(coords) * 0.3:
        return False

    return True


def _count_font_sizes(svg_content: str) -> int:
    """统计字号种类"""
    sizes = re.findall(r'font-size="(\d+)"', svg_content)
    return len(set(sizes))


def _count_accent_usage(svg_content: str) -> int:
    """统计 accent 颜色使用次数"""
    return len(re.findall(r'var\(--accent\)', svg_content))


def _has_image(svg_content: str) -> bool:
    """检查是否包含图片"""
    return '<image' in svg_content


def _has_animation_markers(svg_content: str) -> bool:
    """检查是否有动画标记"""
    return 'data-animate=' in svg_content


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

        # 特殊检查
        if rule["code"] == "gradient_abuse":
            if _count_gradients(svg_content) > 2:
                findings.append(Finding("P0", rule["code"], rule["message"]))
            continue
        elif rule["code"] == "icon_style_mix":
            if not _check_icon_consistency(svg_content):
                findings.append(Finding("P0", rule["code"], rule["message"]))
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
            matches = re.finditer(rule["pattern"], svg_content, flags)
            for m in matches:
                match_text = m.group(0)
                # Check if match should be excluded
                excluded = False
                if rule.get("exclude_patterns"):
                    for exclude_pattern in rule["exclude_patterns"]:
                        if re.search(exclude_pattern, match_text):
                            excluded = True
                            break
                if not excluded:
                    findings.append(Finding("P0", rule["code"], rule["message"]))
                    break

    # Run P1 checks
    for rule in P1_PATTERNS:
        # 特殊检查
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
        elif rule["code"] == "emoji_as_icon":
            # 检查是否使用 emoji 作为装饰图标（而不是 <use data-icon="..."/>）
            has_use_icon = 'data-icon="' in svg_content
            if not has_use_icon:
                # 检查是否有 emoji 字符在 <text> 元素中作为装饰
                emoji_pattern = r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]'
                text_with_emoji = re.findall(r'<text[^>]*>([^<]*' + emoji_pattern + r'[^<]*)</text>', svg_content)
                if text_with_emoji:
                    findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "whitespace_imbalance":
            if not _check_whitespace_balance(svg_content):
                findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "alignment_drift":
            if not _check_alignment(svg_content):
                findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "font_size_variety":
            if _count_font_sizes(svg_content) > 5:
                findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "accent_overuse":
            if _count_accent_usage(svg_content) > 3:
                findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "no_image":
            if not _has_image(svg_content):
                findings.append(Finding("P1", rule["code"], rule["message"]))
        elif rule["code"] == "no_animation_markers":
            if not _has_animation_markers(svg_content):
                findings.append(Finding("P1", rule["code"], rule["message"]))
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
