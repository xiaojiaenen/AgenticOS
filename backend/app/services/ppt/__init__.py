"""PPT rendering package — template-based slide generation."""
from app.services.ppt.base_template import (
    BaseTemplate,
    PPT_PAGE_CLASS,
    build_chart_bars,
    build_numbered_items,
    build_accent_dot_items,
    build_simple_items,
)
from app.services.ppt.registry import (
    ALLOWED_TYPES,
    get,
    get_or_default,
    list_names,
    register,
)

__all__ = [
    "BaseTemplate",
    "PPT_PAGE_CLASS",
    "ALLOWED_TYPES",
    "register",
    "get",
    "get_or_default",
    "list_names",
    "build_chart_bars",
    "build_numbered_items",
    "build_accent_dot_items",
    "build_simple_items",
]
