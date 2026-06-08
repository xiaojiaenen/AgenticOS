from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DesignSystem:
    name: str
    label: str
    category: str
    description: str = ""
    visual_theme: str = ""
    color_palette: dict[str, str] = field(default_factory=dict)
    typography: dict[str, dict[str, str]] = field(default_factory=dict)
    dos_donts: list[str] = field(default_factory=list)
    css_tokens: dict[str, str] = field(default_factory=dict)
    page_layout: str = "light"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "category": self.category,
            "description": self.description,
            "page_layout": self.page_layout,
            "color_palette": self.color_palette,
            "typography": self.typography,
        }

    def to_prompt_excerpt(self) -> str:
        """Build a prompt-ready excerpt with color, typography, and design rules."""
        lines = [f"## 设计系统：{self.label}", f"视觉氛围：{self.visual_theme}", ""]
        if self.color_palette:
            lines.append("### 调色板")
            for role, hex_val in self.color_palette.items():
                lines.append(f"- {role}: {hex_val}")
            lines.append("")
        if self.typography:
            lines.append("### 排版层级")
            for level, rules in self.typography.items():
                parts = ", ".join(f"{k}={v}" for k, v in rules.items())
                lines.append(f"- {level}: {parts}")
            lines.append("")
        if self.dos_donts:
            lines.append("### 设计规则")
            for rule in self.dos_donts:
                lines.append(f"- {rule}")
            lines.append("")
        lines.append("### CSS 令牌\n在 HTML 中使用 var(--xxx) 引用以下令牌，不要替换为具体值：")
        for var_name in sorted(self.css_tokens.keys()):
            if var_name.startswith("--"):
                lines.append(f"- `var({var_name})`")
        return "\n".join(lines)


class DesignSystemLoader:
    """Parse DESIGN.md and tokens.css into structured DesignSystem objects."""

    @staticmethod
    def parse_design_md(text: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "visual_theme": "",
            "color_palette": {},
            "typography": {},
            "dos_donts": [],
        }
        # Extract section 1: Visual Theme & Atmosphere
        m = re.search(r"#+\s*(?:1\.\s*)?Visual Theme.*?\n+(.*?)(?=\n#+\s*(?:2\.|Color)|$)", text, re.S | re.I)
        if m:
            result["visual_theme"] = m.group(1).strip()[:1500]

        # Extract color hex values from section 2 or any Color Palette section
        color_section = ""
        m = re.search(r"#+\s*(?:2\.\s*)?Color Palette.*?\n+(.*?)(?=\n#+\s*(?:3\.|Typography)|$)", text, re.S | re.I)
        if m:
            color_section = m.group(1)
        hex_pattern = re.findall(r'(?:^|\s)(#[0-9a-fA-F]{6})\b.*?(?:[-–]\s*(.+))?', color_section, re.M)
        for hex_val, desc in hex_pattern:
            desc = desc.strip() if desc else hex_val
            result["color_palette"][hex_val] = desc

        # Also capture named color roles
        role_pattern = re.findall(r'\*\*([^*]+)\*\*\s*(?:\(`)?(#[0-9a-fA-F]{6})', color_section)
        for role, hex_val in role_pattern:
            result["color_palette"][hex_val] = role.strip()

        # Extract typography table rows
        typo_section = ""
        m = re.search(r"#+\s*(?:3\.\s*)?Typography.*?\n+(.*?)(?=\n#+\s*(?:4\.|Spacing|Layout|Component)|$)", text, re.S | re.I)
        if m:
            typo_section = m.group(1)
        rows = re.findall(r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', typo_section)
        for row in rows:
            role = row[0].strip()
            if role in ("Role", "---", "**Role**"):
                continue
            result["typography"][role] = {
                "font": row[1].strip() if len(row) > 1 else "",
                "size": row[2].strip() if len(row) > 2 else "",
                "weight": row[3].strip() if len(row) > 3 else "",
            }

        # Extract Do's and Don'ts (section 7 typically)
        dd_section = ""
        m = re.search(r"#+\s*(?:7\.\s*)?Do.s?\s*(?:and|&)\s*Don.ts.*?\n+(.*?)(?=\n#+\s*(?:8\.|Responsive|Agent)|$)", text, re.S | re.I)
        if m:
            dd_section = m.group(1)
        for line in dd_section.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line and len(line) > 5 and not line.startswith("#"):
                result["dos_donts"].append(line)
            if len(result["dos_donts"]) >= 15:
                break

        return result

    @staticmethod
    def parse_tokens_css(text: str) -> dict[str, str]:
        """Parse CSS custom properties from tokens.css."""
        tokens: dict[str, str] = {}
        for match in re.finditer(r'(--[\w-]+)\s*:\s*([^;]+);', text):
            tokens[match.group(1)] = match.group(2).strip()
        return tokens

    @classmethod
    def load(cls, brand_dir: Path) -> DesignSystem | None:
        design_md = brand_dir / "DESIGN.md"
        tokens_css = brand_dir / "tokens.css"
        if not design_md.exists():
            return None
        md_text = design_md.read_text(encoding="utf-8")
        parsed = cls.parse_design_md(md_text)
        css_tokens = {}
        if tokens_css.exists():
            css_tokens = cls.parse_tokens_css(tokens_css.read_text(encoding="utf-8"))
        # Derive category from first heading context or parent metadata
        category = cls._infer_category(brand_dir.name, md_text)
        label = cls._extract_label(md_text) or brand_dir.name.replace("-", " ").title()
        page_layout = "dark" if "dark background" in md_text.lower() or "深色" in md_text else "light"

        return DesignSystem(
            name=brand_dir.name,
            label=label,
            category=category,
            description=parsed["visual_theme"][:200] if parsed["visual_theme"] else "",
            visual_theme=parsed["visual_theme"],
            color_palette=parsed["color_palette"],
            typography=parsed["typography"],
            dos_donts=parsed["dos_donts"],
            css_tokens=css_tokens,
            page_layout=page_layout,
        )

    @staticmethod
    def _infer_category(name: str, md_text: str) -> str:
        first_line = md_text.split("\n")[0] if md_text else ""
        category_keywords = {
            "fintech": ["fintech", "payment", "stripe", "coinbase", "binance", "kraken", "mastercard", "revolut", "wise"],
            "developer": ["developer tools", "cursor", "vercel", "linear", "framer", "expo", "clickhouse",
                          "mongodb", "supabase", "hashicorp", "posthog", "sentry", "warp", "webflow"],
            "productivity": ["productivity", "notion", "figma", "miro", "airtable", "superhuman", "intercom",
                             "zapier", "cal", "clay", "raycast"],
            "ecommerce": ["e-commerce", "shopify", "airbnb", "uber", "nike", "starbucks", "pinterest"],
            "media": ["media", "spotify", "playstation", "wired", "the verge", "meta"],
            "automotive": ["automotive", "tesla", "bmw", "ferrari", "lamborghini", "bugatti", "renault"],
            "ai": ["ai & llm", "claude", "cohere", "mistral", "minimax", "together ai", "replicate",
                   "runwayml", "elevenlabs", "ollama", "x.ai"],
            "enterprise": ["apple", "ibm", "nvidia", "vodafone", "resend", "spacex", "cisco"],
        }
        search_in = (first_line + " " + name).lower()
        for cat, keywords in category_keywords.items():
            for kw in keywords:
                if kw in search_in:
                    return cat
        return "general"

    @staticmethod
    def _extract_label(md_text: str) -> str:
        m = re.search(r"# Design System(?: Inspired by|:)?\s*(.+)", md_text, re.I)
        if m:
            return m.group(1).strip()
        m = re.search(r"> Category:\s*(.+)$", md_text, re.M)
        if not m:
            return ""
        return ""


class DesignSystemRegistry:
    """Registry that scans data/design-systems/ for all available brands."""

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[3] / "data" / "design-systems"
        self.base_dir = Path(base_dir)
        self._systems: dict[str, DesignSystem] = {}
        self._by_category: dict[str, list[str]] = {}

    def scan(self) -> int:
        """Scan the base directory for brand folders. Returns count of loaded systems."""
        self._systems.clear()
        self._by_category.clear()
        if not self.base_dir.exists():
            return 0
        count = 0
        for brand_dir in sorted(self.base_dir.iterdir()):
            if not brand_dir.is_dir() or brand_dir.name.startswith("_") or brand_dir.name.startswith("."):
                continue
            ds = DesignSystemLoader.load(brand_dir)
            if ds is None:
                continue
            self._systems[ds.name] = ds
            self._by_category.setdefault(ds.category, []).append(ds.name)
            count += 1
        return count

    def get(self, name: str) -> DesignSystem | None:
        return self._systems.get(name)

    def get_or_default(self, name: str) -> DesignSystem:
        ds = self._systems.get(name)
        if ds is not None:
            return ds
        # Fallback: return first available, or a minimal default
        if self._systems:
            return next(iter(self._systems.values()))
        return DesignSystem(name="default", label="Default", category="general")

    def search(self, category: str | None = None, query: str | None = None) -> list[DesignSystem]:
        results = list(self._systems.values())
        if category:
            results = [ds for ds in results if ds.category == category]
        if query:
            q = query.lower()
            results = [ds for ds in results if q in ds.name.lower() or q in ds.label.lower()
                       or q in ds.description.lower()]
        return results

    def list_all(self) -> list[DesignSystem]:
        return sorted(self._systems.values(), key=lambda ds: ds.label)

    def list_categories(self) -> list[str]:
        return sorted(self._by_category.keys())

    @property
    def count(self) -> int:
        return len(self._systems)


_registry: DesignSystemRegistry | None = None


def get_design_system_registry() -> DesignSystemRegistry:
    global _registry
    if _registry is None:
        _registry = DesignSystemRegistry()
        _registry.scan()
    return _registry
