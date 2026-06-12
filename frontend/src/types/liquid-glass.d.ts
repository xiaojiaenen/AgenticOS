declare module '@xiaojiaenen/liquid-glass' {
  import React from 'react';

  interface LiquidGlassProps {
    children?: React.ReactNode;
    radius?: number;
    bezelWidth?: number;
    glassThickness?: number;
    refractiveIndex?: number;
    refractionScale?: number;
    blur?: number;
    saturate?: number;
    tint?: string;
    as?: React.ElementType;
    profile?: string;
    parallax?: boolean;
    backdropBlur?: number;
    disabled?: boolean;
    className?: string;
    style?: React.CSSProperties;
    onClick?: (e: React.MouseEvent) => void;
    role?: string;
    tabIndex?: number;
    'aria-label'?: string;
    'aria-checked'?: boolean | 'true' | 'false' | 'mixed';
    'aria-expanded'?: boolean;
    'aria-pressed'?: boolean | 'true' | 'false' | 'mixed';
    'aria-disabled'?: boolean | 'true' | 'false';
    'aria-selected'?: boolean;
    'aria-current'?: 'page' | 'step' | 'location' | 'date' | 'time' | 'true' | 'false' | boolean;
    'aria-live'?: 'off' | 'polite' | 'assertive';
    'aria-hidden'?: boolean;
    id?: string;
    [key: string]: any;
  }

  export const LiquidGlass: React.ForwardRefExoticComponent<
    LiquidGlassProps & React.RefAttributes<HTMLElement>
  >;

  export interface GlassProviderProps {
    children?: React.ReactNode;
    defaultMode?: 'light' | 'dark' | 'system';
  }

  export const GlassProvider: React.FC<GlassProviderProps>;

  export const glassPresets: {
    pill: { bezelWidth: number; glassThickness: number; refractionScale: number; blur: number };
    control: { bezelWidth: number; glassThickness: number; refractionScale: number; blur: number };
    card: { bezelWidth: number; glassThickness: number; refractionScale: number; blur: number };
  };

  export const radii: {
    control: number;
    card: number;
    sheet: number;
    pill: number;
  };

  export const spring: {
    default: string;
    gentle: string;
    snappy: string;
  };

  export const systemColors: Record<string, string>;

  export function useLiquidGlass(opts?: any): any;
  export function useGlassParallax(enabled?: boolean, onAngle?: (angle: any) => void): any;
  export function useGlassTheme(): any;
  export function useBackgroundLuminance(ref: React.RefObject<any>): any;
  export function useReducedMotion(): boolean;
  export function useToast(): any;
  export function withLiquidGlass<P>(component: React.ComponentType<P>, opts?: any): React.FC<P>;

  export const GlassButton: React.FC<{
    children: React.ReactNode;
    onClick?: () => void;
    variant?: 'regular' | 'prominent';
    size?: 'default' | 'small';
    disabled?: boolean;
    'aria-label'?: string;
  }>;

  export const GlassCard: React.FC<{
    title?: string;
    children?: React.ReactNode;
    icon?: React.ReactNode;
    interactive?: boolean;
    onClick?: () => void;
    width?: number | string;
  }>;

  export const GlassModal: React.FC<{
    open: boolean;
    onClose: () => void;
    title?: string;
    children: React.ReactNode;
    width?: number | string;
  }>;

  export const GlassInput: React.FC<any>;
  export const GlassSearch: React.FC<any>;
  export const GlassSelect: React.FC<any>;
  export const GlassCheckbox: React.FC<any>;
  export const GlassRadio: React.FC<any>;
  export const GlassSwitch: React.FC<any>;
  export const GlassSlider: React.FC<any>;
  export const GlassSegmented: React.FC<any>;
  export const GlassStepper: React.FC<any>;
  export const GlassDatePicker: React.FC<any>;
  export const GlassColorPicker: React.FC<any>;
  export const GlassList: React.FC<any>;
  export const GlassAccordion: React.FC<any>;
  export const GlassNotification: React.FC<any>;
  export const GlassProgress: React.FC<any>;
  export const GlassBadge: React.FC<any>;
  export const GlassAvatar: React.FC<any>;
  export const GlassTag: React.FC<any>;
  export const GlassChip: React.FC<any>;
  export const GlassIcon: React.FC<any>;
  export const GlassSpinner: React.FC<any>;
  export const GlassSkeleton: React.FC<any>;
  export const GlassEmptyState: React.FC<any>;
  export const GlassPageControl: React.FC<any>;
  export const GlassDivider: React.FC<any>;
  export const GlassToast: React.FC<any>;
  export const GlassTooltip: React.FC<any>;
  export const GlassPopover: React.FC<any>;
  export const GlassContextMenu: React.FC<any>;
  export const GlassPagination: React.FC<any>;
  export const GlassAlert: React.FC<any>;
  export const GlassCodeBlock: React.FC<any>;
  export const GlassCommandPalette: React.FC<any>;
  export const GlassOnboarding: React.FC<any>;
  export const GlassPullToRefresh: React.FC<any>;
  export const GlassSplitView: React.FC<any>;
  export const GlassTable: React.FC<any>;
  export const GlassTimeline: React.FC<any>;
  export const GlassTreeView: React.FC<any>;
  export const GlassMusicPlayer: React.FC<any>;
  export const GlassNavbar: React.FC<any>;
  export const GlassTabBar: React.FC<any>;
  export const GlassTabs: React.FC<any>;
  export const GlassSidebar: React.FC<any>;
  export const GlassToolbar: React.FC<any>;
  export const GlassToolbarButton: React.FC<any>;
  export const GlassSheet: React.FC<any>;
  export const Dock: React.FC<any>;
  export const DragGlass: React.FC<any>;
}

declare module '@xiaojiaenen/liquid-glass/styles' {
  const content: string;
  export default content;
}
