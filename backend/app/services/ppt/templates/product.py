"""Product template — gradient backgrounds, glass-morphism cards, bold hero layouts, modern SaaS style."""
from typing import Any

from app.services.ppt.base_template import PPT_PAGE_CLASS, BaseTemplate, _h, build_chart_bars
from app.services.ppt.registry import register

COLORS_LIGHT = (
    "--ppt-bg:#f8fafc;--ppt-dark:#0f172a;"
    "--ppt-accent:#00d4aa;--ppt-accent-soft:rgba(0,212,170,0.10);"
    "--ppt-accent-text:#0f766e;"
    "--ppt-text:#0f172a;--ppt-muted:#64748b;"
)
COLORS_DARK = (
    "--ppt-bg:#0d1b2a;--ppt-dark:#070f1a;"
    "--ppt-accent:#00d4aa;--ppt-accent-soft:rgba(0,212,170,0.12);"
    "--ppt-accent-text:#00d4aa;"
    "--ppt-text:#fff;--ppt-muted:rgba(255,255,255,0.55);"
)


def _product_frame(inner: str, index: int, total: int, *, dark: bool = False) -> str:
    colors = COLORS_DARK if dark else COLORS_LIGHT
    border = "border-transparent" if dark else "border-black/[0.04]"
    page_badge = (
        f'<div class="absolute right-8 bottom-8 rounded-full bg-white/10 backdrop-blur-sm '
        f'border border-white/20 px-4 py-1.5 text-xs font-bold text-white/50 tracking-[0.12em]">'
        f'{index + 1:02d} / {total:02d}</div>'
    ) if dark else (
        f'<div class="absolute right-8 bottom-8 rounded-full bg-black/5 '
        f'px-4 py-1.5 text-xs font-bold text-[var(--ppt-muted)] tracking-[0.12em]">'
        f'{index + 1:02d} / {total:02d}</div>'
    )
    glow_orbs = (
        f'<div class="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full '
        f'bg-[var(--ppt-accent)] opacity-[0.06] blur-[80px]"></div>'
        f'<div class="absolute -bottom-32 -left-32 w-[400px] h-[400px] rounded-full '
        f'bg-[#e040fb] opacity-[0.04] blur-[80px]"></div>'
    ) if dark else ""
    return (
        f'<div class="ppt-preview-card w-[720px] h-[405px] mb-8 origin-top-left">'
        f'<section class="{PPT_PAGE_CLASS} relative w-[1000px] h-[562.5px] overflow-hidden '
        f'rounded-[24px] border {border} bg-[var(--ppt-bg)] text-[var(--ppt-text)]" '
        f'style="{colors}">'
        f'{glow_orbs}'
        f'{inner}'
        f'{page_badge}'
        f'</section></div>'
    )


@register("product")
class ProductTemplate(BaseTemplate):
    name = "product"
    label = "渐变毛玻璃 · 产品发布风"

    def color_profile(self, dark: bool = False) -> str:
        return COLORS_DARK if dark else COLORS_LIGHT

    def render_frame(self, inner: str, index: int, total: int, *, dark: bool = False) -> str:
        return _product_frame(inner, index, total, dark=dark)

    def render_cover(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<div class="rounded-full bg-[var(--ppt-accent)]/10 border border-[var(--ppt-accent)]/30 '
            f'px-5 py-1.5 text-[var(--ppt-accent)] text-xs font-black uppercase tracking-[0.2em] mb-8">'
            f'{_h(slide.get("eyebrow") or deck.get("author") or "AgenticOS")}</div>'
            f'<h1 class="max-w-[720px] text-[68px] leading-[0.94] font-black text-white">{_h(slide["title"])}</h1>'
            f'<p class="mt-6 max-w-[560px] text-white/55 text-[22px] leading-[1.35] font-medium">{_h(slide.get("subtitle") or deck.get("subtitle"))}</p>'
            f'<div class="mt-10 flex gap-3">'
            f'<span class="w-2 h-2 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'<span class="w-2 h-2 rounded-full bg-[var(--ppt-accent)]/40"></span>'
            f'<span class="w-2 h-2 rounded-full bg-[var(--ppt-accent)]/20"></span>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_section(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<span class="text-[var(--ppt-accent)] text-[16px] font-black uppercase tracking-[0.25em]">{_h(slide.get("eyebrow") or "Section")}</span>'
            f'<h2 class="mt-8 max-w-[700px] text-[58px] leading-[1.0] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-5 text-white/45 text-[20px] leading-[1.4]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_bullets(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        body = slide.get("body")
        items = slide.get("items") or ([body] if body else ["补充要点"])
        cards = ""
        for idx, item in enumerate(items[:4]):
            cards += (
                f'<div class="rounded-[20px] bg-white/70 backdrop-blur-sm border border-white/80 '
                f'p-5 shadow-[0_8px_30px_rgba(0,0,0,0.04)]">'
                f'<div class="flex items-center gap-3 mb-2">'
                f'<span class="w-8 h-8 rounded-full bg-[var(--ppt-accent)] text-white text-xs font-black '
                f'flex items-center justify-center">{idx + 1}</span>'
                f'<span class="text-[16px] font-black text-[var(--ppt-text)]">{_h(item)}</span>'
                f'</div></div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<div class="text-center">'
            f'<h2 class="text-[44px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[17px]">{_h(slide.get("subtitle"))}</p>'
            f'</div></div>'
            f'<div class="absolute left-12 right-12 top-[160px] grid grid-cols-2 gap-5">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_comparison(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        left_html = "".join(
            f'<p class="text-[17px] leading-[1.4] font-semibold text-[var(--ppt-muted)] py-3 border-b border-black/5">{_h(item)}</p>'
            for item in (slide.get("leftItems") or ["补充项"])[:4]
        )
        right_html = "".join(
            f'<p class="text-[17px] leading-[1.4] font-bold text-white py-3 border-b border-white/10">{_h(item)}</p>'
            for item in (slide.get("rightItems") or ["补充项"])[:4]
        )
        inner = (
            f'<div class="absolute left-12 top-10 right-12 text-center">'
            f'<h2 class="text-[40px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[120px] grid grid-cols-2 gap-8">'
            f'<div class="rounded-[28px] bg-white/60 backdrop-blur-sm border border-white/80 p-8 shadow-[0_12px_40px_rgba(0,0,0,0.04)]">'
            f'<h3 class="mb-6 text-[var(--ppt-muted)] text-[14px] font-bold uppercase tracking-[0.18em]">{_h(slide.get("leftTitle") or "Before")}</h3>{left_html}</div>'
            f'<div class="rounded-[28px] bg-[var(--ppt-dark)] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.12)] text-white relative overflow-hidden">'
            f'<div class="absolute -top-10 -right-10 w-32 h-32 rounded-full bg-[var(--ppt-accent)]/10 blur-[30px]"></div>'
            f'<h3 class="relative z-10 mb-6 text-[var(--ppt-accent)] text-[14px] font-bold uppercase tracking-[0.18em]">{_h(slide.get("rightTitle") or "After")}</h3>{right_html}</div>'
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
            bg = "bg-[var(--ppt-dark)] text-white" if is_first else "bg-white/60 backdrop-blur-sm border border-white/80"
            cap = "text-white/50" if is_first else "text-[var(--ppt-muted)]"
            cards += (
                f'<div class="rounded-[28px] {bg} p-8 shadow-[0_12px_40px_rgba(0,0,0,0.04)]">'
                f'<strong class="block text-[56px] leading-none font-black">{_h(stat.get("value"))}</strong>'
                f'<h3 class="mt-6 text-[18px] font-black">{_h(stat.get("label"))}</h3>'
                f'<p class="mt-2 {cap} text-[13px]">{_h(stat.get("caption"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12 text-center">'
            f'<h2 class="text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[17px]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute left-12 right-12 bottom-[80px] grid grid-cols-3 gap-6">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_timeline(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        timeline = slide.get("timeline") or [
            {"label": "01", "title": "定义目标"}, {"label": "02", "title": "生成内容"}, {"label": "03", "title": "导出文件"}
        ]
        nodes = ""
        for ti, item in enumerate(timeline[:5]):
            is_done = ti < 2
            circle_bg = "bg-[var(--ppt-accent)] text-white" if is_done else "bg-[var(--ppt-accent)]/20 text-[var(--ppt-accent-text)]"
            nodes += (
                f'<div class="flex-1 flex flex-col items-center text-center relative z-[1]">'
                f'<span class="w-14 h-14 rounded-full {circle_bg} flex items-center justify-center text-sm font-black">'
                f'{_h(item.get("label") or f"0{ti + 1}")}</span>'
                f'<h3 class="mt-5 text-[17px] font-black text-[var(--ppt-text)]">{_h(item.get("title"))}</h3>'
                f'<p class="mt-2 text-[13px] text-[var(--ppt-muted)]">{_h(item.get("body"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12 text-center">'
            f'<h2 class="text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[150px] flex gap-6 items-start">'
            f'<div class="absolute left-[7%] right-[7%] top-[28px] h-[3px] rounded-full bg-[var(--ppt-accent)]/20"></div>'
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
            f'<div class="absolute left-12 right-12 top-10 flex items-start justify-between">'
            f'<div><div class="rounded-full inline-block bg-[var(--ppt-accent)]/10 px-4 py-1.5 text-[var(--ppt-accent)] text-xs font-black uppercase tracking-[0.15em] mb-3">Data view</div>'
            f'<h2 class="max-w-[550px] text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[16px]">{_h(slide.get("subtitle"))}</p></div>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[160px] grid grid-cols-[1fr_300px] gap-7">'
            f'<div class="h-[300px] rounded-[28px] bg-white/60 backdrop-blur-sm border border-white/80 p-7 flex items-end gap-5 shadow-[0_12px_40px_rgba(0,0,0,0.04)]">{bars}</div>'
            f'<div class="h-[300px] rounded-[28px] bg-[var(--ppt-dark)] p-7 shadow-[0_16px_50px_rgba(0,0,0,0.14)] text-white relative overflow-hidden">'
            f'<div class="absolute -bottom-8 -right-8 w-40 h-40 rounded-full bg-[var(--ppt-accent)]/10 blur-[40px]"></div>'
            f'<span class="relative text-white/45 text-[13px] font-black uppercase tracking-[0.18em]">Insight</span>'
            f'<strong class="relative block mt-7 text-[52px] leading-none font-black">{_h(insight_val)}{_h(chart.get("unit"))}</strong>'
            f'<p class="relative mt-6 text-white/75 text-[17px] leading-[1.32] font-semibold">{_h(slide.get("body") or "关键指标呈现上升趋势。")}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_quote(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center px-20">'
            f'<div class="w-20 h-1 rounded-full bg-[var(--ppt-accent)] mb-10"></div>'
            f'<h2 class="max-w-[700px] text-[40px] leading-[1.18] font-black text-white">{_h(slide.get("quote") or slide["title"])}</h2>'
            f'<p class="mt-8 text-white/35 text-[15px] font-bold uppercase tracking-[0.2em]">{_h(slide.get("author"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_imageText(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        image_tag = f'<img src="{_h(slide.get("imageUrl"))}" alt="" class="w-full h-full object-cover rounded-[20px]" />' if slide.get("imageUrl") else ""
        items_html = "".join(
            f'<div class="flex items-center gap-3 mb-3">'
            f'<span class="w-2 h-2 rounded-full bg-[var(--ppt-accent)] flex-shrink-0"></span>'
            f'<p class="text-[16px] font-semibold text-[var(--ppt-text)]">{_h(item)}</p></div>'
            for item in (slide.get("items") or [])[:3]
        )
        inner = (
            f'<div class="absolute left-12 top-[60px] w-[440px] h-[440px] bg-[var(--ppt-dark)] rounded-[28px] flex items-center justify-center overflow-hidden">{image_tag}</div>'
            f'<div class="absolute right-14 top-[80px] w-[420px]">'
            f'<h2 class="text-[38px] leading-[1.05] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 text-[var(--ppt-muted)] text-[17px] leading-[1.5]">{_h(slide.get("body") or slide.get("subtitle"))}</p>'
            f'<div class="mt-8">{items_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_closing(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<div class="flex gap-2 mb-10">'
            f'<span class="w-3 h-3 rounded-full bg-[var(--ppt-accent)]"></span>'
            f'<span class="w-3 h-3 rounded-full bg-[var(--ppt-accent)]/50"></span>'
            f'<span class="w-3 h-3 rounded-full bg-[var(--ppt-accent)]/30"></span>'
            f'</div>'
            f'<h2 class="max-w-[740px] text-[54px] leading-[1.02] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-6 max-w-[560px] text-white/45 text-[20px] leading-[1.4]">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)
