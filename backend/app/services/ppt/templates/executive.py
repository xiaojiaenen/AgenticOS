"""Executive template — deep navy + gold, sharp geometric corners, authoritative and clean."""
from html import escape
from typing import Any

from app.services.ppt.base_template import (
    PPT_PAGE_CLASS,
    BaseTemplate,
    _h,
    build_accent_dot_items,
    build_chart_bars,
    build_numbered_items,
)
from app.services.ppt.registry import register

# ---- colors ----

COLORS_LIGHT = (
    "--ppt-bg:#f0f3f8;--ppt-dark:#0a1628;"
    "--ppt-accent:#c8a960;--ppt-accent-soft:#f5f0e0;"
    "--ppt-accent-text:#8b7940;"
    "--ppt-text:#0f172a;--ppt-muted:#64748b;"
    "--ppt-grid:rgba(15,23,42,0.04);"
)
COLORS_DARK = (
    "--ppt-bg:#0a1628;--ppt-dark:#060f1e;"
    "--ppt-accent:#c8a960;--ppt-accent-soft:rgba(200,169,96,0.15);"
    "--ppt-accent-text:#c8a960;"
    "--ppt-text:#fff;--ppt-muted:rgba(255,255,255,0.60);"
    "--ppt-grid:rgba(255,255,255,0.04);"
)


def _executive_frame(inner: str, index: int, total: int, *, dark: bool = False) -> str:
    """Sharp geometric corner decorations, dot grid on light, clean frame."""
    colors = COLORS_DARK if dark else COLORS_LIGHT
    border = "border-black/[0.04]" if not dark else "border-white/[0.06]"
    page_color = "text-white/35" if dark else "text-[rgba(100,116,139,0.6)]"
    # Sharp corner triangles in accent color
    corner = (
        f'<div class="absolute -right-20 -top-24 w-60 h-60 bg-[var(--ppt-accent)] opacity-[0.06] '
        f'rotate-45 rounded-[4px]"></div>'
    )
    grid = (
        f'<div class="absolute inset-0 opacity-[0.35] '
        f'bg-[linear-gradient(90deg,var(--ppt-grid)_1px,transparent_1px),'
        f'linear-gradient(0deg,var(--ppt-grid)_1px,transparent_1px)] '
        f'bg-[length:48px_48px]"></div>'
    ) if not dark else ""
    accent_bar = (
        f'<div class="absolute right-10 top-10 w-12 h-1 rounded-full bg-[var(--ppt-accent)] opacity-60"></div>'
    )
    return (
        f'<div class="ppt-preview-card w-[720px] h-[405px] mb-8 origin-top-left">'
        f'<section class="{PPT_PAGE_CLASS} relative w-[1000px] h-[562.5px] overflow-hidden '
        f'rounded-[4px] border {border} bg-[var(--ppt-bg)] text-[var(--ppt-text)]" '
        f'style="box-shadow:0 20px 60px rgba(15,23,42,0.10);{colors}">'
        f'{grid}{corner}{accent_bar}'
        f'{inner}'
        f'<div class="absolute right-10 bottom-8 text-xs font-black tracking-[0.18em] {page_color}">{index + 1:02d} / {total:02d}</div>'
        f'<div class="absolute left-10 bottom-8 w-8 h-[3px] rounded-full bg-[var(--ppt-accent)] opacity-40"></div>'
        f'</section></div>'
    )


@register("executive")
class ExecutiveTemplate(BaseTemplate):
    name = "executive"
    label = "深蓝+金色 · 企业商务风"

    def color_profile(self, dark: bool = False) -> str:
        return COLORS_DARK if dark else COLORS_LIGHT

    def render_frame(self, inner: str, index: int, total: int, *, dark: bool = False) -> str:
        return _executive_frame(inner, index, total, dark=dark)

    # ---- cover ----
    def render_cover(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute left-14 top-12 flex items-center gap-3 text-white/55 text-[13px] font-black uppercase tracking-[0.24em]">'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'{_h(slide.get("eyebrow") or deck.get("author") or "AgenticOS")}'
            f'</div>'
            f'<div class="absolute left-14 top-[158px] w-[660px]">'
            f'<h1 class="text-[62px] leading-[0.94] font-black text-white tracking-[-0.02em]">{_h(slide["title"])}</h1>'
            f'<p class="mt-7 max-w-[540px] text-white/65 text-[22px] leading-[1.35] font-semibold">{_h(slide.get("subtitle") or deck.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute -right-8 -bottom-8 w-56 h-56 bg-[var(--ppt-accent)] opacity-[0.08] rotate-45 rounded-[4px]"></div>'
            f'<div class="absolute right-14 bottom-14 w-24 h-1 rounded-full bg-[var(--ppt-accent)]"></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    # ---- section ----
    def render_section(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute left-0 top-0 w-[4px] h-full bg-[var(--ppt-accent)]"></div>'
            f'<div class="absolute left-20 top-28 w-[760px]">'
            f'<span class="text-[var(--ppt-accent-text)] text-[13px] font-black uppercase tracking-[0.2em]">{_h(slide.get("eyebrow") or "Section")}</span>'
            f'<h2 class="mt-7 text-[56px] leading-[1.02] font-black text-white tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<p class="mt-6 max-w-[620px] text-white/55 text-[22px] leading-[1.35]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    # ---- bullets (default) ----
    def render_bullets(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        body = slide.get("body")
        items = slide.get("items") or ([body] if body else ["补充要点"])
        inner = (
            f'<div class="absolute left-12 top-12 right-12 flex items-end justify-between">'
            f'<div class="w-[430px]">'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)] mb-4"></span>'
            f'<h2 class="max-w-[650px] text-[42px] leading-[1.04] font-black text-[var(--ppt-text)] tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 max-w-[540px] text-[var(--ppt-muted)] text-[17px] leading-[1.45]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'</div>'
            f'<div class="absolute right-12 top-[132px] w-[460px] grid gap-4">{build_numbered_items(items)}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- comparison ----
    def render_comparison(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        left_title = _h(slide.get("leftTitle") or "Before")
        right_title = _h(slide.get("rightTitle") or "After")
        left_html = "".join(
            f'<div class="flex gap-4 items-start mb-4">'
            f'<div class="w-[10px] h-[10px] mt-2 flex-shrink-0 rounded-full bg-[var(--ppt-accent)]"></div>'
            f'<p class="text-[18px] leading-[1.28] font-extrabold">{_h(item)}</p></div>'
            for item in (slide.get("leftItems") or ["补充对比项"])[:4]
        )
        right_html = "".join(
            f'<div class="flex gap-4 items-start mb-4">'
            f'<div class="w-[10px] h-[10px] mt-2 flex-shrink-0 rounded-full bg-[var(--ppt-accent)]"></div>'
            f'<p class="text-[18px] leading-[1.28] font-extrabold text-white">{_h(item)}</p></div>'
            for item in (slide.get("rightItems") or ["补充对比项"])[:4]
        )
        inner = (
            f'<div class="absolute left-12 top-10 right-12 flex items-end justify-between">'
            f'<h2 class="w-[580px] text-[40px] leading-[1.04] font-black text-[var(--ppt-text)] tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[146px] grid grid-cols-2 gap-6">'
            f'<div class="h-[330px] rounded-[8px] bg-white p-8 shadow-[0_18px_50px_rgba(15,23,42,0.06)] border border-[var(--ppt-accent)]/15">'
            f'<h3 class="mb-6 text-[var(--ppt-muted)] text-[15px] font-black uppercase tracking-[0.18em]">{left_title}</h3>'
            f'{left_html}</div>'
            f'<div class="h-[330px] rounded-[8px] bg-[var(--ppt-dark)] p-8 shadow-[0_18px_50px_rgba(15,23,42,0.08)] text-white">'
            f'<h3 class="mb-6 text-white/50 text-[15px] font-black uppercase tracking-[0.18em]">{right_title}</h3>'
            f'{right_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- stats ----
    def render_stats(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        stats = slide.get("stats") or [
            {"value": "3x", "label": "效率提升"}, {"value": "80%", "label": "重复工作减少"}, {"value": "24/7", "label": "持续响应"}
        ]
        cards = ""
        for si, stat in enumerate(stats[:3]):
            is_first = si == 0
            bg = "bg-[var(--ppt-dark)] text-white" if is_first else "bg-white"
            caption_color = "text-white/45" if is_first else "text-[var(--ppt-muted)]"
            cards += (
                f'<div class="h-[210px] rounded-[8px] {bg} p-7 shadow-[0_14px_40px_rgba(15,23,42,0.06)]">'
                f'<strong class="block text-[60px] leading-none font-black">{_h(stat.get("value"))}</strong>'
                f'<h3 class="mt-7 text-[20px] leading-[1.15] font-black">{_h(stat.get("label"))}</h3>'
                f'<p class="mt-3 {caption_color} text-[13px] leading-[1.35]">{_h(stat.get("caption"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)] mb-4"></span>'
            f'<h2 class="max-w-[650px] text-[42px] leading-[1.04] font-black text-[var(--ppt-text)] tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 max-w-[540px] text-[var(--ppt-muted)] text-[17px] leading-[1.45]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute left-12 right-12 bottom-[88px] grid grid-cols-3 gap-5">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- timeline ----
    def render_timeline(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        timeline = slide.get("timeline") or [
            {"label": "01", "title": "定义目标"}, {"label": "02", "title": "生成内容"}, {"label": "03", "title": "导出文件"}
        ]
        nodes = ""
        for ti, item in enumerate(timeline[:5]):
            nodes += (
                f'<div class="relative z-[1] flex flex-col">'
                f'<span class="flex items-center justify-center w-12 h-12 rounded-[4px] '
                f'bg-[var(--ppt-accent)] text-white text-[13px] font-black">{_h(item.get("label") or f"0{ti + 1}")}</span>'
                f'<h3 class="mt-5 text-[#0f172a] text-[19px] leading-[1.12] font-black">{_h(item.get("title"))}</h3>'
                f'<p class="mt-3 text-[var(--ppt-muted)] text-[13px] leading-[1.35]">{_h(item.get("body"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)] mb-4"></span>'
            f'<h2 class="max-w-[650px] text-[42px] leading-[1.04] font-black text-[var(--ppt-text)] tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-14 right-14 top-[178px] grid grid-cols-5 gap-4">'
            f'<div class="absolute left-0 right-0 top-[72px] h-[2px] rounded-full bg-[var(--ppt-accent)]/20"></div>'
            f'{nodes}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- chart ----
    def render_chart(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        chart = slide.get("chart") or {
            "type": "bar", "labels": ["入口", "转化", "留存", "复购"],
            "values": [32, 58, 74, 86], "unit": "%",
        }
        labels = chart.get("labels") or []
        values = chart.get("values") or []
        max_value = max([float(v) for v in values] + [1])
        bars = build_chart_bars(labels, values, chart.get("unit", ""), max_value)
        insight_val = max(values) if values else 0
        inner = (
            f'<div class="absolute left-12 right-12 top-10 flex items-start justify-between">'
            f'<div><span class="text-[var(--ppt-accent-text)] text-[13px] font-black uppercase tracking-[0.2em]">Data view</span>'
            f'<h2 class="max-w-[650px] text-[42px] leading-[1.04] font-black text-[var(--ppt-text)] tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 max-w-[540px] text-[var(--ppt-muted)] text-[17px] leading-[1.45]">{_h(slide.get("subtitle"))}</p></div>'
            f'<span class="rounded-full bg-[var(--ppt-accent-soft)] text-[var(--ppt-accent-text)] px-4 py-2 text-xs font-black uppercase tracking-[0.18em]">{_h(chart.get("type", "bar"))} chart</span>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[184px] grid grid-cols-[1fr_300px] gap-7">'
            f'<div class="h-[300px] rounded-[8px] bg-white p-7 flex items-end gap-5 shadow-[0_18px_50px_rgba(15,23,42,0.06)] border border-[var(--ppt-accent)]/10">{bars}</div>'
            f'<div class="h-[300px] rounded-[8px] bg-[var(--ppt-dark)] p-7 shadow-[0_18px_50px_rgba(15,23,42,0.12)] text-white">'
            f'<span class="text-white/40 text-[13px] font-black uppercase tracking-[0.18em]">Insight</span>'
            f'<strong class="block mt-7 text-[52px] leading-none font-black">{_h(insight_val)}{_h(chart.get("unit"))}</strong>'
            f'<p class="mt-6 text-white/75 text-[18px] leading-[1.32] font-extrabold">{_h(slide.get("body") or "关键指标呈现上升趋势。")}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- quote ----
    def render_quote(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute left-14 top-[88px] w-[760px]">'
            f'<span class="text-white/10 text-[82px] font-black leading-none">&ldquo;</span>'
            f'<h2 class="text-[38px] leading-[1.16] font-black text-white">{_h(slide.get("quote") or slide["title"])}</h2>'
            f'<div class="mt-8 flex items-center gap-3">'
            f'<span class="block h-[3px] w-10 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'<p class="text-white/40 text-[16px] font-black uppercase tracking-[0.2em]">{_h(slide.get("author"))}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    # ---- imageText ----
    def render_imageText(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        image_tag = f'<img src="{_h(slide.get("imageUrl"))}" alt="" class="w-full h-full object-cover" />' if slide.get("imageUrl") else ""
        inner = (
            f'<div class="absolute left-0 top-0 w-[390px] h-full bg-[var(--ppt-dark)]"></div>'
            f'<div class="absolute left-[176px] top-[92px] w-[380px] h-[380px] overflow-hidden rounded-[8px] '
            f'bg-[var(--ppt-accent)] shadow-[0_20px_60px_rgba(15,23,42,0.15)]">{image_tag}</div>'
            f'<div class="absolute right-14 top-[94px] w-[450px]">'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)] mb-4"></span>'
            f'<h2 class="text-[40px] leading-[1.05] font-black text-[var(--ppt-text)] tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<p class="mt-5 text-[var(--ppt-muted)] text-[19px] leading-[1.45] font-semibold">{_h(slide.get("body") or slide.get("subtitle"))}</p>'
            f'<div class="mt-3">{build_accent_dot_items(slide.get("items") or [])}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- closing ----
    def render_closing(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<span class="block h-[3px] w-14 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'<h2 class="mt-9 max-w-[760px] text-[56px] leading-[1.02] font-black text-white tracking-[-0.01em]">{_h(slide["title"])}</h2>'
            f'<p class="mt-6 max-w-[620px] text-white/55 text-[21px] leading-[1.38]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)
