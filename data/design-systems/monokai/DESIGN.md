## 1. Visual Theme & Atmosphere

The code editor theme that defined a generation. Warm charcoal canvas (`#272822`) with lime green, hot pink, and electric cyan accents. Nostalgic yet modern — the color of late-night coding sessions. High readability, warm undertones (the background is dark brown-tinted, not blue-tinted), and primary accent in bright lime green that commands attention.

**Mood:** Developer-native, energetic, nostalgic, functional.
**Best for:** Dev tools, coding platforms, technical tutorials, hackathons, API documentation.

## 2. Color Palette & Roles

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Canvas | `--bg` | `#272822` | Full-slide background |
| Soft BG | `--bg-soft` | `#2e2f28` | Gradient bases |
| Surface | `--surface` | `#333530` | Cards, panels |
| Surface 2 | `--surface-2` | `#3e3f36` | Code blocks, embedded code |
| Border | `--border` | `#49483e` | Subtle dividers |
| Border Strong | `--border-strong` | `#75715e` | Active states |
| Text 1 | `--text-1` | `#f8f8f2` | Headlines |
| Text 2 | `--text-2` | `#cfcfc2` | Body text |
| Text 3 | `--text-3` | `#8b8b7e` | Muted, footnotes |
| Accent | `--accent` | `#a6e22e` | Primary CTA, key metrics, strings |
| Accent 2 | `--accent-2` | `#f92672` | Secondary emphasis, keywords |
| Accent 3 | `--accent-3` | `#66d9ef` | Links, class names, tertiary |
| Good | `--good` | `#a6e22e` | Growth, success |
| Warn | `--warn` | `#e6db74` | Cautions |
| Bad | `--bad` | `#f92672` | Errors, declines |

## 3. Typography

- **Display:** Inter or system sans-serif, 700 weight, text-1 or accent
- **Body:** 400 weight, text-2, 18-24px
- **Code:** JetBrauns Mono or Fira Code, 14-16px — the green/pink/cyan syntax coloring IS the brand
- Monospace for all data/metric displays to reinforce the developer aesthetic

## 4. Prompt Guide

- Lime green (`--accent`) is the unmistakable Monokai signature — use prominently
- Pink (`--accent-2`) for emphasis, cyan (`--accent-3`) for links and metadata
- Code blocks on `--surface-2` with green strings, pink keywords, cyan identifiers
- Yellow (`--warn`) function calls out warnings without feeling like errors
