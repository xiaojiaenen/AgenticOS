from __future__ import annotations

import json
import re
import uuid
from html import escape
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json

PPT_PAGE_CLASS = "agenticos-ppt-page"

ALLOWED_TYPES = {
    "cover",
    "section",
    "bullets",
    "imageText",
    "comparison",
    "timeline",
    "stats",
    "chart",
    "quote",
    "closing",
}

THEMES = {
    "executive": {
        "page": "#f6f8fb",
        "dark": "#121826",
        "muted": "#64748b",
        "accent": "#1f6feb",
        "accent_soft": "#dbeafe",
        "accent_text": "#1f6feb",
        "text": "#020617",
        "panel": "#ffffff",
    },
    "product": {
        "page": "#f7fbf9",
        "dark": "#0f2f2a",
        "muted": "#64748b",
        "accent": "#14b8a6",
        "accent_soft": "#ccfbf1",
        "accent_text": "#0f766e",
        "text": "#020617",
        "panel": "#ffffff",
    },
    "minimal": {
        "page": "#fafafa",
        "dark": "#18181b",
        "muted": "#71717a",
        "accent": "#27272a",
        "accent_soft": "#e4e4e7",
        "accent_text": "#27272a",
        "text": "#09090b",
        "panel": "#ffffff",
    },
}


def _as_string(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _as_string_array(value: Any, limit: int = 7) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_string(item) for item in value if _as_string(item)][:limit]


def _normalize_slide(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    raw_type = _as_string(value.get("type"), "cover" if index == 0 else "bullets")
    slide_type = raw_type if raw_type in ALLOWED_TYPES else "bullets"
    chart = value.get("chart") if isinstance(value.get("chart"), dict) else None
    normalized: dict[str, Any] = {
        "type": slide_type,
        "eyebrow": _as_string(value.get("eyebrow")),
        "title": _as_string(value.get("title"), f"第 {index + 1} 页"),
        "subtitle": _as_string(value.get("subtitle")),
        "body": _as_string(value.get("body")),
        "items": _as_string_array(value.get("items")),
        "leftTitle": _as_string(value.get("leftTitle")),
        "rightTitle": _as_string(value.get("rightTitle")),
        "leftItems": _as_string_array(value.get("leftItems")),
        "rightItems": _as_string_array(value.get("rightItems")),
        "imageUrl": _as_string(value.get("imageUrl")),
        "quote": _as_string(value.get("quote")),
        "author": _as_string(value.get("author")),
        "stats": [],
        "timeline": [],
    }
    if chart and isinstance(chart.get("labels"), list) and isinstance(chart.get("values"), list):
        values: list[float] = []
        for item in chart.get("values", [])[:6]:
            try:
                values.append(float(item))
            except (TypeError, ValueError):
                continue
        normalized["chart"] = {
            "type": chart.get("type") if chart.get("type") in {"bar", "line", "donut"} else "bar",
            "labels": _as_string_array(chart.get("labels"), limit=6),
            "values": values,
            "unit": _as_string(chart.get("unit")),
        }
    if isinstance(value.get("stats"), list):
        normalized["stats"] = [
            {
                "label": _as_string(item.get("label")) if isinstance(item, dict) else "",
                "value": _as_string(item.get("value")) if isinstance(item, dict) else "",
                "caption": _as_string(item.get("caption")) if isinstance(item, dict) else "",
            }
            for item in value["stats"][:4]
        ]
        normalized["stats"] = [item for item in normalized["stats"] if item["label"] or item["value"]]
    if isinstance(value.get("timeline"), list):
        normalized["timeline"] = [
            {
                "label": _as_string(item.get("label")) if isinstance(item, dict) else "",
                "title": _as_string(item.get("title")) if isinstance(item, dict) else "",
                "body": _as_string(item.get("body")) if isinstance(item, dict) else "",
            }
            for item in value["timeline"][:5]
        ]
        normalized["timeline"] = [item for item in normalized["timeline"] if item["label"] or item["title"]]
    return normalized


def parse_ppt_deck(code: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(code)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("slides"), list):
        return None
    slides = [_normalize_slide(slide, index) for index, slide in enumerate(payload["slides"][:16])]
    if not slides:
        return None
    theme = payload.get("theme") if payload.get("theme") in THEMES else "executive"
    return {
        "title": _as_string(payload.get("title"), slides[0]["title"] or "AgenticOS 演示文稿"),
        "subtitle": _as_string(payload.get("subtitle")),
        "author": _as_string(payload.get("author")),
        "theme": theme,
        "slides": slides,
    }


def extract_ppt_deck_from_text(text: str) -> tuple[str, dict[str, Any]] | None:
    match = re.search(r"```pptdeck\n([\s\S]*?)\n```", text) or re.search(
        r"```json\n([\s\S]*?\"slides\"[\s\S]*?)\n```",
        text,
    )
    if not match:
        return None
    code = match.group(1).strip()
    deck = parse_ppt_deck(code)
    return (code, deck) if deck else None


def strip_ppt_deck_from_text(text: str) -> str:
    text = re.sub(r"```pptdeck\n[\s\S]*?\n```", "", text)
    text = re.sub(r"```json\n(?=[\s\S]*?\"slides\"[\s\S]*?```)[\s\S]*?\n```", "", text)
    partial_index = text.find("```pptdeck")
    if partial_index >= 0:
        text = text[:partial_index]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _h(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _items(items: list[str], *, numbered: bool = False) -> str:
    if not items:
        items = ["补充要点"]
    html = []
    for index, item in enumerate(items[:5]):
        marker = str(index + 1) if numbered else ""
        html.append(
            f'<div class="ppt-item"><span class="ppt-marker">{_h(marker)}</span><p>{_h(item)}</p></div>'
        )
    return "".join(html)


def _slide_number(index: int, total: int) -> str:
    return f'<div class="ppt-slide-number">{index + 1:02d} / {total:02d}</div>'


def _section(children: str, theme: dict[str, str], index: int, total: int, *, dark: bool = False) -> str:
    colors = (
        f'--ppt-bg:{theme["dark"]};--ppt-text:#fff;--ppt-muted:rgba(255,255,255,.62);'
        if dark
        else f'--ppt-bg:{theme["page"]};--ppt-text:{theme["text"]};--ppt-muted:{theme["muted"]};'
    )
    style = (
        f'{colors}--ppt-dark:{theme["dark"]};--ppt-accent:{theme["accent"]};'
        f'--ppt-accent-soft:{theme["accent_soft"]};--ppt-accent-text:{theme["accent_text"]};'
    )
    return (
        f'<div class="ppt-preview-card"><section class="{PPT_PAGE_CLASS} {"is-dark" if dark else ""}" style="{style}">'
        '<div class="ppt-orb ppt-orb-a"></div><div class="ppt-orb ppt-orb-b"></div><div class="ppt-grid"></div>'
        f'{children}{_slide_number(index, total)}</section></div>'
    )


def _render_chart(slide: dict[str, Any], theme: dict[str, str], index: int, total: int) -> str:
    chart = slide.get("chart") or {"type": "bar", "labels": ["入口", "转化", "留存", "复购"], "values": [32, 58, 74, 86], "unit": "%"}
    labels = chart.get("labels") or []
    values = chart.get("values") or []
    max_value = max([float(value) for value in values] + [1])
    bars = ""
    for label, value in zip(labels, values):
        height = max(20, float(value) / max_value * 210)
        bars += (
            f'<div class="ppt-bar-wrap"><div class="ppt-bar" style="height:{height:.1f}px">'
            f'<span>{_h(value)}{_h(chart.get("unit"))}</span></div><b>{_h(label)}</b></div>'
        )
    children = f"""
      <div class="ppt-topline"><div><div class="ppt-eyebrow">Data view</div><h2>{_h(slide["title"])}</h2><p>{_h(slide.get("subtitle"))}</p></div><span class="ppt-pill">{_h(chart.get("type", "bar"))} chart</span></div>
      <div class="ppt-chart-layout"><div class="ppt-chart">{bars}</div><div class="ppt-insight"><span>Insight</span><strong>{_h(max(values) if values else 0)}{_h(chart.get("unit"))}</strong><p>{_h(slide.get("body") or "关键指标呈现上升趋势，适合作为方案价值或阶段进展的主证据。")}</p></div></div>
    """
    return _section(children, theme, index, total)


def _render_slide(slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
    total = len(deck["slides"])
    theme = THEMES.get(deck.get("theme"), THEMES["executive"])
    slide_type = slide.get("type")
    if slide_type == "cover":
        return _section(
            f"""
            <div class="ppt-cover-label"><span></span>{_h(slide.get("eyebrow") or deck.get("author") or "AgenticOS")}</div>
            <div class="ppt-cover-copy"><h1>{_h(slide["title"])}</h1><p>{_h(slide.get("subtitle") or deck.get("subtitle"))}</p></div>
            <div class="ppt-cover-block"></div>
            """,
            theme,
            index,
            total,
            dark=True,
        )
    if slide_type == "section":
        return _section(
            f'<div class="ppt-section-rule"></div><div class="ppt-section-copy"><div class="ppt-eyebrow">{_h(slide.get("eyebrow") or "Section")}</div><h2>{_h(slide["title"])}</h2><p>{_h(slide.get("subtitle"))}</p></div>',
            theme,
            index,
            total,
            dark=True,
        )
    if slide_type == "comparison":
        left_items = _items(slide.get("leftItems") or ["补充对比项"])
        right_items = _items(slide.get("rightItems") or ["补充对比项"])
        return _section(
            f"""
            <div class="ppt-title-row"><h2>{_h(slide["title"])}</h2><span></span></div>
            <div class="ppt-compare"><div><h3>{_h(slide.get("leftTitle") or "Before")}</h3>{left_items}</div><div class="is-dark"><h3>{_h(slide.get("rightTitle") or "After")}</h3>{right_items}</div></div>
            """,
            theme,
            index,
            total,
        )
    if slide_type == "stats":
        stats = slide.get("stats") or [{"value": "3x", "label": "效率提升"}, {"value": "80%", "label": "重复工作减少"}, {"value": "24/7", "label": "持续响应"}]
        cards = "".join(
            f'<div class="ppt-stat {"is-dark" if item_index == 0 else ""}"><strong>{_h(stat.get("value"))}</strong><h3>{_h(stat.get("label"))}</h3><p>{_h(stat.get("caption"))}</p></div>'
            for item_index, stat in enumerate(stats[:3])
        )
        return _section(
            f'<div class="ppt-heading"><h2>{_h(slide["title"])}</h2><p>{_h(slide.get("subtitle"))}</p></div><div class="ppt-stats">{cards}</div>',
            theme,
            index,
            total,
        )
    if slide_type == "timeline":
        timeline = slide.get("timeline") or [{"label": "01", "title": "定义目标"}, {"label": "02", "title": "生成内容"}, {"label": "03", "title": "导出文件"}]
        nodes = "".join(
            f'<div><span>{_h(item.get("label") or f"0{item_index + 1}")}</span><h3>{_h(item.get("title"))}</h3><p>{_h(item.get("body"))}</p></div>'
            for item_index, item in enumerate(timeline[:5])
        )
        return _section(
            f'<div class="ppt-heading"><h2>{_h(slide["title"])}</h2></div><div class="ppt-timeline">{nodes}</div>',
            theme,
            index,
            total,
        )
    if slide_type == "chart":
        return _render_chart(slide, theme, index, total)
    if slide_type == "quote":
        return _section(
            f'<div class="ppt-quote"><span>“</span><h2>{_h(slide.get("quote") or slide["title"])}</h2><p>{_h(slide.get("author"))}</p></div>',
            theme,
            index,
            total,
            dark=True,
        )
    if slide_type == "imageText":
        image = f'<img src="{_h(slide.get("imageUrl"))}" alt="" />' if slide.get("imageUrl") else ""
        return _section(
            f'<div class="ppt-image-band"></div><div class="ppt-image-box">{image}</div><div class="ppt-image-copy"><h2>{_h(slide["title"])}</h2><p>{_h(slide.get("body") or slide.get("subtitle"))}</p>{_items(slide.get("items") or [], numbered=False)}</div>',
            theme,
            index,
            total,
        )
    if slide_type == "closing":
        return _section(
            f'<div class="ppt-closing"><span></span><h2>{_h(slide["title"])}</h2><p>{_h(slide.get("subtitle"))}</p></div>',
            theme,
            index,
            total,
            dark=True,
        )
    return _section(
        f'<div class="ppt-heading narrow"><span></span><h2>{_h(slide["title"])}</h2><p>{_h(slide.get("subtitle"))}</p></div><div class="ppt-bullets">{_items(slide.get("items") or [slide.get("body") or "补充要点"], numbered=True)}</div>',
        theme,
        index,
        total,
    )


def render_ppt_html(deck: dict[str, Any]) -> str:
    slides = "".join(_render_slide(slide, deck, index) for index, slide in enumerate(deck["slides"]))
    return f"""
<style>
.agenticos-ppt-preview {{ width:720px; margin:0 auto; padding-bottom:32px; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
.agenticos-ppt-preview * {{ box-sizing:border-box; letter-spacing:0; }}
.ppt-preview-card {{ width:720px; height:405px; margin:0 0 32px; transform-origin:top left; }}
.ppt-preview-card > .{PPT_PAGE_CLASS} {{ transform:scale(.72); transform-origin:top left; }}
.{PPT_PAGE_CLASS} {{ position:relative; width:1000px; height:562.5px; overflow:hidden; border-radius:20px; border:1px solid rgba(0,0,0,.06); background:var(--ppt-bg); color:var(--ppt-text); box-shadow:0 24px 70px rgba(15,23,42,.12); }}
.{PPT_PAGE_CLASS} h1,.{PPT_PAGE_CLASS} h2,.{PPT_PAGE_CLASS} h3,.{PPT_PAGE_CLASS} p {{ margin:0; }}
.ppt-grid {{ position:absolute; inset:0; background-image:linear-gradient(90deg,rgba(15,23,42,.045) 1px,transparent 1px),linear-gradient(0deg,rgba(15,23,42,.045) 1px,transparent 1px); background-size:48px 48px; opacity:.42; }}
.is-dark .ppt-grid {{ background-image:linear-gradient(90deg,rgba(255,255,255,.055) 1px,transparent 1px),linear-gradient(0deg,rgba(255,255,255,.055) 1px,transparent 1px); }}
.ppt-orb {{ position:absolute; border-radius:999px; pointer-events:none; }}
.ppt-orb-a {{ right:-80px; top:-96px; width:288px; height:288px; background:rgba(255,255,255,.48); }}
.ppt-orb-b {{ left:64px; bottom:-96px; width:256px; height:256px; background:var(--ppt-accent-soft); opacity:.45; }}
.is-dark .ppt-orb-a,.is-dark .ppt-orb-b {{ background:rgba(255,255,255,.1); }}
.ppt-slide-number {{ position:absolute; right:40px; bottom:32px; font-size:12px; font-weight:800; letter-spacing:.18em; color:rgba(100,116,139,.7); }}
.is-dark .ppt-slide-number {{ color:rgba(255,255,255,.38); }}
.ppt-eyebrow {{ color:var(--ppt-accent-text); font-size:13px; font-weight:900; text-transform:uppercase; letter-spacing:.2em; }}
.is-dark .ppt-eyebrow {{ color:rgba(255,255,255,.45); }}
.ppt-cover-label {{ position:absolute; left:56px; top:48px; display:flex; align-items:center; gap:12px; color:rgba(255,255,255,.62); font-size:13px; font-weight:900; text-transform:uppercase; letter-spacing:.24em; }}
.ppt-cover-label span,.ppt-heading span,.ppt-closing span,.ppt-title-row span {{ display:block; height:8px; width:64px; border-radius:999px; background:var(--ppt-accent); }}
.ppt-cover-copy {{ position:absolute; left:56px; top:158px; width:660px; }}
.ppt-cover-copy h1 {{ font-size:62px; line-height:.96; font-weight:950; }}
.ppt-cover-copy p {{ margin-top:28px; max-width:540px; color:rgba(255,255,255,.68); font-size:22px; line-height:1.35; font-weight:600; }}
.ppt-cover-block {{ position:absolute; right:56px; bottom:64px; width:160px; height:160px; border-radius:34px; background:var(--ppt-accent); }}
.ppt-section-rule {{ position:absolute; left:0; top:0; width:12px; height:100%; background:var(--ppt-accent); }}
.ppt-section-copy {{ position:absolute; left:80px; top:112px; width:760px; }}
.ppt-section-copy h2 {{ margin-top:28px; font-size:56px; line-height:1.02; font-weight:950; }}
.ppt-section-copy p {{ margin-top:24px; max-width:620px; color:rgba(255,255,255,.64); font-size:22px; line-height:1.35; }}
.ppt-heading {{ position:absolute; left:48px; top:48px; right:48px; }}
.ppt-heading.narrow {{ width:430px; }}
.ppt-heading h2,.ppt-topline h2 {{ max-width:650px; font-size:42px; line-height:1.04; font-weight:950; color:var(--ppt-text); }}
.ppt-heading p,.ppt-topline p {{ margin-top:16px; max-width:540px; color:var(--ppt-muted); font-size:17px; line-height:1.45; }}
.ppt-bullets {{ position:absolute; right:48px; top:132px; width:460px; display:grid; gap:16px; }}
.ppt-item {{ display:flex; gap:16px; align-items:flex-start; border-radius:22px; background:#fff; padding:16px 20px; box-shadow:0 18px 40px rgba(15,23,42,.08); color:#1e293b; }}
.ppt-marker {{ flex:0 0 auto; display:flex; align-items:center; justify-content:center; width:36px; height:36px; border-radius:999px; background:var(--ppt-accent); color:#fff; font-size:13px; font-weight:900; }}
.ppt-item p {{ font-size:20px; line-height:1.28; font-weight:800; }}
.ppt-title-row {{ position:absolute; left:48px; top:40px; right:48px; display:flex; align-items:flex-end; justify-content:space-between; }}
.ppt-title-row h2 {{ width:580px; font-size:40px; line-height:1.04; font-weight:950; }}
.ppt-compare {{ position:absolute; left:48px; right:48px; top:146px; display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
.ppt-compare > div {{ height:330px; border-radius:28px; background:#fff; padding:32px; box-shadow:0 18px 50px rgba(15,23,42,.08); }}
.ppt-compare > .is-dark,.ppt-stat.is-dark,.ppt-insight {{ background:var(--ppt-dark); color:#fff; }}
.ppt-compare h3 {{ margin-bottom:24px; color:var(--ppt-muted); font-size:15px; font-weight:900; text-transform:uppercase; letter-spacing:.18em; }}
.ppt-compare .is-dark h3 {{ color:rgba(255,255,255,.55); }}
.ppt-compare .ppt-item {{ padding:0; margin-bottom:16px; background:transparent; box-shadow:none; }}
.ppt-compare .ppt-marker {{ width:10px; height:10px; margin-top:8px; color:transparent; }}
.ppt-compare .ppt-item p {{ font-size:18px; }}
.ppt-compare .is-dark .ppt-item p {{ color:#fff; }}
.ppt-stats {{ position:absolute; left:48px; right:48px; bottom:88px; display:grid; grid-template-columns:repeat(3,1fr); gap:20px; }}
.ppt-stat {{ height:210px; border-radius:30px; background:#fff; padding:28px; box-shadow:0 18px 50px rgba(15,23,42,.08); }}
.ppt-stat strong {{ display:block; font-size:60px; line-height:1; font-weight:950; }}
.ppt-stat h3 {{ margin-top:28px; font-size:20px; line-height:1.15; font-weight:900; }}
.ppt-stat p {{ margin-top:12px; color:var(--ppt-muted); font-size:13px; line-height:1.35; }}
.ppt-stat.is-dark p {{ color:rgba(255,255,255,.48); }}
.ppt-timeline {{ position:absolute; left:56px; right:56px; top:178px; display:grid; grid-template-columns:repeat(5,1fr); gap:16px; }}
.ppt-timeline:before {{ content:""; position:absolute; left:0; right:0; top:72px; height:4px; border-radius:999px; background:#e2e8f0; }}
.ppt-timeline div {{ position:relative; z-index:1; }}
.ppt-timeline span {{ display:flex; align-items:center; justify-content:center; width:48px; height:48px; border-radius:999px; background:var(--ppt-accent); color:#fff; font-size:13px; font-weight:900; }}
.ppt-timeline h3 {{ margin-top:20px; color:#0f172a; font-size:19px; line-height:1.12; font-weight:950; }}
.ppt-timeline p {{ margin-top:12px; color:var(--ppt-muted); font-size:13px; line-height:1.35; }}
.ppt-topline {{ position:absolute; left:48px; right:48px; top:40px; display:flex; align-items:flex-start; justify-content:space-between; }}
.ppt-pill {{ border-radius:999px; background:var(--ppt-accent-soft); color:var(--ppt-accent-text); padding:8px 16px; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.18em; }}
.ppt-chart-layout {{ position:absolute; left:48px; right:48px; top:184px; display:grid; grid-template-columns:1fr 300px; gap:28px; }}
.ppt-chart {{ height:300px; border-radius:32px; background:#fff; padding:28px; display:flex; align-items:flex-end; gap:20px; box-shadow:0 22px 56px rgba(15,23,42,.1); }}
.ppt-bar-wrap {{ flex:1; display:flex; flex-direction:column; align-items:center; gap:12px; }}
.ppt-bar {{ width:100%; border-radius:18px 18px 0 0; background:var(--ppt-accent); text-align:center; color:#fff; font-size:15px; font-weight:900; padding-top:12px; }}
.ppt-bar-wrap b {{ color:#64748b; font-size:12px; }}
.ppt-insight {{ height:300px; border-radius:32px; padding:28px; box-shadow:0 22px 56px rgba(15,23,42,.16); }}
.ppt-insight span {{ color:rgba(255,255,255,.45); font-size:13px; font-weight:900; text-transform:uppercase; letter-spacing:.18em; }}
.ppt-insight strong {{ display:block; margin-top:28px; font-size:52px; line-height:1; font-weight:950; }}
.ppt-insight p {{ margin-top:24px; color:rgba(255,255,255,.78); font-size:18px; line-height:1.32; font-weight:800; }}
.ppt-quote {{ position:absolute; left:56px; top:88px; width:760px; }}
.ppt-quote span {{ color:rgba(255,255,255,.16); font-size:82px; font-weight:950; line-height:1; }}
.ppt-quote h2 {{ font-size:38px; line-height:1.16; font-weight:950; }}
.ppt-quote p {{ margin-top:32px; color:rgba(255,255,255,.45); font-size:16px; font-weight:900; text-transform:uppercase; letter-spacing:.2em; }}
.ppt-image-band {{ position:absolute; left:0; top:0; width:390px; height:100%; background:var(--ppt-dark); }}
.ppt-image-box {{ position:absolute; left:176px; top:92px; width:380px; height:380px; overflow:hidden; border-radius:34px; background:var(--ppt-accent); box-shadow:0 20px 60px rgba(15,23,42,.2); }}
.ppt-image-box img {{ width:100%; height:100%; object-fit:cover; }}
.ppt-image-copy {{ position:absolute; right:56px; top:94px; width:450px; }}
.ppt-image-copy h2 {{ font-size:40px; line-height:1.05; font-weight:950; }}
.ppt-image-copy > p {{ margin-top:20px; color:var(--ppt-muted); font-size:19px; line-height:1.45; font-weight:600; }}
.ppt-image-copy .ppt-item {{ margin-top:12px; padding:0; background:transparent; box-shadow:none; }}
.ppt-image-copy .ppt-marker {{ width:10px; height:10px; margin-top:8px; color:transparent; }}
.ppt-image-copy .ppt-item p {{ font-size:17px; }}
.ppt-closing {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }}
.ppt-closing h2 {{ margin-top:36px; max-width:760px; font-size:56px; line-height:1.02; font-weight:950; }}
.ppt-closing p {{ margin-top:24px; max-width:620px; color:rgba(255,255,255,.64); font-size:21px; line-height:1.38; }}
</style>
<div class="agenticos-ppt-preview">{slides}</div>
""".strip()


class PptArtifactService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def create_from_text(self, session_id: str, text: str) -> dict[str, Any] | None:
        extracted = extract_ppt_deck_from_text(text)
        if extracted is None:
            return None
        code, deck = extracted
        artifact_id = uuid.uuid4().hex
        preview_html = render_ppt_html(deck)
        with self.session_factory() as db:
            db.add(
                PptArtifactModel(
                    artifact_id=artifact_id,
                    session_id=session_id,
                    title=deck["title"],
                    slide_count=len(deck["slides"]),
                    deck_json=dump_json(deck),
                    preview_html=preview_html,
                    metadata_json=dump_json({"source": "pptdeck", "raw_chars": len(code)}),
                )
            )
            db.commit()
        return {
            "artifact_id": artifact_id,
            "session_id": session_id,
            "title": deck["title"],
            "slide_count": len(deck["slides"]),
            "html": preview_html,
        }

    async def get(self, artifact_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            row = db.get(PptArtifactModel, artifact_id)
            if row is None:
                return None
            return {
                "artifact_id": row.artifact_id,
                "session_id": row.session_id,
                "title": row.title,
                "slide_count": row.slide_count,
                "html": row.preview_html,
                "metadata": load_json(row.metadata_json, {}),
            }
