## 1. Visual Theme & Atmosphere

Neon-drenched futuristic aesthetic. Jet-black canvas (`#0a0a1a`) with high-voltage cyan accents. Electric magenta and yellow for emphasis. Think Neo-Tokyo at midnight — dense information panes, glowing borders, monospace data displays. Maximalist but structured. Angles and grids dominate. No soft shadows — use hard glow (`feGaussianBlur` on accent colors).

**Mood:** High-tech, adrenaline, edge, rebellion.
**Best for:** Gaming, crypto, cybersecurity, hackathon, sci-fi presentations.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#0a0a1a` | Full-slide background |
| Soft BG | `--bg-soft` | `#0f0f2a` | Section backgrounds, subtle panels |
| Surface | `--surface` | `#12123a` | Cards, elevated containers |
| Surface 2 | `--surface-2` | `#1a1a4a` | Code blocks, secondary cards |
| Border | `--border` | `#2a2a6a` | Dividers, card borders |
| Border Strong | `--border-strong` | `#4a3aaa` | Active borders, focus rings |
| Text 1 | `--text-1` | `#e0e0ff` | Headlines, primary content |
| Text 2 | `--text-2` | `#a0a0dd` | Body text, descriptions |
| Text 3 | `--text-3` | `#6060aa` | Muted labels, footnotes |
| Accent | `--accent` | `#00ffcc` | Primary CTA, key metrics, glow elements |
| Accent 2 | `--accent-2` | `#ff00aa` | Secondary emphasis, highlights |
| Accent 3 | `--accent-3` | `#ffdd00` | Warnings, alerts, tertiary accents |
| Good | `--good` | `#00ff88` | Positive metrics, growth indicators |
| Warn | `--warn` | `#ffaa00` | Cautions, amber alerts |
| Bad | `--bad` | `#ff3366` | Errors, negative trends, destructive actions |

## 3. Typography

- **Display/Headlines:** Inter or system sans-serif, 700-800 weight, cyan accent
- **Body:** 400 weight, text-2 color, 16-24px
- **Code/Data:** JetBrains Mono, monospace, 14-18px, green-on-dark
- **Hierarchy:** Size drops in multiples of 8px (80/64/48/36/28/20/16/14)

## 4. Prompt Guide

- Use `filter="url(#neonGlow)"` for accent-colored glows behind key numbers
- Borders should be 1-2px, never heavy — let color do the work
- Every page gets one neon accent element as visual anchor
- Avoid pure white text — always use `--text-1` (#e0e0ff) which is slightly blue-tinted
