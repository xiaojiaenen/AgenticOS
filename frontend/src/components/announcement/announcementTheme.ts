import type { AnnouncementTheme } from '../../services/announcementService';

/* ──────────────────────────────────────
   Shared light-theme definitions
   All three themes use the system's
   glassmorphism + light-gradient style
   ────────────────────────────────────── */

export type ThemeDef = {
  label: string;
  chipGradient: string;
  bgGradient: string;
  orbA: string;
  orbB: string;
  orbC: string;
  borderColor: string;
  shadow: string;
  accentClass: string;
  accentLightClass: string;
  accentTextClass: string;
  ctaBg: string;
  dotColor: string;
};

export const THEME_DEFS: Record<AnnouncementTheme, ThemeDef> = {
  // sky-blue — system primary brand
  aurora: {
    label: 'Aurora',
    chipGradient: 'linear-gradient(135deg, #0ea5e9 0%, #22d3ee 52%, #34d399 100%)',
    bgGradient: 'linear-gradient(160deg, #e8f4fd 0%, #d4ecf8 28%, #e0f2fe 55%, #c9e6f4 82%, #dff0f8 100%)',
    orbA: 'radial-gradient(circle, rgba(14,165,233,0.24), transparent 64%)',
    orbB: 'radial-gradient(circle, rgba(6,182,212,0.18), transparent 62%)',
    orbC: 'radial-gradient(circle, rgba(56,189,248,0.12), transparent 58%)',
    borderColor: 'rgba(186,230,253,0.65)',
    shadow: '0 24px 80px rgba(15,23,42,0.10), 0 0 0 1px rgba(255,255,255,0.55) inset',
    accentClass: 'bg-brand-500',
    accentLightClass: 'bg-brand-100',
    accentTextClass: 'text-brand-700',
    ctaBg: 'bg-brand-500 hover:bg-brand-600',
    dotColor: 'rgba(14,165,233,0.35)',
  },
  // warm coral/amber — energetic but light
  sunset: {
    label: 'Sunset',
    chipGradient: 'linear-gradient(135deg, #f59e0b 0%, #fb923c 52%, #fb7185 100%)',
    bgGradient: 'linear-gradient(160deg, #fef6ee 0%, #fef0e0 28%, #fef7f0 55%, #fde8d4 82%, #fef3e6 100%)',
    orbA: 'radial-gradient(circle, rgba(251,146,60,0.20), transparent 64%)',
    orbB: 'radial-gradient(circle, rgba(244,114,182,0.14), transparent 62%)',
    orbC: 'radial-gradient(circle, rgba(245,158,11,0.10), transparent 58%)',
    borderColor: 'rgba(253,186,116,0.55)',
    shadow: '0 24px 80px rgba(120,50,10,0.09), 0 0 0 1px rgba(255,255,255,0.55) inset',
    accentClass: 'bg-orange-500',
    accentLightClass: 'bg-orange-100',
    accentTextClass: 'text-orange-700',
    ctaBg: 'bg-orange-500 hover:bg-orange-600',
    dotColor: 'rgba(251,146,60,0.30)',
  },
  // indigo/violet — elegant, calm
  midnight: {
    label: 'Midnight',
    chipGradient: 'linear-gradient(135deg, #818cf8 0%, #8b5cf6 52%, #d946ef 100%)',
    bgGradient: 'linear-gradient(160deg, #f0f0fd 0%, #e8e4f8 28%, #efeefc 55%, #e2dcf6 82%, #ece8fa 100%)',
    orbA: 'radial-gradient(circle, rgba(99,102,241,0.20), transparent 64%)',
    orbB: 'radial-gradient(circle, rgba(139,92,246,0.14), transparent 62%)',
    orbC: 'radial-gradient(circle, rgba(129,140,248,0.10), transparent 58%)',
    borderColor: 'rgba(165,180,252,0.55)',
    shadow: '0 24px 80px rgba(30,20,80,0.09), 0 0 0 1px rgba(255,255,255,0.55) inset',
    accentClass: 'bg-violet-500',
    accentLightClass: 'bg-violet-100',
    accentTextClass: 'text-violet-700',
    ctaBg: 'bg-violet-500 hover:bg-violet-600',
    dotColor: 'rgba(139,92,246,0.28)',
  },
};
