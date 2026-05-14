"""Academic template — structured grid, numbered hierarchies, clear data, training/research style."""
from typing import Any

from app.services.ppt.base_template import PPT_PAGE_CLASS, BaseTemplate, _h, build_chart_bars
from app.services.ppt.registry import register

COLORS_LIGHT = (
    "--ppt-bg:#f0f4f8;--ppt-dark:#1e293b;"
    "--ppt-accent:#2563eb;--ppt-accent-soft:#dbeafe;"
    "--ppt-accent-text:#1d4ed8;"
    "--ppt-text:#1e293b;--ppt-muted:#64748b;"
    "--ppt-grid:rgba(37,99,235,0.06);"
)
COLORS_DARK = (
    "--ppt-bg:#0f172a;--ppt-dark:#070e1a;"
    "--ppt-accent:#3b82f6;--ppt-accent-soft:rgba(59,130,246,0.12);"
    "--ppt-accent-text:#60a5fa;"
    "--ppt-text:#fff;--ppt-muted:rgba(255,255,255,0.55);"
    "--ppt-grid:rgba(255,255,255,0.04);"
)


def _academic_frame(inner: str, index: int, total: int, *, dark: bool = False) -> str:
    colors = COLORS_DARK if dark else COLORS_LIGHT
    border = "border-[var(--ppt-accent)]/10" if not dark else "border-white/[0.06]"
    footer_hint = (
        f'<div class="absolute left-0 right-0 bottom-0 h-[32px] bg-[var(--ppt-accent)]/3 flex items-center px-8">'
        f'<span class="text-[10px] font-medium text-[var(--ppt-muted)] tracking-[0.1em]">Slide {index + 1} of {total}</span>'
        f'</div>'
    )
    header = (
        f'<div class="absolute left-0 right-0 top-0 h-[3px] bg-[var(--ppt-accent)]"></div>'
    )
    grid = (
        f'<div class="absolute inset-0 opacity-[0.3] '
        f'bg-[linear-gradient(90deg,var(--ppt-grid)_1px,transparent_1px),'
        f'linear-gradient(0deg,var(--ppt-grid)_1px,transparent_1px)] '
        f'bg-[length:80px_80px]"></div>'
    )
    return (
        f'<div class="ppt-preview-card w-[720px] h-[405px] mb-8 origin-top-left">'
        f'<section class="{PPT_PAGE_CLASS} relative w-[1000px] h-[562.5px] overflow-hidden '
        f'rounded-[8px] border {border} bg-[var(--ppt-bg)] text-[var(--ppt-text)]" '
        f'style="{colors}">'
        f'{grid}{header}'
        f'{inner}'
        f'{footer_hint}'
        f'</section></div>'
    )


@register("academic")
class AcademicTemplate(BaseTemplate):
    name = "academic"
    label = "学术培训风 · 结构化网格"

    def color_profile(self, dark: bool = False) -> str:
        return COLORS_DARK if dark else COLORS_LIGHT

    def render_frame(self, inner: str, index: int, total: int, *, dark: bool = False) -> str:
        return _academic_frame(inner, index, total, dark=dark)

    def render_cover(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center pt-6">'
            f'<div class="inline-block rounded-full bg-[var(--ppt-accent)]/10 border border-[var(--ppt-accent)]/25 px-5 py-1.5 text-[var(--ppt-accent)] text-xs font-bold uppercase tracking-[0.15em] mb-8">{_h(slide.get("eyebrow") or deck.get("author") or "AgenticOS")}</div>'
            f'<h1 class="max-w-[720px] text-[52px] leading-[1.06] font-black text-white">{_h(slide["title"])}</h1>'
            f'<div class="mt-8 w-20 h-[2px] bg-[var(--ppt-accent)]/40"></div>'
            f'<p class="mt-8 max-w-[580px] text-white/50 text-[20px] leading-[1.45]">{_h(slide.get("subtitle") or deck.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_section(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex items-center px-16">'
            f'<div class="w-1 h-[200px] bg-[var(--ppt-accent)] rounded-full mr-10 flex-shrink-0"></div>'
            f'<div>'
            f'<span class="text-[var(--ppt-accent)] text-[14px] font-bold uppercase tracking-[0.2em]">{_h(slide.get("eyebrow") or "Chapter")}</span>'
            f'<h2 class="mt-4 text-[50px] leading-[1.04] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 text-white/45 text-[20px] leading-[1.4]">{_h(slide.get("subtitle"))}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_bullets(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        body = slide.get("body")
        items = slide.get("items") or ([body] if body else ["补充要点"])
        cards = ""
        for idx, item in enumerate(items[:4]):
            cards += (
                f'<div class="rounded-[12px] bg-white p-5 shadow-[0_8px_24px_rgba(0,0,0,0.04)] border border-[var(--ppt-accent)]/8">'
                f'<div class="flex items-center gap-3">'
                f'<span class="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-[6px] bg-[var(--ppt-accent)] text-white text-xs font-bold">{idx + 1}</span>'
                f'<div><p class="text-[17px] leading-[1.3] font-bold text-[var(--ppt-text)]">{_h(item)}</p></div>'
                f'</div></div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12 flex items-start justify-between">'
            f'<div class="max-w-[480px]">'
            f'<span class="text-[var(--ppt-accent-text)] text-[12px] font-bold uppercase tracking-[0.15em] bg-[var(--ppt-accent-soft)] px-3 py-1 rounded-[4px]">Key Points</span>'
            f'<h2 class="mt-4 text-[38px] leading-[1.06] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[15px] leading-[1.5]">{_h(slide.get("subtitle"))}</p>'
            f'</div></div>'
            f'<div class="absolute left-12 right-12 top-[160px] grid grid-cols-2 gap-4">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_comparison(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        left_html = "".join(
            f'<div class="py-3 px-4 {"bg-[var(--ppt-accent-soft)]" if i == 0 else ""} rounded-[6px]">'
            f'<p class="text-[15px] leading-[1.3] font-semibold text-[var(--ppt-text)]">{_h(item)}</p></div>'
            for i, item in enumerate((slide.get("leftItems") or ["补充项"])[:4])
        )
        right_html = "".join(
            f'<div class="py-3 px-4 {"bg-white/10" if i == 0 else ""} rounded-[6px]">'
            f'<p class="text-[15px] leading-[1.3] font-bold text-white">{_h(item)}</p></div>'
            for i, item in enumerate((slide.get("rightItems") or ["补充项"])[:4])
        )
        inner = (
            f'<div class="absolute left-10 top-10 right-10">'
            f'<h2 class="text-[36px] leading-[1.06] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-10 right-10 top-[110px] grid grid-cols-2 gap-6">'
            f'<div class="rounded-[12px] bg-white p-6 shadow-[0_8px_24px_rgba(0,0,0,0.04)] border border-[var(--ppt-accent)]/10">'
            f'<h3 class="mb-5 text-[var(--ppt-muted)] text-[13px] font-bold uppercase tracking-[0.15em] flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-[var(--ppt-muted)]"></span>{_h(slide.get("leftTitle") or "Option A")}</h3>{left_html}</div>'
            f'<div class="rounded-[12px] bg-[var(--ppt-dark)] p-6 shadow-[0_8px_24px_rgba(0,0,0,0.08)] text-white">'
            f'<h3 class="mb-5 text-[var(--ppt-accent-text)] text-[13px] font-bold uppercase tracking-[0.15em] flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-[var(--ppt-accent)]"></span>{_h(slide.get("rightTitle") or "Option B")}</h3>{right_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_stats(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        stats = slide.get("stats") or [
            {"value": "3.2x", "label": "效率提升"}, {"value": "-41%", "label": "成本降低"}, {"value": "92%", "label": "满意度"}
        ]
        cards = ""
        for si, stat in enumerate(stats[:3]):
            is_first = si == 0
            bg = "bg-[var(--ppt-dark)] text-white" if is_first else "bg-white border border-[var(--ppt-accent)]/8"
            cap = "text-white/45" if is_first else "text-[var(--ppt-muted)]"
            cards += (
                f'<div class="h-[200px] rounded-[12px] {bg} p-6 shadow-[0_8px_24px_rgba(0,0,0,0.04)]">'
                f'<strong class="block text-[52px] leading-none font-black">{_h(stat.get("value"))}</strong>'
                f'<h3 class="mt-5 text-[17px] font-bold">{_h(stat.get("label"))}</h3>'
                f'<p class="mt-2 {cap} text-[12px] leading-[1.3]">{_h(stat.get("caption"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<span class="text-[var(--ppt-accent-text)] text-[12px] font-bold uppercase tracking-[0.15em] bg-[var(--ppt-accent-soft)] px-3 py-1 rounded-[4px]">Results</span>'
            f'<h2 class="mt-4 text-[38px] leading-[1.06] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-2 text-[var(--ppt-muted)] text-[15px]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute left-12 right-12 bottom-[60px] grid grid-cols-3 gap-5">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_timeline(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        timeline = slide.get("timeline") or [
            {"label": "Phase 1", "title": "定义目标"}, {"label": "Phase 2", "title": "生成内容"}, {"label": "Phase 3", "title": "导出文件"}
        ]
        nodes = ""
        for ti, item in enumerate(timeline[:5]):
            is_done = ti < 2
            c = "bg-[var(--ppt-accent)] text-white" if is_done else "bg-white border-2 border-[var(--ppt-accent)]/30 text-[var(--ppt-muted)]"
            nodes += (
                f'<div class="flex-1 flex flex-col items-center relative z-[1]">'
                f'<span class="w-12 h-12 rounded-[6px] {c} flex items-center justify-center text-[11px] font-bold rotate-45">'
                f'<span class="-rotate-45">{_h(item.get("label") or f"0{ti + 1}")}</span></span>'
                f'<h3 class="mt-6 text-[16px] font-bold text-[var(--ppt-text)]">{_h(item.get("title"))}</h3>'
                f'<p class="mt-2 text-[12px] text-[var(--ppt-muted)] text-center leading-[1.3]">{_h(item.get("body"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<h2 class="text-[38px] leading-[1.06] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[140px] flex gap-4">'
            f'<div class="absolute left-[6%] right-[6%] top-[24px] h-[3px] bg-[var(--ppt-accent)]/15"></div>'
            f'{nodes}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

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
            f'<div class="absolute left-12 right-12 top-8 flex items-start justify-between">'
            f'<div>'
            f'<span class="text-[var(--ppt-accent-text)] text-[12px] font-bold uppercase tracking-[0.15em] bg-[var(--ppt-accent-soft)] px-3 py-1 rounded-[4px]">Data Analysis</span>'
            f'<h2 class="mt-3 max-w-[550px] text-[36px] leading-[1.06] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-2 text-[var(--ppt-muted)] text-[15px]">{_h(slide.get("subtitle"))}</p>'
            f'</div></div>'
            f'<div class="absolute left-12 right-12 top-[150px] grid grid-cols-[1fr_280px] gap-6">'
            f'<div class="h-[290px] rounded-[12px] bg-white p-6 flex items-end gap-5 shadow-[0_8px_24px_rgba(0,0,0,0.04)] border border-[var(--ppt-accent)]/10">{bars}</div>'
            f'<div class="h-[290px] rounded-[12px] bg-[var(--ppt-dark)] p-6 shadow-[0_8px_24px_rgba(0,0,0,0.08)] text-white">'
            f'<span class="text-white/40 text-[11px] font-bold uppercase tracking-[0.15em]">Key Insight</span>'
            f'<strong class="block mt-5 text-[48px] leading-none font-black">{_h(insight_val)}{_h(chart.get("unit"))}</strong>'
            f'<p class="mt-5 text-white/65 text-[15px] leading-[1.4]">{_h(slide.get("body") or "关键指标呈现上升趋势，适合作为方案价值或阶段进展的主证据。")}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_quote(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center px-20">'
            f'<span class="text-[var(--ppt-accent)]/30 text-[100px] leading-none font-serif italic">&ldquo;</span>'
            f'<h2 class="-mt-6 max-w-[700px] text-[36px] leading-[1.2] font-serif italic text-white">{_h(slide.get("quote") or slide["title"])}</h2>'
            f'<div class="mt-8 w-16 h-[1px] bg-[var(--ppt-accent)]/40"></div>'
            f'<p class="mt-6 text-white/35 text-[14px] font-bold uppercase tracking-[0.2em]">{_h(slide.get("author"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_imageText(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        image_tag = f'<img src="{_h(slide.get("imageUrl"))}" alt="" class="w-full h-full object-cover" />' if slide.get("imageUrl") else ""
        items_html = "".join(
            f'<div class="flex items-center gap-3 py-2.5 border-b border-[var(--ppt-accent)]/8">'
            f'<span class="w-5 h-5 rounded-[4px] bg-[var(--ppt-accent)]/15 flex items-center justify-center text-[10px] font-bold text-[var(--ppt-accent-text)]">{i + 1}</span>'
            f'<p class="text-[15px] font-semibold text-[var(--ppt-text)]">{_h(item)}</p></div>'
            for i, item in enumerate((slide.get("items") or [])[:3])
        )
        inner = (
            f'<div class="absolute left-12 top-[50px] w-[420px] h-[460px] rounded-[12px] bg-[var(--ppt-dark)] flex items-center justify-center overflow-hidden border border-[var(--ppt-accent)]/20">{image_tag}</div>'
            f'<div class="absolute right-12 top-[60px] w-[440px]">'
            f'<span class="text-[var(--ppt-accent-text)] text-[12px] font-bold uppercase tracking-[0.15em] bg-[var(--ppt-accent-soft)] px-3 py-1 rounded-[4px]">Diagram</span>'
            f'<h2 class="mt-4 text-[36px] leading-[1.08] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[16px] leading-[1.5]">{_h(slide.get("body") or slide.get("subtitle"))}</p>'
            f'<div class="mt-6">{items_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_closing(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<div class="rounded-full bg-[var(--ppt-accent)]/10 border border-[var(--ppt-accent)]/25 px-5 py-1.5 text-[var(--ppt-accent)] text-xs font-bold uppercase tracking-[0.15em] mb-8">Summary</div>'
            f'<h2 class="max-w-[740px] text-[48px] leading-[1.06] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-6 max-w-[600px] text-white/45 text-[19px] leading-[1.45]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)
