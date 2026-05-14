"""Creative template — bold color blocks, irregular shapes, overlapped elements, high saturation."""
from typing import Any

from app.services.ppt.base_template import PPT_PAGE_CLASS, BaseTemplate, _h, build_chart_bars
from app.services.ppt.registry import register

PALETTE = ["#7c3aed", "#ec4899", "#06b6d4", "#f59e0b"]

COLORS_LIGHT = (
    "--ppt-bg:#fffbeb;--ppt-dark:#0f0a1a;"
    "--ppt-accent:#7c3aed;--ppt-accent-soft:rgba(124,58,237,0.08);"
    "--ppt-accent-text:#6d28d9;"
    "--ppt-text:#1e0a3c;--ppt-muted:#78716c;"
)
COLORS_DARK = (
    "--ppt-bg:#0f0a1a;--ppt-dark:#0a0512;"
    "--ppt-accent:#a855f7;--ppt-accent-soft:rgba(168,85,247,0.12);"
    "--ppt-accent-text:#c084fc;"
    "--ppt-text:#fff;--ppt-muted:rgba(255,255,255,0.50);"
)


def _creative_frame(inner: str, index: int, total: int, *, dark: bool = False) -> str:
    colors = COLORS_DARK if dark else COLORS_LIGHT
    page_badge = (
        f'<div class="absolute right-8 bottom-8 rounded-[4px] bg-[var(--ppt-accent)] '
        f'px-4 py-1.5 text-xs font-black text-white tracking-[0.12em] rotate-3">{index + 1:02d} / {total:02d}</div>'
    ) if dark else (
        f'<div class="absolute right-8 bottom-8 rounded-[4px] bg-[var(--ppt-text)] '
        f'px-4 py-1.5 text-xs font-black text-white tracking-[0.12em] -rotate-2">{index + 1:02d} / {total:02d}</div>'
    )
    return (
        f'<div class="ppt-preview-card w-[720px] h-[405px] mb-8 origin-top-left">'
        f'<section class="{PPT_PAGE_CLASS} relative w-[1000px] h-[562.5px] overflow-hidden '
        f'rounded-[2px] bg-[var(--ppt-bg)] text-[var(--ppt-text)]" '
        f'style="{colors}">'
        f'{inner}'
        f'{page_badge}'
        f'</section></div>'
    )


def _color_for(idx: int) -> str:
    return PALETTE[idx % len(PALETTE)]


@register("creative")
class CreativeTemplate(BaseTemplate):
    name = "creative"
    label = "多彩色块 · 创意提案风"

    def color_profile(self, dark: bool = False) -> str:
        return COLORS_DARK if dark else COLORS_LIGHT

    def render_frame(self, inner: str, index: int, total: int, *, dark: bool = False) -> str:
        return _creative_frame(inner, index, total, dark=dark)

    def render_cover(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0">'
            f'<div class="absolute top-0 right-0 w-[55%] h-full bg-[#ec4899] rotate-6 translate-x-20 -translate-y-10 opacity-80"></div>'
            f'<div class="absolute bottom-0 left-0 w-[45%] h-[60%] bg-[#06b6d4] -rotate-3 -translate-x-10 translate-y-10 opacity-80"></div>'
            f'<div class="absolute left-14 top-[130px] w-[620px] z-10">'
            f'<span class="inline-block bg-[#7c3aed] text-white px-5 py-2 rounded-[4px] text-xs font-black uppercase tracking-[0.2em] -rotate-2">{_h(slide.get("eyebrow") or deck.get("author") or "AgenticOS")}</span>'
            f'<h1 class="mt-8 text-[64px] leading-[0.92] font-black text-white">{_h(slide["title"])}</h1>'
            f'<p class="mt-6 max-w-[480px] text-white/70 text-[20px] leading-[1.4] font-bold">{_h(slide.get("subtitle") or deck.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute right-20 bottom-20 w-24 h-24 bg-[#f59e0b] rotate-12 z-10"></div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_section(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        c = _color_for(index)
        inner = (
            f'<div class="absolute inset-0 flex">'
            f'<div class="w-[45%] h-full flex items-center justify-center" style="background:{c}">'
            f'<span class="text-white/30 text-[160px] font-black leading-none -rotate-6 select-none">{index + 1:02d}</span>'
            f'</div>'
            f'<div class="flex-1 flex flex-col justify-center px-14">'
            f'<span class="text-[var(--ppt-accent)] text-[14px] font-black uppercase tracking-[0.25em]">{_h(slide.get("eyebrow") or "Section")}</span>'
            f'<h2 class="mt-6 text-[52px] leading-[1.02] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 text-white/40 text-[18px] leading-[1.4]">{_h(slide.get("subtitle"))}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_bullets(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        body = slide.get("body")
        items = slide.get("items") or ([body] if body else ["补充要点"])
        cards = ""
        for idx, item in enumerate(items[:4]):
            c = _color_for(idx)
            rot = [-2, 1, -1, 0.5][idx] if idx < 4 else 0
            cards += (
                f'<div class="rounded-[12px] p-6 shadow-[8px_8px_0_rgba(0,0,0,0.08)]" '
                f'style="background:{c};transform:rotate({rot}deg)">'
                f'<span class="text-white/80 text-[13px] font-black">0{idx + 1}</span>'
                f'<p class="mt-2 text-[19px] leading-[1.25] font-black text-white">{_h(item)}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<h2 class="max-w-[600px] text-[44px] leading-[1.02] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-3 max-w-[500px] text-[var(--ppt-muted)] text-[16px] font-bold">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[160px] grid grid-cols-2 gap-5">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_comparison(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        left_html = "".join(
            f'<p class="text-[16px] leading-[1.4] font-bold py-2">{_h(item)}</p>'
            for item in (slide.get("leftItems") or ["补充项"])[:4]
        )
        right_html = "".join(
            f'<p class="text-[16px] leading-[1.4] font-black text-white py-2">{_h(item)}</p>'
            for item in (slide.get("rightItems") or ["补充项"])[:4]
        )
        inner = (
            f'<div class="absolute left-10 top-10 right-10">'
            f'<h2 class="text-[38px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-10 right-10 top-[120px] grid grid-cols-2 gap-6">'
            f'<div class="rounded-[16px] bg-white p-7 shadow-[6px_6px_0_rgba(0,0,0,0.06)] border-2 border-black/5 -rotate-1">'
            f'<h3 class="mb-5 text-[var(--ppt-muted)] text-[13px] font-black uppercase tracking-[0.15em]">{_h(slide.get("leftTitle") or "Before")}</h3>{left_html}</div>'
            f'<div class="rounded-[16px] bg-[var(--ppt-dark)] p-7 shadow-[6px_6px_0_rgba(124,58,237,0.3)] rotate-1 text-white">'
            f'<h3 class="mb-5 text-[var(--ppt-accent)] text-[13px] font-black uppercase tracking-[0.15em]">{_h(slide.get("rightTitle") or "After")}</h3>{right_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_stats(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        stats = slide.get("stats") or [
            {"value": "3.2x", "label": "效率提升"}, {"value": "-41%", "label": "成本降低"}, {"value": "92%", "label": "满意度"}
        ]
        cards = ""
        for si, stat in enumerate(stats[:3]):
            c = _color_for(si)
            rot = [-3, 2, -1][si]
            cards += (
                f'<div class="rounded-[16px] p-7 text-white shadow-[6px_6px_0_rgba(0,0,0,0.1)]" '
                f'style="background:{c};transform:rotate({rot}deg)">'
                f'<strong class="block text-[58px] leading-none font-black">{_h(stat.get("value"))}</strong>'
                f'<h3 class="mt-5 text-[17px] font-black">{_h(stat.get("label"))}</h3>'
                f'<p class="mt-1 text-white/60 text-[12px]">{_h(stat.get("caption"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<h2 class="text-[42px] leading-[1.02] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-12 right-12 bottom-[90px] grid grid-cols-3 gap-6">{cards}</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_timeline(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        timeline = slide.get("timeline") or [
            {"label": "01", "title": "定义目标"}, {"label": "02", "title": "生成内容"}, {"label": "03", "title": "导出文件"}
        ]
        nodes = ""
        for ti, item in enumerate(timeline[:5]):
            c = _color_for(ti)
            nodes += (
                f'<div class="relative z-[1] flex-1 flex flex-col">'
                f'<span class="w-14 h-14 rounded-[8px] flex items-center justify-center text-white text-sm font-black" style="background:{c};transform:rotate(3deg)">{_h(item.get("label") or f"0{ti + 1}")}</span>'
                f'<h3 class="mt-5 text-[18px] font-black text-[var(--ppt-text)]">{_h(item.get("title"))}</h3>'
                f'<p class="mt-2 text-[13px] text-[var(--ppt-muted)] font-medium">{_h(item.get("body"))}</p>'
                f'</div>'
            )
        inner = (
            f'<div class="absolute left-12 top-12 right-12">'
            f'<h2 class="text-[42px] leading-[1.02] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[160px] flex gap-5">'
            f'<div class="absolute left-[7%] right-[7%] top-[28px] h-[6px] rounded-full bg-[var(--ppt-accent)]/15 -rotate-1"></div>'
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
        bars = ""
        for idx, (label, value) in enumerate(zip(labels, values)):
            c = _color_for(idx)
            h = max(20, float(value) / max_value * 200)
            bars += (
                f'<div class="flex-1 flex flex-col items-center gap-3">'
                f'<div class="w-full text-center text-white text-[14px] font-black pt-3" style="background:{c};height:{h:.0f}px;border-radius:8px 8px 0 0">'
                f'{_h(value)}{_h(chart.get("unit"))}</div>'
                f'<b class="text-[var(--ppt-muted)] text-[11px] font-bold">{_h(label)}</b>'
                f'</div>'
            )
        insight_val = max(values) if values else 0
        inner = (
            f'<div class="absolute left-12 right-12 top-10 flex items-start justify-between">'
            f'<div><h2 class="max-w-[550px] text-[38px] leading-[1.04] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-2 text-[var(--ppt-muted)] text-[15px] font-bold">{_h(slide.get("subtitle"))}</p></div>'
            f'</div>'
            f'<div class="absolute left-12 right-12 top-[150px] grid grid-cols-[1fr_280px] gap-6">'
            f'<div class="h-[300px] rounded-[16px] bg-white p-7 flex items-end gap-5 shadow-[6px_6px_0_rgba(0,0,0,0.06)] border-2 border-black/5">{bars}</div>'
            f'<div class="h-[300px] rounded-[16px] bg-[var(--ppt-dark)] p-7 shadow-[6px_6px_0_rgba(124,58,237,0.3)] text-white">'
            f'<span class="text-[var(--ppt-accent)] text-[12px] font-black uppercase tracking-[0.15em]">Insight</span>'
            f'<strong class="block mt-6 text-[56px] leading-none font-black">{_h(insight_val)}{_h(chart.get("unit"))}</strong>'
            f'<p class="mt-5 text-white/70 text-[16px] leading-[1.3] font-bold">{_h(slide.get("body") or "关键指标呈现上升趋势。")}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_quote(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        c = _color_for(index)
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center px-20">'
            f'<div class="w-24 h-3 mb-12" style="background:{c};transform:rotate(-2deg)"></div>'
            f'<h2 class="max-w-[680px] text-[42px] leading-[1.16] font-black text-white">{_h(slide.get("quote") or slide["title"])}</h2>'
            f'<div class="mt-10 flex items-center gap-3 -rotate-1">'
            f'<span class="w-8 h-[4px] block" style="background:{c}"></span>'
            f'<p class="text-white/35 text-[15px] font-black uppercase tracking-[0.2em]">{_h(slide.get("author"))}</p>'
            f'</div></div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)

    def render_imageText(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        c1, c2 = _color_for(0), _color_for(1)
        image_tag = f'<img src="{_h(slide.get("imageUrl"))}" alt="" class="w-full h-full object-cover" />' if slide.get("imageUrl") else ""
        items_html = "".join(
            f'<p class="text-[15px] leading-[1.4] font-bold text-[var(--ppt-text)] py-2">{_h(item)}</p>'
            for item in (slide.get("items") or [])[:3]
        )
        inner = (
            f'<div class="absolute left-0 top-0 w-[420px] h-full bg-[var(--ppt-dark)]"></div>'
            f'<div class="absolute left-[160px] top-[60px] w-[380px] h-[440px] overflow-hidden rounded-[8px] '
            f'shadow-[10px_10px_0_rgba(0,0,0,0.12)]" style="background:{c1}">{image_tag}</div>'
            f'<div class="absolute right-12 top-[70px] w-[400px]">'
            f'<span class="inline-block w-16 h-[3px] rounded-full" style="background:{c2}"></span>'
            f'<h2 class="mt-6 text-[38px] leading-[1.05] font-black text-[var(--ppt-text)]">{_h(slide["title"])}</h2>'
            f'<p class="mt-4 text-[var(--ppt-muted)] text-[17px] leading-[1.5] font-medium">{_h(slide.get("body") or slide.get("subtitle"))}</p>'
            f'<div class="mt-6">{items_html}</div>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=False)

    def render_closing(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        inner = (
            f'<div class="absolute inset-0 flex flex-col items-center justify-center text-center">'
            f'<div class="flex gap-3 mb-8">'
            f'<span class="w-5 h-5 rotate-45" style="background:{_color_for(0)}"></span>'
            f'<span class="w-5 h-5 rotate-45" style="background:{_color_for(1)}"></span>'
            f'<span class="w-5 h-5 rotate-45" style="background:{_color_for(2)}"></span>'
            f'</div>'
            f'<h2 class="max-w-[740px] text-[56px] leading-[1.02] font-black text-white">{_h(slide["title"])}</h2>'
            f'<p class="mt-6 max-w-[560px] text-white/40 text-[20px] leading-[1.4] font-bold">{_h(slide.get("subtitle"))}</p>'
            f'</div>'
        )
        return self.render_frame(inner, index, len(deck["slides"]), dark=True)
