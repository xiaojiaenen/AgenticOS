## 1. Visual Theme & Atmosphere

Arctic calm meets Scandinavian functionality. Frost-white canvas (`#eceff4`) with cool blue-grey accents. Nothing shouts — everything whispers with purpose. Inspired by the Nord editor theme and Nordic design philosophy. Generous whitespace, restrained palette, high readability. The color that's not there does as much work as the color that is.

**Mood:** Calm, professional, trustworthy, focused.
**Best for:** Academic papers, enterprise reports, medical/healthcare, government, financial statements.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#eceff4` | Full-slide background |
| Soft BG | `--bg-soft` | `#e5e9f0` | Section alternation |
| Surface | `--surface` | `#ffffff` | Cards, data panels |
| Surface 2 | `--surface-2` | `#f4f6fa` | Table rows, code blocks |
| Border | `--border` | `#d8dee9` | Subtle card borders |
| Border Strong | `--border-strong` | `#b0bec5` | Section dividers |
| Text 1 | `--text-1` | `#2e3440` | Headlines |
| Text 2 | `--text-2` | `#4c566a` | Body text |
| Text 3 | `--text-3` | `#7b88a1` | Captions, footnotes |
| Accent | `--accent` | `#5e81ac` | CTA, key figures |
| Accent 2 | `--accent-2` | `#81a1c1` | Secondary highlights |
| Accent 3 | `--accent-3` | `#88c0d0` | Tertiary accents, links |
| Good | `--good` | `#a3be8c` | Positive growth |
| Warn | `--warn` | `#ebcb8b` | Cautions |
| Bad | `--bad` | `#bf616a` | Negative trends |

## 3. Typography

- **Display:** Inter or system sans-serif, 600-700 weight, text-1
- **Body:** 400 weight, text-2, 18-24px
- **Code:** JetBrains Mono, 14-16px, accent
- Generous line-height (1.5-1.6) for readability

## 4. Prompt Guide

- Every slide needs breathing room — no more than 3 content blocks
- Cards are white (`--surface`) with a single-pixel `--border` stroke, no shadows
- Use `--surface-2` for alternating table rows, never zebra stripes
- Icons in `--accent` or `--text-3` only, never text-1
