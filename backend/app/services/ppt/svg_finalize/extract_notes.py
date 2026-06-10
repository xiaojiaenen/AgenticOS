"""提取演讲者备注

从 SVG 文件的 <!-- notes: ... --> 注释或独立的 .notes.md 文件中提取备注。
"""

from __future__ import annotations

import re
from pathlib import Path


def extract_notes_from_svg(svg_content: str) -> str | None:
    """从 SVG 内容中提取 <!-- notes: ... --> 注释

    参数:
        svg_content: SVG 文件内容

    返回:
        备注文本，如果没有找到则返回 None
    """
    match = re.search(r'<!--\s*notes:\s*(.*?)\s*-->', svg_content, re.DOTALL)
    if match:
        notes = match.group(1).strip()
        if notes:
            return notes
    return None


def extract_notes_from_file(notes_file: Path) -> str | None:
    """从独立的 .notes.md 文件中读取备注

    参数:
        notes_file: 备注文件路径

    返回:
        备注文本，如果文件不存在则返回 None
    """
    if notes_file.exists():
        content = notes_file.read_text(encoding="utf-8").strip()
        if content:
            return content
    return None


def extract_all_notes(slides_dir: Path) -> dict[int, str]:
    """从目录中提取所有幻灯片的备注

    优先级：
    1. 独立的 .notes.md 文件
    2. SVG 中的 <!-- notes: ... --> 注释

    参数:
        slides_dir: 幻灯片目录路径

    返回:
        {slide_num: notes_text} 字典
    """
    notes: dict[int, str] = {}

    # 首先查找独立的 .notes.md 文件
    for notes_file in sorted(slides_dir.glob("slide_*.notes.md")):
        match = re.search(r'slide_(\d+)', notes_file.name)
        if match:
            slide_num = int(match.group(1))
            content = extract_notes_from_file(notes_file)
            if content:
                notes[slide_num] = content

    # 然后从 SVG 文件中提取（如果独立文件不存在）
    for svg_file in sorted(slides_dir.glob("slide_*.svg")):
        match = re.search(r'slide_(\d+)', svg_file.name)
        if match:
            slide_num = int(match.group(1))
            # 如果已经有备注，跳过
            if slide_num in notes:
                continue

            svg_content = svg_file.read_text(encoding="utf-8")
            extracted = extract_notes_from_svg(svg_content)
            if extracted:
                notes[slide_num] = extracted

    return notes


def merge_notes_to_svgs(slides_dir: Path) -> int:
    """将独立的 .notes.md 文件内容合并到 SVG 的 <!-- notes: ... --> 注释中

    参数:
        slides_dir: 幻灯片目录路径

    返回:
        合并的文件数量
    """
    merged_count = 0

    for notes_file in sorted(slides_dir.glob("slide_*.notes.md")):
        match = re.search(r'slide_(\d+)', notes_file.name)
        if not match:
            continue

        slide_num = int(match.group(1))
        svg_file = slides_dir / f"slide_{slide_num}.svg"

        if not svg_file.exists():
            continue

        notes_content = extract_notes_from_file(notes_file)
        if not notes_content:
            continue

        svg_content = svg_file.read_text(encoding="utf-8")

        # 检查是否已有 notes 注释
        if '<!-- notes:' in svg_content:
            # 替换现有的 notes 注释
            svg_content = re.sub(
                r'<!--\s*notes:\s*.*?\s*-->',
                f'<!-- notes: {notes_content} -->',
                svg_content,
                flags=re.DOTALL,
            )
        else:
            # 在 <svg> 标签后添加 notes 注释
            svg_content = re.sub(
                r'(<svg[^>]*>)',
                f'\\1\n  <!-- notes: {notes_content} -->',
                svg_content,
                count=1,
            )

        svg_file.write_text(svg_content, encoding="utf-8")
        merged_count += 1

    return merged_count
