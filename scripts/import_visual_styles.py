#!/usr/bin/env python
"""把 ppt-master 的 visual-styles markdown 转成 AgenticOS 的结构化风格注册表。

用法（在仓库根目录）：
    python scripts/import_visual_styles.py <上游 visual-styles 目录>

产出：backend/app/services/ppt/visual_styles_data.py

为什么单独生成一个数据文件、而不是直接读 markdown：
- 上游 markdown 是给「人/模型读」的长文，字段位置靠标题约定；
- AgenticOS 要在运行时（前端选择器、提示词注入）用到结构化字段
  （id / 标签 / 分类 / 形状 / 字体 / 配色纪律 / 纹理 / 配对插画 / 插画倾向）；
- 生成物带来源标注与生成时间，便于以后重新同步时 diff。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# _index.md 的五个分类小节 → 内部 category key
CATEGORY_MAP = {
    "Corporate / product": "corporate",
    "Editorial / publication": "editorial",
    "Expressive / print": "expressive",
    "Hand-drawn / brush": "hand_drawn",
    "Specialty": "specialty",
}

SECTION_KEYS = {
    "1": "shape",          # Shape & decoration
    "2": "typography",     # Typography character
    "3": "color_usage",    # Using the deck's colors
    "4": "texture",        # Texture / elevation
    "5": "paired_rendering",
    "6": "illustration",
}

# 中文标签（上游只有英文一句话特征；前端选择器需要短标签）
LABEL_ZH = {
    "swiss-minimal": "瑞士极简",
    "soft-rounded": "柔和圆角",
    "glassmorphism": "玻璃拟态",
    "dark-tech": "科技暗色",
    "blueprint": "工程蓝图",
    "editorial": "杂志编辑",
    "photo-editorial": "摄影编辑",
    "data-journalism": "数据新闻",
    "brutalist": "粗野主义",
    "memphis": "孟菲斯",
    "zine": "独立杂志",
    "vintage-poster": "复古海报",
    "paper-cut": "剪纸",
    "sketch-notes": "手绘笔记",
    "ink-notes": "墨线笔记",
    "chalkboard": "黑板",
    "ink-wash": "水墨",
    "pixel-art": "像素艺术",
}


def parse_index(index_md: str) -> dict[str, dict]:
    """从 _index.md 提取每风格的一行摘要 + 分类。"""
    meta: dict[str, dict] = {}
    current_category = None
    for line in index_md.splitlines():
        stripped = line.strip()
        # 分类标题形如 "### 1.1 Corporate / product"
        m = re.match(r"^###\s+[\d.]+\s+(.+)$", stripped)
        if m:
            raw = m.group(1).strip()
            current_category = CATEGORY_MAP.get(raw, raw.lower().replace(" ", "-").split("/")[0].strip())
            continue
        # 表格行
        m = re.match(
            r"^\|\s*\[`([a-z0-9-]+)`\]\([^)]*\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
            stripped,
        )
        if m:
            sid, character, rendering, illus = (g.strip() for g in m.groups())
            meta[sid] = {
                "character": character,
                "paired_rendering": rendering.strip("`"),
                "illustration": illus,
                "category": current_category or "corporate",
            }
    return meta


def parse_style(md: str) -> dict[str, list[str]]:
    """按 '## N. Title' 切分，收集每节的 bullet 文本。"""
    sections: dict[str, list[str]] = {}
    current = None
    for line in md.splitlines():
        m = re.match(r"^##\s+(\d)\.\s", line)
        if m:
            current = SECTION_KEYS.get(m.group(1))
            if current:
                sections[current] = []
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            sections[current].append(stripped[2:].strip())
        elif stripped and not stripped.startswith(">") and sections[current] and not stripped.startswith("#"):
            # 续行（上游有长句折行）
            sections[current][-1] += " " + stripped
    return sections


def clean_bullets(bullets: list[str]) -> list[str]:
    """去掉上游文件里对确认流程的交叉引用（e/h/g 等），保留实质描述。"""
    out = []
    for b in bullets:
        # 去掉 "carrier eligibility / image source" 这类纯流程约束的长句
        if len(b) > 400:
            b = b[:400].rstrip() + "…"
        out.append(b)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/import_visual_styles.py <visual-styles 目录>")
        return 2
    src = Path(sys.argv[1])
    index_md = (src / "_index.md").read_text(encoding="utf-8")
    index_meta = parse_index(index_md)
    if not index_meta:
        print("解析 _index.md 失败：没有抓到任何风格行")
        return 1

    styles: dict[str, dict] = {}
    for md_file in sorted(src.glob("*.md")):
        sid = md_file.stem
        if sid.startswith("_"):
            continue
        sections = parse_style(md_file.read_text(encoding="utf-8"))
        meta = index_meta.get(sid, {})
        # 标题里的第一段描述（"# Visual style: xxx" 之后那句）
        body = md_file.read_text(encoding="utf-8")
        summary_m = re.search(r"^#\s+Visual style:\s*\S+\s*\n+(.+?)\n", body, re.M)
        styles[sid] = {
            "id": sid,
            "label": meta.get("character", sid),
            "label_zh": LABEL_ZH.get(sid, sid),
            "category": meta.get("category", "corporate"),
            "summary": summary_m.group(1).strip() if summary_m else "",
            "shape": clean_bullets(sections.get("shape", [])),
            "typography": clean_bullets(sections.get("typography", [])),
            "color_usage": clean_bullets(sections.get("color_usage", [])),
            "texture": clean_bullets(sections.get("texture", [])),
            "paired_rendering": meta.get("paired_rendering", ""),
            "illustration": meta.get("illustration", ""),
            "illustration_note": " ".join(sections.get("illustration", []))[:400],
        }

    out = Path("backend/app/services/ppt/visual_styles_data.py")
    lines = [
        '"""PPT 视觉风格注册表（自动生成，勿手改）。',
        "",
        "来源：ppt-master 的 references/visual-styles/（19 种风格）。",
        "重新生成：python scripts/import_visual_styles.py <visual-styles 目录>",
        "",
        "**风格与配色正交**：风格只管形状语言 / 装饰密度 / 留白节奏 / 字体特征 /",
        "纹理层次，**不携带任何 HEX 色值**；配色由 design-themes 的 236 个主题提供。",
        "两者在生成时组合使用（如 github 配色 × swiss-minimal 风格）。",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "VISUAL_STYLES: dict[str, dict] = " + json.dumps(styles, ensure_ascii=False, indent=4),
        "",
        "",
        "def list_styles() -> list[dict]:",
        '    """给前端选择器用的精简列表（不含长文本规则）。"""',
        "    return [",
        "        {",
        '            "id": s["id"],',
        '            "label": s["label_zh"],',
        '            "label_en": s["label"],',
        '            "category": s["category"],',
        '            "summary": s["summary"],',
        '            "illustration": s["illustration"],',
        "        }",
        "        for s in VISUAL_STYLES.values()",
        "    ]",
        "",
        "",
        "def get_style(style_id: str | None) -> dict | None:",
        '    """按 id 取完整风格；未知 id 返回 None（调用方应回退到默认）。"""',
        "    if not style_id:",
        "        return None",
        "    return VISUAL_STYLES.get(style_id)",
        "",
        "",
        "def style_prompt_block(style_id: str | None) -> str:",
        '    """把风格渲染成注入模型的文案块（纯文本，不含色值）。"""',
        "    style = get_style(style_id)",
        "    if not style:",
        '        return ""',
        "    parts: list[str] = [f\"### 视觉风格：{style['label_zh']}（{style['id']}）\"]",
        "    if style['summary']:",
        "        parts.append(style['summary'])",
        "    for key, title in (",
        "        ('shape', '形状与装饰'),",
        "        ('typography', '字体特征'),",
        "        ('color_usage', '配色使用纪律（色值来自所选主题）'),",
        "        ('texture', '纹理与层次'),",
        "    ):",
        "        bullets = style.get(key) or []",
        "        if bullets:",
        "            body = chr(10).join(f'- {b}' for b in bullets)",
        "            parts.append(f'**{title}**' + chr(10) + body)",
        "    return (chr(10) * 2).join(parts)",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"写入 {out}：{len(styles)} 种风格")
    for sid, s in styles.items():
        print(f"  {sid:18s} [{s['category']:12s}] shape={len(s['shape'])} typo={len(s['typography'])} color={len(s['color_usage'])} texture={len(s['texture'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
