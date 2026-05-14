"""Template registry — maps theme names to template class instances."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.ppt.base_template import BaseTemplate

_registry: dict[str, type[BaseTemplate]] = {}
_instances: dict[str, BaseTemplate] = {}

# Backward-compat aliases: old theme name → canonical template name
ALIASES: dict[str, str] = {}

ALLOWED_TYPES = {
    "cover", "section", "bullets", "imageText",
    "comparison", "timeline", "stats", "chart", "quote", "closing",
}


def register(name: str, template_cls: type[BaseTemplate] | None = None, aliases: list[str] | None = None):
    """Register a template class under a canonical name with optional aliases.

    Can be used as a decorator: @register("name") or called directly: register("name", cls).
    """
    if template_cls is not None:
        _registry[name] = template_cls
        for alias in (aliases or []):
            ALIASES[alias] = name
        return template_cls

    def decorator(cls: type[BaseTemplate]) -> type[BaseTemplate]:
        _registry[name] = cls
        for alias in (aliases or []):
            ALIASES[alias] = name
        return cls
    return decorator


def get(name: str) -> BaseTemplate | None:
    """Get a template instance by name or alias. Returns None if not found."""
    canonical = ALIASES.get(name, name)
    if canonical not in _registry:
        return None
    if canonical not in _instances:
        _instances[canonical] = _registry[canonical]()
    return _instances[canonical]


def get_or_default(name: str) -> BaseTemplate:
    """Get a template instance, falling back to 'executive' if unknown."""
    return get(name) or get("executive")  # type: ignore[return-value]


def list_names() -> list[str]:
    """Return all registered canonical template names."""
    return sorted(_registry.keys())
