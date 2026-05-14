"""Minimal template — pure black/white + red accent, editorial magazine style, pure typography."""
from typing import Any

from app.services.ppt.base_template import PPT_PAGE_CLASS, BaseTemplate, _h
from app.services.ppt.registry import register

COLORS_LIGHT = (
    "--ppt-bg:#ffffff;--ppt-dark:#000000;"
    "--ppt-accent:#e53e3e;--ppt-accent-soft:#fff5f5;"
    "--ppt-accent-text:#e53e3e;"
    "--ppt-text:#000000;--ppt-muted:#888888;"
)
COLORS_DARK = (
    "--ppt-bg:#000000;--ppt-dark:#000000;"
    "--ppt-accent:#e53e3e;--ppt-accent-soft:rgba(229,62,62,0.12);"
    "--ppt-accent-text:#e53e3e;"
    "--ppt-text:#ffffff;--ppt-muted:rgba(255,255,255,0.50);"
)


def _minimal_frame(inner: str, index: int, total: int, *, dark: bool = False) -> str:
    colors = COLORS_DARK if dark else COLORS_LIGHT
    border = "border-black/[0.08]" if not dark else "border-white/[0.08]"
    page_color = "text-black/25" if not dark else "text-white/25"
    return (
        f'<div class="ppt-preview-card w-[720px] h-[405px] mb-8 origin-top-left">'
        f'<section class="{PPT_PAGE_CLASS} relative w-[1000px] h-[562.5px] overflow-hidden '
        f'border {border} bg-[var(--ppt-bg)] text-[var(--ppt-text)]" '
        f'style="{colors}">'
        f'{inner}'
        f'<div class="absolute left-10 bottom-8 text-xs font-medium tracking-[0.2em] {page_color}">'
        f'{index + 1:02d}<span class="opacity-30"> / {total:02d}</span></div>'
        f'</section></div>'
    )


@register("minimal")
class MinimalTemplate(BaseTemplate):
    name = "minimal"
    label = "极简杂志风 · 黑白+红"

    def color_profile(self, dark: bool = False) -> str:
        return COLORS_DARK if dark else COLORS_LIGHT

    def render_frame(self, inner: str, index: int, total: int, *, dark: bool = False) -> str:
        return _minimal_frame(inner, index, total, dark=dark)

    # ---- cover: right-aligned, massive type ----
    def render_cover(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute right-16 top-[130px] text-right w-[700px]">'
            f'<div class="flex items-center justify-end gap-3 mb-8">'
            f'<span class="text-[var(--ppt-muted)] text-[13px] font-bold uppercase tracking-[0.3em]">{_h(slide.get("eyebrow") or deck.get("author") or "AgenticOS")}</span>'
            f'<span class="block w-3 h-3 bg-[var(--ppt-accent)]"></span>'
            f'</div>'
            f'<h1 class="text-[72px] leading-[0.92] font-black text-white">{_h(slide["title"])}</h1>'
            f'<div class="mt-8 w-full h-[1px] bg-white/15"></div>'
            f'<p class="mt-8 text-white/45 text-[22px] leading-[1.4] font-light">{_h(slide.get("subtitle") or deck.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute left-0 top-0 text-[220px] font-black text-white/[0.03] leading-none select-none">{index + 1:02d}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    # ---- section: large number + title ----
    def render_section(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex items-center justify-center">'
            f'<div class="text-center">'
            f'<span class="text-[200px] font-black text-white/[0.04] leading-none select-none block">{index + 1:02d}</span>'
            f'<div class="-mt-16">'
            f'<span class="text-[var(--ppt-accent)] text-[13px] font-bold uppercase tracking-[0.3em]">{_h(slide.get("eyebrow") or "Section")}</span>'
            f'<h2 class="mt-6 text-[56px] leading-[1.02] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-5 text-white/40 text-[20px] leading-[1.4] font-light">{_h(slide.get("subtitle"))}</p>'
            f'</div></div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    # ---- bullets: red numbers, thin rules, no cards ----
    def render_bullets(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        body = slide.get("body")
        items = slide.get("items") or ([body] if body else ["补充要点"])
        items_html = ""
        for idx, item in enumerate(items[:5]):
            items_html += (
                f'<div class="flex gap-6 items-start py-5 border-t border-black/8">'
                f'<span class="text-[var(--ppt-accent)] text-[28px] font-black leading-none w-10 flex-shrink-0">{idx + 1:02d}</span>'
                f'<p class="text-[20px] leading-[1.35] font-bold text-[var(--ppt-text)]">{_h(item)}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-16 top-12 right-16">'
            f'<h2 class="text-[46px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[16px] leading-[1.5] font-light">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute left-16 right-16 top-[170px]">{items_html}'
            f'<div class="border-t border-black/8"></div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- comparison: two text columns with center red rule ----
    def render_comparison(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        left_html = "".join(
            f'<p class="text-[18px] leading-[1.4] font-medium text-[var(--ppt-text)] py-2 border-b border-black/6">{_h(item)}</p>'
            for item in (slide.get("leftItems") or ["补充项"])[:4]
        )
        right_html = "".join(
            f'<p class="text-[18px] leading-[1.4] font-bold text-white py-2 border-b border-white/10">{_h(item)}</p>'
            for item in (slide.get("rightItems") or ["补充项"])[:4]
        )
        inner = (
            f'<div class="absolute left-16 top-10 right-16">'
            f'<h2 class="text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-16 right-16 top-[130px] grid grid-cols-2 gap-0">'
            f'<div class="pr-12"><h3 class="mb-6 text-[var(--ppt-muted)] text-[14px] font-bold uppercase tracking-[0.2em]">{_h(slide.get("leftTitle") or "Before")}</h3>{left_html}</div>'
            f'<div class="pl-12 border-l-2 border-[var(--ppt-accent)] bg-[var(--ppt-dark)] p-8 -m-8">'
            f'<h3 class="mb-6 text-[var(--ppt-accent)] text-[14px] font-bold uppercase tracking-[0.2em]">{_h(slide.get("rightTitle") or "After")}</h3>{right_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- stats: large numbers, asymmetric ----
    def render_stats(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        stats = slide.get("stats") or [
            {"value": "3.2x", "label": "效率提升"}, {"value": "-41%", "label": "成本降低"}, {"value": "92%", "label": "满意度"}
        ]
        cards = ""
        for si, stat in enumerate(stats[:3]):
            accent_bar = f'<div class="w-8 h-[3px] bg-[var(--ppt-accent)] mb-4"></div>' if si == 0 else ""
            cards += (
                f'<div class="{"col-span-1" if si > 0 else ""}">'
                f'{accent_bar}'
                f'<strong class="block text-[64px] leading-none font-black text-[var(--ppt-text)]">{_h(stat.get("value"))}</strong>'
                f'<p class="mt-2 text-[18px] font-bold text-[var(--ppt-text)]">{_h(stat.get("label"))}</p>'
                f'<p class="mt-1 text-[13px] text-[var(--ppt-muted)] font-light">{_h(stat.get("caption"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-16 top-16 right-16">'
            f'<h2 class="text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-16 right-16 bottom-[100px] grid grid-cols-[2fr_1fr_1fr] gap-10">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- timeline: vertical minimalist ----
    def render_timeline(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        timeline = slide.get("timeline") or [
            {"label": "01", "title": "定义目标"}, {"label": "02", "title": "生成内容"}, {"label": "03", "title": "导出文件"}
        ]
        nodes = ""
        for item in timeline[:5]:
            nodes += (
                f'<div class="flex gap-6 items-start">'
                f'<div class="flex flex-col items-center flex-shrink-0">'
                f'<span class="w-3 h-3 bg-[var(--ppt-accent)]"></span>'
                f'<div class="w-[1px] h-12 bg-black/10"></div></div>'
                f'<div class="pb-10"><p class="text-[12px] font-mono text-[var(--ppt-accent)] tracking-[0.2em] uppercase">{_h(item.get("label"))}</p>'
                f'<h3 class="mt-1 text-[20px] font-black text-[var(--ppt-text)]">{_h(item.get("title"))}</h3>'
                f'<p class="mt-1 text-[14px] text-[var(--ppt-muted)] font-light">{_h(item.get("body"))}</p></div>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-16 top-12 right-16">'
            f'<h2 class="text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-16 right-16 top-[160px]">{nodes}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- chart: minimal bars + insight ----
    def render_chart(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        chart = slide.get("chart") or {
            "type": "bar", "labels": ["入口", "转化", "留存", "复购"],
            "values": [32, 58, 74, 86], "unit": "%",
        }
        labels = chart.get("labels") or []
        values = chart.get("values") or []
        max_value = max([float(v) for v in values] + [1])
        bars = ""
        for label, value in zip(labels, values):
            h = max(20, float(value) / max_value * 200)
            bars += (
                f'<div class="flex-1 flex flex-col items-center gap-3">'
                f'<span class="text-[13px] font-mono text-[var(--ppt-muted)]">{_h(value)}{_h(chart.get("unit"))}</span>'
                f'<div class="w-full bg-[var(--ppt-accent)]" style="height:{h:.0f}px"></div>'
                f'<span class="text-[11px] font-mono text-[var(--ppt-muted)] uppercase">{_h(label)}</span>'
                f'</div>'
            )
        insight_val = max(values) if values else 0
        inner = (
            f'<div class="absolute left-16 top-10 right-16 flex items-start justify-between">'
            f'<div><h2 class="max-w-[500px] text-[42px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 text-[var(--ppt-muted)] text-[16px] font-light">{_h(slide.get("subtitle"))}</p></div>'
            f'<span class="text-[11px] font-mono text-[var(--ppt-accent)] uppercase tracking-[0.2em]">{_h(chart.get("type", "bar"))}</span>'
            f'</div>'
            f'<div class="absolute left-16 right-16 top-[170px] grid grid-cols-[1fr_280px] gap-10">'
            f'<div class="h-[280px] flex items-end gap-6 border-b-2 border-black/8 pb-6">{bars}</div>'
            f'<div class="h-[280px] bg-[var(--ppt-dark)] p-8 text-white">'
            f'<p class="text-[11px] font-mono text-white/40 uppercase tracking-[0.2em]">Insight</p>'
            f'<strong class="block mt-6 text-[64px] leading-none font-black">{_h(insight_val)}{_h(chart.get("unit"))}</strong>'
            f'<p class="mt-6 text-white/70 text-[16px] leading-[1.4] font-light">{_h(slide.get("body") or "关键指标呈上升趋势。")}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- quote: massive, centered ----
    def render_quote(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center px-20">'
            f'<span class="text-[var(--ppt-accent)] text-[120px] font-black leading-none">&ldquo;</span>'
            f'<h2 class="-mt-8 max-w-[700px] text-[38px] leading-[1.2] font-black text-white">{_h(slide.get("quote") or slide["title"])}</h2>'
            f'<div class="mt-10 w-12 h-[2px] bg-[var(--ppt-accent)]"></div>'
            f'<p class="mt-6 text-white/35 text-[15px] font-bold uppercase tracking-[0.25em]">{_h(slide.get("author"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    # ---- imageText: large image + minimal text ----
    def render_imageText(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        image_tag = f'<img src="{_h(slide.get("imageUrl"))}" alt="" class="w-full h-full object-cover" />' if slide.get("imageUrl") else ""
        items_html = "".join(
            f'<p class="text-[16px] leading-[1.5] font-medium text-[var(--ppt-text)] py-2 border-b border-black/6">{_h(item)}</p>'
            for item in (slide.get("items") or [])[:3]
        )
        inner = (
            f'<div class="absolute left-16 top-[60px] w-[420px] h-[440px] bg-[var(--ppt-dark)] flex items-center justify-center">{image_tag}</div>'
            f'<div class="absolute right-16 top-[80px] w-[420px]">'
            f'<h2 class="text-[40px] leading-[1.05] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 text-[var(--ppt-muted)] text-[18px] leading-[1.5] font-light">{_h(slide.get("body") or slide.get("subtitle"))}</p>'
            f'<div class="mt-8">{items_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    # ---- closing: centered, clean ----
    def render_closing(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<div class="w-3 h-3 bg-[var(--ppt-accent)]"></div>'
            f'<h2 class="mt-8 max-w-[700px] text-[56px] leading-[1.02] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-6 max-w-[560px] text-white/40 text-[20px] leading-[1.4] font-light">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)
