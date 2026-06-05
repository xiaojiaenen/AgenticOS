# AgenticOS Design System

## Register
Product — 面向普通用户的 AI 平台

## 设计哲学
安静的助手。温暖、友好、不吓人。保留亮色，做减法。

## Color Palette

### Background
- Base: #f8fafc (surface-0)
- Card: #ffffff (surface-1)

### Brand
- Primary: #2b87c2 (brand-500, 降低饱和度的 sky)
- Hover: #1e6ea0 (brand-600)
- Light: #ddeaf8 (brand-100)

### Text
- Primary: #1e293b
- Secondary: #64748b
- Muted: #94a3b8
- Disabled: #cbd5e1

### Borders
- Subtle: rgba(15,23,42, 0.06)
- Medium: rgba(15,23,42, 0.10)
- Strong: rgba(15,23,42, 0.15)

### Semantic
- Success: #3daa6d
- Error: #d94444
- Warning: #e8a817
- Info: #4582e6

## Typography
- Body: Plus Jakarta Sans, 400/500/600
- Display: Space Grotesk, 500/700
- Mono: JetBrains Mono, 400/500

### Hierarchy
- H1: text-2xl font-semibold
- H2: text-xl font-semibold
- H3: text-lg font-medium
- Body: text-sm font-normal
- Label: text-xs font-medium
- Kicker: text-[11px] font-medium uppercase tracking-[0.08em]

## Spacing
- Section: py-16 to py-24
- Card: p-6
- Compact: p-4
- Tight: p-2

## Border Radius
- Button/Input: rounded-md (8px)
- Card: rounded-lg (12px)
- Modal: rounded-xl (16px)
- Badge: rounded-full

## Shadows
- xs: 0 1px 2px rgba(0,0,0,0.04)
- sm: 0 2px 8px rgba(0,0,0,0.06)
- md: 0 4px 16px rgba(0,0,0,0.08)
- focus: 0 0 0 3px rgba(43,135,194,0.15)

## Components
- Cards: single border, no ring, no shadow stacking
- Buttons: solid color, no gradient, no hover lift
- Inputs: clean border, focus glow
- Glass: only sidebar/modal, not everywhere

## Motion
- Duration: 150-300ms
- Easing: cubic-bezier(0.16, 1, 0.3, 1)
- Entry: opacity + translate-y-2 (subtle)
- No infinite animations
- No blob animations
- prefers-reduced-motion: instant

## Icons
- Lucide React (single library, no mixing)

## 关键规则
1. 每个元素只用一种边框处理（border OR shadow，不同时用）
2. 字体粗细梯度：600/500/400，不用 700/800
3. 所有页面共用同一套背景，不自定义渐变
4. backdrop-blur 只用于 sidebar 和 modal
5. 动画只用于状态变化反馈，不用于装饰
