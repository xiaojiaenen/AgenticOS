"""Deck style presets for PPT generation.

Each style is a curated combination of design principles, recommended themes,
and forbidden patterns — distilled from open-design's craft rules and deck skills.
"""

DECK_STYLES: dict[str, dict] = {
    "editorial": {
        "label": "编辑墨水风格",
        "description": "衬线展示字体 + 极简装饰 + 无渐变无阴影 + 文字驱动叙事",
        "font_display": "Playfair Display, Noto Serif SC, serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "single accent, no gradients, at most 1 per slide",
        "radius": "4-8px subtle",
        "shadow": "none",
        "forbidden": ["gradients", "drop-shadow filters", "emoji decor", "accent left bar", "heavy rounded pills"],
        "recommended_themes": ["kami", "paper", "editorial", "publication", "warm-editorial", "atelier-zero", "editorial-serif"],
        "best_for": ["投资报告", "战略提案", "学术演讲", "出版级内容"],
    },
    "modern_minimal": {
        "label": "现代极简",
        "description": "克制的 accent + 大量留白 + 字体层级驱动 + 精确间距",
        "font_display": "Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "1-2 per slide, no gradients",
        "radius": "8-12px",
        "shadow": "minimal or none",
        "forbidden": ["decorative blobs", "heavy borders", "loud gradients"],
        "recommended_themes": ["apple", "minimal", "clean", "mono", "refined", "sleek", "swiss-grid", "simple"],
        "best_for": ["产品发布", "SaaS 汇报", "技术分享", "初创路演"],
    },
    "bold_statement": {
        "label": "大胆宣言",
        "description": "大字号标题 + 高对比 accent + 几何装饰 + 非对称布局",
        "font_display": "Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "bold, up to 3 per slide",
        "radius": "0-4px sharp or 16px bold rounded",
        "shadow": "strong but sparing",
        "forbidden": ["subtle color palettes", "small text sizes", "symmetric grid layouts"],
        "recommended_themes": ["neo-brutalism", "brutalism", "bold", "nike", "spotify", "playstation", "magazine-bold", "dracula"],
        "best_for": ["品牌发布会", "创意提案", "设计评审", "市场营销"],
    },
    "tech_dark": {
        "label": "科技暗色",
        "description": "暗色背景 + 高饱和 accent + 终端/代码元素 + 荧光感",
        "font_display": "JetBrains Mono, monospace",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "bright accent on dark, glowing feel",
        "radius": "4-8px",
        "shadow": "none or glow",
        "forbidden": ["warm color palettes", "serif fonts", "paper-like textures"],
        "recommended_themes": ["github", "dracula", "tokyo-night", "monokai", "terminal-green", "cyberpunk-neon", "nord", "mission-control", "hud"],
        "best_for": ["开发者大会", "安全报告", "技术架构", "黑客松"],
    },
    "warm_human": {
        "label": "温暖人文",
        "description": "暖色调 + 柔和圆角 + 有机曲线 + 亲和力",
        "font_display": "Playfair Display, Noto Serif SC, serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "soft, warm accent, 1-2 per slide",
        "radius": "12-20px soft",
        "shadow": "soft and gentle",
        "forbidden": ["harsh pure-black text", "sharp corners", "cold blue-grey palettes"],
        "recommended_themes": ["airbnb", "pinterest", "xiaohongshu", "sunset-warm", "soft-pastel", "rose-pine", "warm-editorial", "cafe"],
        "best_for": ["品牌故事", "用户研究", "团队文化", "社交媒体"],
    },
    "data_driven": {
        "label": "数据驱动",
        "description": "数据可视化优先 + 网格对齐 + 信息密度高 + 图表为主",
        "font_display": "Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "function over form, accent highlights key data",
        "radius": "4-8px",
        "shadow": "none",
        "forbidden": ["excessive decoration", "low data-ink ratio elements", "distracting gradients"],
        "recommended_themes": ["stripe", "corporate", "enterprise", "ibm", "professional", "linear-app", "engineering-whiteprint"],
        "best_for": ["季度财报", "数据分析", "运营汇报", "KPI 仪表盘"],
    },
    "creative_experimental": {
        "label": "创意实验",
        "description": "非传统布局 + 大胆配色 + 意外排版 + 视觉冲击",
        "font_display": "Playfair Display, Noto Serif SC, serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "bold multi-accent or monochrome",
        "radius": "varied",
        "shadow": "creative",
        "forbidden": ["standard grid layouts", "boring centering", "safe corporates"],
        "recommended_themes": ["glassmorphism", "vaporwave", "memphis-pop", "bauhaus", "y2k-chrome", "retro-tv", "futuristic", "cosmic", "creative"],
        "best_for": ["设计作品集", "艺术展览", "潮流发布", "年终总结"],
    },
}


def build_deck_styles_text() -> str:
    """Build a compact deck style reference for injection into the design catalog."""
    lines = [
        "## Deck 风格预设（可选，快速匹配设计语言）",
        "",
        "当用户有明确的风格偏好时，从下表选择最匹配的风格并应用其原则。未指定时自动推断。",
        "",
        "| 风格 | 关键词 | 展示字体 | 推荐主题 |",
        "|------|--------|---------|---------|",
    ]
    for key, style in DECK_STYLES.items():
        themes = ", ".join(style["recommended_themes"][:4])
        keywords = " / ".join(style["best_for"][:2])
        lines.append(
            f"| {style['label']} | {keywords} | {style['font_display'].split(',')[0]} | {themes} |"
        )
    lines.append("")
    lines.append("**使用方法**：根据用户需求匹配一个风格，遵循其 accent_usage、radius、forbidden 约束。推荐主题仅供参考——可从 161 个完整列表中另选。")
    return "\n".join(lines)
