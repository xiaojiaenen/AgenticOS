## 1. Visual Theme & Atmosphere

Warm, cozy, pastel-toned dark theme. Deep mauve canvas (`#1e1e2e`) with lavender, pink, and blue pastel accents. The dark mode that doesn't feel dark — it feels like a warm cafe at dusk. Rounded corners, soft transitions, no harsh contrast. Every color is slightly muted, slightly warm. Cards have subtle surface elevation, not stark borders.

**Mood:** Cozy, creative, warm, approachable.
**Best for:** Design systems, lifestyle apps, education, storytelling, indie products.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#1e1e2e` | Full-slide background |
| Soft BG | `--bg-soft` | `#242438` | Gradient overlay bases |
| Surface | `--surface` | `#2a2a42` | Cards, panels |
| Surface 2 | `--surface-2` | `#333356` | Code blocks, embedded content |
| Border | `--border` | `#454575` | Subtle dividers |
| Border Strong | `--border-strong` | `#585b70` | Active states |
| Text 1 | `--text-1` | `#cdd6f4` | Headlines |
| Text 2 | `--text-2` | `#bac2de` | Body text |
| Text 3 | `--text-3` | `#7f849c` | Muted, footnotes |
| Accent | `--accent` | `#cba6f7` | Primary CTA, key metrics |
| Accent 2 | `--accent-2` | `#f5c2e7` | Secondary highlights |
| Accent 3 | `--accent-3` | `#89b4fa` | Links, tertiary accents |
| Good | `--good` | `#a6e3a1` | Growth, success |
| Warn | `--warn` | `#f9e2af` | Cautions |
| Bad | `--bad` | `#f38ba8` | Errors, declines |

## 3. Typography

- **Display:** Inter or system sans-serif, 600-700 weight, text-1 or accent
- **Body:** 400 weight, text-2, 18-24px
- **Code:** JetBrains Mono, 14-16px, accent-3
- Rounded, friendly feel — pair with generous border-radius (12-20px)

## 4. Prompt Guide

- Cards should use `--surface` with `--border` stroke at 1px, rx=16
- Gradient overlays (`--grad-soft`) on hero slides for warmth
- Lavender/pink/blue form a triad — cycle through them across sections
- Never use pure white text; `--text-1` (#cdd6f4) is the whitest you'll go
