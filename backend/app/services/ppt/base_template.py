"""Abstract base class for PPT templates with shared rendering helpers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from html import escape
from typing import Any

PPT_PAGE_CLASS = "agenticos-ppt-page"

_h = lambda v: escape(str(v or ""), quote=True)


# ---- shared utility builders ----

def build_chart_bars(
    labels: list[str],
    values: list[float],
    unit: str,
    max_value: float | None = None,
) -> str:
    """Return HTML for vertical bar chart bars. Reusable across templates."""
    if not labels or not values:
        return ""
    if max_value is None:
        max_value = max([float(v) for v in values] + [1])
    bars = ""
    for label, value in zip(labels, values):
        height = max(20, float(value) / max_value * 210)
        bars += (
            f'<div class="flex-1 flex flex-col items-center gap-3">'
            f'<div class="w-full rounded-t-[18px] bg-[var(--ppt-accent)] text-center text-white '
            f'text-[15px] font-black pt-3" style="height:{height:.1f}px">'
            f'<span>{_h(value)}{_h(unit)}</span></div>'
            f'<b class="text-[#64748b] text-xs">{_h(label)}</b>'
            f'</div>'
        )
    return bars


def build_numbered_items(items: list[str], max_items: int = 5) -> str:
    """Items with numbered accent-circle markers. Used by bullets slide."""
    if not items:
        items = ["补充要点"]
    parts = []
    for idx, item in enumerate(items[:max_items]):
        parts.append(
            f'<div class="flex gap-4 items-start rounded-[22px] bg-white p-4 pl-5 '
            f'shadow-[0_18px_40px_rgba(15,23,42,0.08)] text-[#1e293b]">'
            f'<div class="flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-full '
            f'bg-[var(--ppt-accent)] text-white text-[13px] font-black">{idx + 1}</div>'
            f'<p class="text-[20px] leading-[1.28] font-extrabold">{_h(item)}</p>'
            f'</div>'
        )
    return "".join(parts)


def build_accent_dot_items(items: list[str], max_items: int = 5) -> str:
    """Items with small accent dot markers."""
    if not items:
        items = ["补充要点"]
    parts = []
    for item in items[:max_items]:
        parts.append(
            f'<div class="flex gap-4 items-start">'
            f'<div class="w-[10px] h-[10px] mt-2 flex-shrink-0 rounded-full bg-[var(--ppt-accent)]"></div>'
            f'<p class="text-[17px] leading-[1.28] font-extrabold text-[var(--ppt-text)]">{_h(item)}</p>'
            f'</div>'
        )
    return "".join(parts)


def build_simple_items(items: list[str], max_items: int = 5) -> str:
    """Simple text items with no markers."""
    if not items:
        items = ["补充要点"]
    parts = []
    for item in items[:max_items]:
        parts.append(
            f'<p class="text-[17px] leading-[1.28] font-extrabold text-[var(--ppt-text)]">{_h(item)}</p>'
        )
    return "".join(parts)


# ---- base class ----

class BaseTemplate(ABC):
    """Abstract base for PPT slide templates.

    Each concrete template provides:
    - A color profile (CSS custom properties) for light and dark backgrounds
    - A slide frame wrapper (decorative chrome around content)
    - Render methods for all 10 slide types
    """

    name: str
    label: str  # Human-readable label for prompts

    # ---- color profile ----

    @abstractmethod
    def color_profile(self, dark: bool = False) -> str:
        """Return inline CSS custom properties string for the given mode."""
        ...

    # ---- frame ----

    @abstractmethod
    def render_frame(self, inner: str, index: int, total: int, *, dark: bool = False) -> str:
        """Wrap slide inner content with template-specific decorative chrome."""
        ...

    # ---- slide type dispatch ----

    def render_slide(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        """Dispatch to the correct render method by slide type."""
        slide_type = slide.get("type", "bullets")
        method = getattr(self, f"render_{slide_type}", None)
        if method is None:
            method = self.render_bullets
        return method(slide, deck, index)

    # ---- slide type renderers ----

    @abstractmethod
    def render_cover(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_section(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_bullets(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_comparison(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_stats(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_timeline(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_chart(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_quote(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_imageText(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...

    @abstractmethod
    def render_closing(self, slide: dict[str, Any], deck: dict[str, Any], index: int) -> str:
        ...
