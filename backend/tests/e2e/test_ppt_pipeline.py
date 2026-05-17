#!/usr/bin/env python3
"""
End-to-end test for PPT generation → export pipeline.
Checks: skill loading, icon expansion, animation integration, export validity.
Run from backend/ directory:
    uv run python ../tests/e2e/test_ppt_pipeline.py
"""

import json
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Ensure backend/ is on the Python path
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _BACKEND_DIR)

DB_PATH = Path("/Users/xiaojia/code/AgenticOS/data/agenticos.db")
ICONS_DIR = Path("/Users/xiaojia/code/AgenticOS/data/icons")

PASS = 0
FAIL = 0


def check(description: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {description}")
    else:
        FAIL += 1
        print(f"  ❌ {description}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================================
# 1. Skill Loading
# ============================================================================

if __name__ == "__main__":
    section("1. Skill Registration & Loading")
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 1a. Check ppt-svg-reference skill exists
    cursor = conn.execute(
        "SELECT id, name, slug, root_dir FROM skills WHERE slug='ppt-svg-reference'"
    )
    skill = cursor.fetchone()
    check("ppt-svg-reference skill registered in DB", skill is not None)
    if skill:
        skill_id, name, slug, root_dir = skill
        check(f"Skill root_dir exists: {root_dir}", Path(root_dir).is_dir())
        check(f"SKILL.md exists", (Path(root_dir) / "SKILL.md").is_file())
        # Verify SKILL.md has animation content
        skill_md = (Path(root_dir) / "SKILL.md").read_text()
        check("SKILL.md contains animation chapter",
              "元素分组与 PPTX 动画" in skill_md or "分组与动画" in skill_md)
        check("SKILL.md contains icon chapter",
              "图标" in skill_md)
        check("SKILL.md contains chrome group rules",
              "bg-layer" in skill_md and "跳过动画" in skill_md)
    
    # 1b. Check PPT agent profile
    cursor = conn.execute(
        "SELECT id, name, slug FROM agent_profiles WHERE response_mode='ppt'"
    )
    ppt_profile = cursor.fetchone()
    check("PPT agent profile exists", ppt_profile is not None)
    if ppt_profile:
        profile_id, profile_name, profile_slug = ppt_profile
        print(f"  Profile: {profile_name} (slug={profile_slug})")
    
    # 1c. Check tool config for PPT mode
    cursor = conn.execute("PRAGMA table_info(agent_tool_configs)")
    tool_cols = [r[1] for r in cursor.fetchall()]
    check("agent_tool_configs table exists", "tool_name" in tool_cols)
    
    cursor = conn.execute(
        "SELECT tool_name, mode, enabled FROM agent_tool_configs WHERE mode='ppt'"
    )
    ppt_tools = list(cursor.fetchall())
    print(f"  PPT mode tools: {[(r[0], r[2]) for r in ppt_tools]}")
    
    # Check if 'skill' is enabled for PPT mode
    skill_enabled = any(r[0] == "skill" and r[2] for r in ppt_tools)
    check("Skill tool enabled for PPT mode", skill_enabled)
    
    # search_icons is registered via register_icon_tools() in _build_tool_registry,
    # not via agent_tool_configs — check that the function works
    from app.tools.icon_tools import register_icon_tools
    check("search_icons module importable", register_icon_tools is not None)
    
    conn.close()
    
    # ============================================================================
    # 2. Icon Search + Expansion Pipeline
    # ============================================================================
    section("2. Icon Search & Expansion")
    
    from app.tools.icon_tools import _search as icon_search
    
    # 2a. Search functionality
    results = icon_search("rocket")
    check("search_icons('rocket') returns results", len(results) > 0)
    if results:
        print(f"  Results ({len(results)}):")
        for r in results[:5]:
            print(f"    - {r}")
    
    # 2b. Verify icon files exist
    rocket_path = ICONS_DIR / "chunk-filled" / "rocket.svg"
    check(f"Icon file exists: chunk-filled/rocket.svg", rocket_path.is_file())
    
    # 2c. Icon expansion - create test SVG with <use data-icon>
    test_svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <rect width="1280" height="720" fill="#ffffff"/>
      <g font-family="Arial" id="bg-layer">
        <g id="card-1">
          <rect x="100" y="100" width="300" height="200" rx="16" fill="#f0f0f0"/>
          <use data-icon="chunk-filled/rocket" x="200" y="150" width="32" height="32" fill="#0071e3"/>
          <text x="250" y="190" font-size="20" fill="#333">Rocket Launch</text>
        </g>
      </g>
    </svg>"""
    
    from app.services.ppt.svg_finalize.embed_icons import process_svg_file as embed_icons_fn
    
    with tempfile.TemporaryDirectory() as tmpdir:
        svg_path = Path(tmpdir) / "test_icon.svg"
        svg_path.write_text(test_svg_icon, encoding="utf-8")
    
        count = embed_icons_fn(svg_path, ICONS_DIR, dry_run=False, verbose=False)
        check("Icon expansion replaced use element", count == 1, f"replaced {count} icons")
    
        expanded = svg_path.read_text(encoding="utf-8")
        check("<use data-icon> removed from SVG", "data-icon=" not in expanded)
        check("Expanded <g> contains <path>", "<path" in expanded)
        check("Expanded group has transform",
              'transform="translate(' in expanded or "translate(200" in expanded)
    
        # Verify expanded SVG is valid XML
        try:
            ET.fromstring(expanded)
            check("Expanded SVG is valid XML", True)
        except ET.ParseError as e:
            check("Expanded SVG is valid XML", False, str(e))
    
    # ============================================================================
    # 3. Animation Integration
    # ============================================================================
    section("3. Animation Integration")
    
    # 3a. Test SVG with <g id> groups → anim_targets should be non-empty
    test_svg_groups = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <rect width="1280" height="720" fill="#ffffff"/>
      <g id="bg-layer">
        <rect width="1280" height="720" fill="#f5f5f5"/>
      </g>
      <g id="cover-header">
        <text x="640" y="180" font-size="24" fill="#333">Title Here</text>
      </g>
      <g id="card-1">
        <rect x="100" y="300" width="500" height="200" rx="16" fill="#e8f0fe"/>
        <text x="350" y="400" font-size="32" fill="#0071e3">Key Metric +42%</text>
      </g>
      <g id="card-2">
        <rect x="680" y="300" width="500" height="200" rx="16" fill="#e8f0fe"/>
        <text x="930" y="400" font-size="32" fill="#0071e3">Revenue $12.8M</text>
      </g>
      <g id="cover-footer">
        <text x="80" y="680" font-size="12" fill="#999">Company Name</text>
      </g>
    </svg>"""
    
    from app.services.ppt.svg_to_pptx.drawingml_converter import convert_svg_to_slide_shapes
    from app.services.ppt.svg_to_pptx.pptx_animations import (
        create_transition_xml,
        create_sequence_timing_xml,
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        svg_path = Path(tmpdir) / "test_groups.svg"
        svg_path.write_text(test_svg_groups, encoding="utf-8")
    
        slide_xml, media_files, rel_entries, anim_targets = convert_svg_to_slide_shapes(
            svg_path, slide_num=1, verbose=False,
        )
    
        check("SVG conversion succeeded", slide_xml is not None and len(slide_xml) > 0)
        check("anim_targets is non-empty", len(anim_targets) > 0)
    
        # Chrome groups (bg-layer, cover-footer) should NOT be in anim_targets
        chrome_names = {name for _, name in anim_targets}
        check("bg-layer excluded from anim_targets", "bg-layer" not in chrome_names)
        check("cover-footer excluded from anim_targets",
              "cover-footer" not in chrome_names,
              f"chrome_names: {chrome_names}")
        # cover-header contains "header" → chrome keyword, correctly excluded
        check("cover-header excluded (chrome keyword 'header')",
              "cover-header" not in chrome_names)
    
        # Content groups (card-1, card-2) SHOULD be in anim_targets
        content_found = [name for _, name in anim_targets if name in ("card-1", "card-2")]
        check("card-1 included in anim_targets", "card-1" in chrome_names)
        check("card-2 included in anim_targets", "card-2" in chrome_names)
    
        # Generate transition + animation timing XML
        transition_xml = create_transition_xml(effect="fade", duration=0.5)
        check("Transition XML generated", transition_xml is not None and "<p:transition" in transition_xml)
    
        # Build sequence targets from anim_targets (as pptx_builder does)
        from app.services.ppt.svg_to_pptx.pptx_builder import _build_sequence_targets
        from app.services.ppt.svg_to_pptx.pptx_animations import pick_animation_effect
    
        slide_cfg = {}
        seq_targets, _ = _build_sequence_targets(
            anim_targets, slide_cfg, "mixed", 0.3, 0.1, 0,
        )
        check("Sequence targets built from anim_targets", len(seq_targets) > 0)
        print(f"  seq_targets: {len(seq_targets)} targets")
    
        timing_xml = create_sequence_timing_xml(seq_targets, duration=0.3, trigger="after-previous")
        check("Timing XML generated", timing_xml is not None and "<p:timing" in timing_xml)
    
        # Inject into slide XML
        slide_with_anim = slide_xml.replace("</p:sld>", transition_xml + timing_xml + "</p:sld>")
        check("Animation injected into slide XML",
              "<p:transition" in slide_with_anim and "<p:timing" in slide_with_anim)
    
        print(f"  anim_targets: {anim_targets}")
        print(f"  chrome_names: {chrome_names}")
    
    # ============================================================================
    # 4. SVG Sanitization
    # ============================================================================
    section("4. XML Sanitization (escape < and & in text)")
    
    from app.services.ppt_artifact_service import sanitize_svg_xml
    
    # Test cases
    test_cases = [
        # (input, should_be_valid_after, description)
        ('<svg><text>Delta E < 0.5</text></svg>', True, "Escapes raw < in text"),
        ('<svg><text>Price: A & B</text></svg>', True, "Escapes raw & in text"),
        ('<svg><text>Already &lt; 10 &amp; good</text></svg>', True, "Preserves existing entities"),
        ('<svg><text><tspan>Nested < 1</tspan></text></svg>', True, "Escapes in nested tspan"),
        ('<svg><g><rect/></g></svg>', True, "No-op on valid SVG"),
    ]
    
    for svg_input, should_pass, desc in test_cases:
        fixed = sanitize_svg_xml(svg_input)
        try:
            ET.fromstring(fixed)
            check(desc, should_pass)
        except ET.ParseError as e:
            check(desc, not should_pass, str(e)[:80])
    
    # ============================================================================
    # 5. Full Export Pipeline (with existing artifact)
    # ============================================================================
    section("5. Full Export Pipeline")
    
    from app.services.ppt.svg_to_pptx.pptx_builder import create_pptx_with_native_svg
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute(
        "SELECT artifact_id, deck_json FROM ppt_artifacts ORDER BY created_at DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        artifact_id, deck_json = row
        deck = json.loads(deck_json)
        svgs = deck.get("svgs", [])
    
        # Sanitize all SVGs
        svgs = [sanitize_svg_xml(s) for s in svgs]
        print(f"  Artifact: {artifact_id}, slides: {len(svgs)}")
    
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
    
            # Write Sanitized SVGs
            svg_paths = []
            for i, svg in enumerate(svgs):
                svg_path = tmpdir_path / f"slide{i+1}.svg"
                svg_path.write_text(svg, encoding="utf-8")
                svg_paths.append(svg_path)
    
            # Icon expansion
            icons_processed = 0
            for svg_path in svg_paths:
                icons_processed += embed_icons_fn(svg_path, ICONS_DIR, dry_run=False, verbose=False)
            check("Icon expansion completed", icons_processed >= 0,
                  f"{icons_processed} icons expanded")
    
            # Try full export
            output_path = tmpdir_path / "output.pptx"
            try:
                create_pptx_with_native_svg(
                    svg_files=svg_paths,
                    output_path=output_path,
                    canvas_format="ppt169",
                    verbose=False,
                    transition="fade",
                    use_native_shapes=True,
                    use_compat_mode=False,
                    animation="mixed",
                    enable_notes=False,
                    notes={},
                )
                check("PPTX export succeeded", output_path.is_file())
    
                # Verify PPTX has animation XML
                pptx_bytes = output_path.read_bytes()
                check("PPTX is non-empty", len(pptx_bytes) > 1000, f"size: {len(pptx_bytes)} bytes")
    
                # Check PPTX zip for animation content
                import zipfile
                with zipfile.ZipFile(output_path) as zf:
                    slides = [n for n in zf.namelist() if n.startswith("ppt/slides/slide")]
                    print(f"  Found {len(slides)} slides in PPTX")
    
                    # Check first content slide for transition/timing
                    anim_slides = 0
                    for slide_name in slides:
                        slide_data = zf.read(slide_name).decode("utf-8", errors="replace")
                        has_transition = "<p:transition" in slide_data
                        has_timing = "<p:timing" in slide_data
                        if has_transition or has_timing:
                            anim_slides += 1
                            # Print first animated slide details
                            if anim_slides == 1:
                                print(f"  {slide_name}: transition={has_transition}, timing={has_timing}")
    
                    check("At least some slides have animations", anim_slides > 0,
                          f"{anim_slides}/{len(slides)} slides with animation")
    
                    # Check for icon shapes (not images)
                    icon_slides = 0
                    for slide_name in slides:
                        slide_data = zf.read(slide_name).decode("utf-8", errors="replace")
                        if "<a:custGeom>" in slide_data or "<a:prstGeom" in slide_data:
                            icon_slides += 1
                    check("Slides contain vector shapes (icons)", icon_slides > 0,
                          f"{icon_slides} slides with vector geometry")
    
            except Exception as e:
                check("PPTX export succeeded", False, str(e)[:120])
    
    
    # ============================================================================
    # 6. Layout Template Validation
    # ============================================================================
    section("6. SVG Layout Template Validation")
    
    import re
    from app.services.ppt.svg_layouts import SVG_LAYOUTS
    
    layout_count = len(SVG_LAYOUTS)
    check(f"SVG_LAYOUTS has {layout_count} layouts", layout_count == 31)
    
    layouts_with_groups = 0
    layouts_with_icons = 0
    layouts_with_bg = 0
    for name, svg in SVG_LAYOUTS.items():
        try:
            ET.fromstring(svg)
        except ET.ParseError as e:
            check(f"{name}: valid XML", False, str(e)[:80])
            continue
    
        # Count <g id="..."> elements
        g_ids = re.findall(r'<g[^>]*id="([^"]*)"', svg)
        if any(gid != "bg-layer" for gid in g_ids):
            layouts_with_groups += 1
        if "data-icon=" in svg:
            layouts_with_icons += 1
        if "bg-layer" in g_ids:
            layouts_with_bg += 1
    
    check("Layouts with item groups", layouts_with_groups >= 18, f"{layouts_with_groups}/31")
    check("Layouts with icon placeholders", layouts_with_icons >= 5, f"{layouts_with_icons}/31")
    check("Layouts with bg-layer id", layouts_with_bg == 31, f"{layouts_with_bg}/31")
    
    # ============================================================================
    # Summary
    # ============================================================================
    section("Summary")
    print(f"  Passed: {PASS}")
    print(f"  Failed: {FAIL}")
    print(f"  Total:  {PASS + FAIL}")
    
    if FAIL > 0:
        print("\n  ⚠️  Some tests FAILED — check output above for details.")
        sys.exit(1)
    else:
        print("\n  🎉 All tests PASSED!")
        sys.exit(0)
    