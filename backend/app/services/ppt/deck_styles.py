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
        "recommended_themes": ["github", "apple", "minimal", "clean", "mono", "refined", "sleek", "swiss-grid", "simple"],
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
        "recommended_themes": ["dracula", "tokyo-night", "monokai", "terminal-green", "cyberpunk-neon", "nord", "mission-control", "hud"],
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
    "swiss_international": {
        "label": "瑞士国际主义",
        "description": "16列网格 + 直角 + 单一饱和accent + 1px hairline + 无渐变无阴影 + 极端字号反差",
        "font_display": "Inter Tight, Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "font_mono": "JetBrains Mono, monospace",
        "accent_usage": "single saturated accent, max 2 uses per slide",
        "radius": "0px — strictly no rounded corners",
        "shadow": "none — strictly forbidden",
        "forbidden": ["rounded corners (border-radius > 0)", "gradients", "drop shadows", "blur", "serif fonts", "decorative emoji", "more than 2 accent uses per slide"],
        "recommended_themes": ["klein-blue", "swiss-grid", "minimal", "mono", "bauhaus", "brutalist"],
        "best_for": ["商业报告", "AI/设计提案", "事实演讲", "工业分析"],
    },
    "glass_layers": {
        "label": "玻璃层次",
        "description": "毛玻璃面板 + 多层透明叠加 + 精致阴影 + 现代 SaaS 质感",
        "font_display": "Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "subtle, 1 per slide on frosted panels",
        "radius": "16-24px prominent",
        "shadow": "layered, depth-creating",
        "forbidden": ["solid opaque backgrounds", "flat design", "harsh borders", "dark mode"],
        "recommended_themes": ["glassmorphism", "vercel", "apple", "linear-app", "notion", "raycast"],
        "best_for": ["SaaS 产品发布", "UI/UX 评审", "技术博客", "现代企业介绍"],
    },
    "zen_garden": {
        "label": "禅意留白",
        "description": "极致留白 + 单一自然 accent + 有机曲线 + 无边框无阴影 + 呼吸感",
        "font_display": "Noto Serif SC, serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "one natural accent only, used once per slide max",
        "radius": "none",
        "shadow": "none",
        "forbidden": ["borders", "shadows", "gradients", "more than 1 accent element", "dense layouts", "emoji", "grid lines"],
        "recommended_themes": ["japanese-minimal", "paper", "kami", "warm-editorial", "atelier-zero", "refined"],
        "best_for": ["哲学演讲", "品牌理念", "高端咨询", "文化艺术"],
    },
    "luxe_noir": {
        "label": "奢华暗金",
        "description": "深色背景 + 金色/玫瑰金 accent + 衬线标题 + 精致装饰线 + 奢侈感",
        "font_display": "Playfair Display, Noto Serif SC, serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "gold/rose-gold accent, 1-2 per slide, never bright yellow",
        "radius": "2-4px subtle",
        "shadow": "none",
        "forbidden": ["bright primary colors", "casual fonts", "emoji", "neon", "glass effects"],
        "recommended_themes": ["premium", "luxury", "mastercard", "bugatti", "ferrari", "lamborghini"],
        "best_for": ["高端品牌发布", "奢侈品报告", "VIP 演讲", "年度盛典"],
    },
    "pastel_dream": {
        "label": "柔和粉彩",
        "description": "粉彩色板 + 大圆角 + 柔和阴影 + 友好亲和 + 轻盈愉悦",
        "font_display": "Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "soft pastel accent, 2-3 per slide, no harsh contrasts",
        "radius": "16-24px bold rounded",
        "shadow": "soft, gentle, colorful",
        "forbidden": ["pure black text", "sharp corners", "dark backgrounds", "harsh red/green", "serif fonts"],
        "recommended_themes": ["soft-pastel", "xiaohongshu", "pinterest", "duolingo", "friendly", "catppuccin-latte"],
        "best_for": ["团队建设", "用户研究", "教育课件", "社交分享"],
    },
    "magazine_layout": {
        "label": "杂志跨页",
        "description": "大图出血 + 超大标题 + 引用块 + 非对称四栏 + 编辑感",
        "font_display": "Playfair Display, Noto Serif SC, serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "accent_usage": "minimal accent, let typography and images dominate",
        "radius": "0px",
        "shadow": "none",
        "forbidden": ["rounded corners", "gradients", "drop shadows", "emoji", "small title text"],
        "recommended_themes": ["editorial", "publication", "magazine-bold", "theverge", "warm-editorial", "editorial-serif"],
        "best_for": ["品牌故事", "年度回顾", "深度报道", "作品集"],
    },
    "neon_pulse": {
        "label": "霓虹脉冲",
        "description": "深黑背景 + 霓虹强调色 + 发光边框 + 终端字体 + 夜店/赛博精致感",
        "font_display": "Inter, Noto Sans SC, sans-serif",
        "font_body": "Inter, Noto Sans SC, sans-serif",
        "font_mono": "JetBrains Mono, monospace",
        "accent_usage": "1-2 neon accents with glow, no more per slide",
        "radius": "4-8px",
        "shadow": "glow only, no drop shadow",
        "forbidden": ["warm colors", "serif fonts", "white backgrounds", "subtle palettes", "organic shapes"],
        "recommended_themes": ["cyberpunk-neon", "dracula", "tokyo-night", "synthwave", "hud", "futuristic"],
        "best_for": ["黑客松", "游戏发布", "Web3 路演", "电子音乐"],
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
    lines.append("")
    lines.append("### 瑞士国际主义风格特别约束（选择此风格时必须遵守）")
    lines.append("")
    lines.append("- **只用直角**：所有 rect 的 rx/ry=0，严禁圆角。圆角 = 立刻违反风格契约")
    lines.append("- **1px hairline 边框**：用 `stroke=\"var(--border)\" stroke-width=\"1\"`，严禁阴影滤镜/gradient/blur")
    lines.append("- **极端字号反差**：封面标题 9-12vw 级（48-72px），正文 14-16px，标签 11px uppercase letter-spacing=0.08em")
    lines.append("- **16 列隐式网格**：所有元素对齐到 1280/16=80px 的列网格上")
    lines.append("- **单一饱和 accent**：整份 deck 仅使用一个高饱和强调色，其余为黑白灰中性色")
    lines.append("- **不许编造数据**：数字必须来自用户输入，图表柱高/弧度为真实数据按比例")
    lines.append("")
    lines.append("### 玻璃层次风格特别约束（选择此风格时必须遵守）")
    lines.append("")
    lines.append("- **每层必有 backdrop-blur**：所有卡片/面板使用毛玻璃效果，底层隐约透出背景色块")
    lines.append("- **多层深度**：至少 3 层视觉深度——背景装饰色块 → 半透明卡片 → 前景内容")
    lines.append("- **精致阴影**：用双层阴影（近距离浅 + 远距离深）营造浮动感，禁止 flat")
    lines.append("- **圆角 16-24px**：所有面板、卡片、图片使用大圆角，按钮 12px")
    lines.append("- **禁止实色背景**：不使用纯白/纯黑不透明面板，所有面板至少 60% 透明度")
    return "\n".join(lines)
