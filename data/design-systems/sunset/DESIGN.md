## 1. Visual Theme & Atmosphere

Dramatic sunset captured as a design palette. Deep violet canvas (`#1a0a1e`) with warm coral, peach, and gold accents transitioning like the sky at golden hour. Bold gradients, emotional warmth, cinematic scale. Dark enough for the warm colors to pop, light enough in the purples to feel luxurious. Every slide should feel like a movie poster.

**Mood:** Dramatic, emotional, cinematic, luxurious.
**Best for:** Brand launches, creative pitches, fashion, film/entertainment, photography, luxury goods.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#1a0a1e` | Full-slide background |
| Soft BG | `--bg-soft` | `#200d26` | Gradient bases |
| Surface | `--surface` | `#281533` | Cards, panels |
| Surface 2 | `--surface-2` | `#341d45` | Embedded content |
| Border | `--border` | `#452956` | Subtle dividers |
| Border Strong | `--border-strong` | `#5a3870` | Active states |
| Text 1 | `--text-1` | `#f5e6f0` | Headlines |
| Text 2 | `--text-2` | `#d4b8d8` | Body text |
| Text 3 | `--text-3` | `#9a80a8` | Muted, footnotes |
| Accent | `--accent` | `#ff6b6b` | Primary CTA, key metrics |
| Accent 2 | `--accent-2` | `#ffa07a` | Secondary highlights, warmth |
| Accent 3 | `--accent-3` | `#ffd93d` | Tertiary accents, gold highlights |
| Good | `--good` | `#7bc67e` | Growth, success |
| Warn | `--warn` | `#ffb347` | Cautions |
| Bad | `--bad` | `#ff4757` | Errors, declines |

## 3. Typography

- **Display:** Inter or serif (Playfair Display) for hero slides, 700-800 weight
- **Body:** Inter or system sans-serif, 400 weight, text-2, 18-24px
- **Code:** JetBrains Mono, 14-16px
- Hero headlines can use `--grad` fill for gradient text effect

## 4. Prompt Guide

- Every hero slide needs a gradient — coral → peach → gold at 135deg
- Coral (`--accent`) for the most important data, gold (`--accent-3`) for highlights
- Use serif typography (Playfair Display) for section openers to enhance the cinematic feel
- Dark violet `--surface` cards with no border, letting color contrast define separation
