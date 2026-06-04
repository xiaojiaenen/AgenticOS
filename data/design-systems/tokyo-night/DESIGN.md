## 1. Visual Theme & Atmosphere

Tokyo skyline at midnight — deep navy, electric blue, and neon pink. Midnight-blue canvas (`#1a1b26`) with blue-accent dominance and pink/purple for emphasis. Clean, geometric, modern. High contrast without harshness. Cards and surfaces are slightly lighter blue-tinted, creating layered depth. This is the dark theme for power users who want focus and beauty.

**Mood:** Modern, focused, sophisticated, technical.
**Best for:** API docs, developer tools, infrastructure, platform presentations, DevOps.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#1a1b26` | Full-slide background |
| Soft BG | `--bg-soft` | `#1f2035` | Gradient bases |
| Surface | `--surface` | `#24253d` | Cards, panels |
| Surface 2 | `--surface-2` | `#2e3054` | Code blocks, embedded content |
| Border | `--border` | `#3b3d60` | Subtle dividers |
| Border Strong | `--border-strong` | `#565a7e` | Active states |
| Text 1 | `--text-1` | `#c0caf5` | Headlines |
| Text 2 | `--text-2` | `#a9b1d6` | Body text |
| Text 3 | `--text-3` | `#6c7086` | Muted, footnotes |
| Accent | `--accent` | `#7aa2f7` | Primary CTA, key metrics |
| Accent 2 | `--accent-2` | `#bb9af7` | Secondary highlights, emphasis |
| Accent 3 | `--accent-3` | `#f7768e` | Links, tertiary accents, alerts |
| Good | `--good` | `#9ece6a` | Growth, success |
| Warn | `--warn` | `#e0af68` | Cautions |
| Bad | `--bad` | `#f7768e` | Errors, declines |

## 3. Typography

- **Display:** Inter or system sans-serif, 700 weight, text-1 or accent
- **Body:** 400 weight, text-2, 18-24px
- **Code:** JetBrains Mono, 14-16px, accent
- Clean geometric layout with strong grid alignment

## 4. Prompt Guide

- Blue (`--accent`) carries the primary visual weight — use for headlines and CTAs
- Purple (`--accent-2`) for secondary emphasis, pink (`--accent-3`) for alerts/highlights
- Cards should use `--surface` with `--border` at 1px, no shadow needed on dark
- Green/good metrics pop beautifully against the blue-dark background
