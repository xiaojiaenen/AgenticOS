## 1. Visual Theme & Atmosphere

Warm latte foam on a cream morning. The light counterpart to Catppuccin Mocha — soft, airy, gentle on the eyes. Cream canvas (`#eff1f5`) with mauve and pink accents. No harsh whites, no aggressive contrast. Every surface is slightly tinted, creating a layered, editorial feel. Perfect for long-form reading and data-dense slides.

**Mood:** Gentle, refined, editorial, comforting.
**Best for:** Brand decks, lifestyle presentations, education, editorial reports, wellness.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#eff1f5` | Full-slide background |
| Soft BG | `--bg-soft` | `#e6e9ef` | Section alternation |
| Surface | `--surface` | `#ffffff` | Cards, panels |
| Surface 2 | `--surface-2` | `#f4f6fc` | Table rows, embedded content |
| Border | `--border` | `#d1d5e0` | Subtle card borders |
| Border Strong | `--border-strong` | `#bcc0cc` | Section dividers |
| Text 1 | `--text-1` | `#4c4f69` | Headlines |
| Text 2 | `--text-2` | `#5c5f77` | Body text |
| Text 3 | `--text-3` | `#8c8fa1` | Captions, footnotes |
| Accent | `--accent` | `#8839ef` | CTA, key figures |
| Accent 2 | `--accent-2` | `#ea76cb` | Secondary highlights, emphasis |
| Accent 3 | `--accent-3` | `#1e66f5` | Links, tertiary accents |
| Good | `--good` | `#40a02b` | Growth, success |
| Warn | `--warn` | `#df8e1d` | Cautions |
| Bad | `--bad` | `#d20f39` | Errors, declines |

## 3. Typography

- **Display:** Inter or system sans-serif, 600-700 weight, text-1
- **Body:** 400 weight, text-2, 18-24px
- **Code:** JetBrains Mono, 14-16px, accent
- Generous line-height (1.5) for long-form readability

## 4. Prompt Guide

- Cards are white (`--surface`) with single-pixel `--border` strokes, subtle shadow OK
- Use `--accent` (mauve) sparingly for emphasis — let the cream/white dominate
- Pink (`--accent-2`) for emotional highlights, blue (`--accent-3`) for logical links
- Avoid heavy borders; the palette creates depth through subtle color shifts
