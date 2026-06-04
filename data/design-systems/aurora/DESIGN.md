## 1. Visual Theme & Atmosphere

Northern lights captured in a dark sky. Deep navy canvas (`#0a1628`) with shifting bands of emerald green, teal, and indigo. Smooth gradients, soft glows, and organic flow. Not cyberpunk's aggression — this is calm, mysterious, awe-inspiring. Gradients should transition through 3-4 color stops, never just 2.

**Mood:** Ethereal, visionary, futuristic but human.
**Best for:** AI/ML research, climate tech, space tech, biotech, visionary keynotes.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#0a1628` | Full-slide background |
| Soft BG | `--bg-soft` | `#0d1d35` | Gradient overlay base |
| Surface | `--surface` | `#112240` | Cards, panels |
| Surface 2 | `--surface-2` | `#1a3055` | Data tables, code blocks |
| Border | `--border` | `#1e3a5f` | Subtle dividers |
| Border Strong | `--border-strong` | `#2a5080` | Active states, focus |
| Text 1 | `--text-1` | `#dce6f5` | Headlines |
| Text 2 | `--text-2` | `#8899bb` | Body text |
| Text 3 | `--text-3` | `#556688` | Muted, footnotes |
| Accent | `--accent` | `#64ffda` | Key metrics, CTA, primary glow |
| Accent 2 | `--accent-2` | `#00e5a0` | Secondary highlights |
| Accent 3 | `--accent-3` | `#00b8d4` | Links, tertiary accents |
| Good | `--good` | `#64ffda` | Growth, success |
| Warn | `--warn` | `#ffd54f` | Warnings |
| Bad | `--bad` | `#ff5c8a` | Errors, declines |

## 3. Typography

- **Display:** Inter or system sans-serif, 700 weight, accent or text-1
- **Body:** 400 weight, text-2, 18-24px
- **Code:** JetBrains Mono, 14-16px, teal accent
- Gradient text (`--grad` as fill) for hero headlines

## 4. Prompt Guide

- Lead with a dramatic hero slide — full-width gradient with one big number
- Use `--grad` and `--grad-soft` generously as background overlays
- Soft glow filters on accent elements (not harsh neon, warm diffuse light)
- Every 3rd slide should use a different accent from the gradient as dominant color
