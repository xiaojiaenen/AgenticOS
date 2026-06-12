import React from 'react';
import { LiquidGlass, glassPresets, radii } from '@xiaojiaenen/liquid-glass';
import { useTheme } from '../../hooks/useTheme';
import LightRays from './LightRays';

type GlassPreset = 'pill' | 'control' | 'card';

const presetRadii: Record<GlassPreset, number> = {
  pill: radii.pill,
  control: radii.control,
  card: radii.card,
};

interface GlassThemeWrapperProps {
  children: React.ReactNode;
  preset?: GlassPreset;
  className?: string;
  /** Custom tint override */
  tint?: string;
  /** Custom radius override */
  radius?: number;
  /** Whether to wrap with LiquidGlass even in non-glass themes */
  forceGlass?: boolean;
}

/**
 * Conditionally wraps children with LiquidGlass when the liquid-glass theme is active.
 * In other themes, renders children directly with the provided className.
 */
export const GlassThemeWrapper: React.FC<GlassThemeWrapperProps> = ({
  children,
  preset = 'card',
  className,
  tint,
  radius,
  forceGlass = false,
}) => {
  const { theme } = useTheme();
  const isGlass = theme === 'liquid-glass' || forceGlass;

  if (!isGlass) {
    return <div className={className}>{children}</div>;
  }

  const presetConfig = glassPresets[preset];

  return (
    <>
      <LightRays
        raysOrigin="top-center"
        raysColor="rgba(100, 180, 255, 0.15)"
        raysSpeed={1.5}
        lightSpread={1.2}
        rayLength={2.5}
        fadeDistance={1.2}
        saturation={0.8}
        followMouse={true}
        mouseInfluence={0.15}
      />
      <LiquidGlass
        {...presetConfig}
        tint={tint ?? 'rgba(255,255,255,0.04)'}
        radius={radius ?? presetRadii[preset]}
      >
        <div className={className}>{children}</div>
      </LiquidGlass>
    </>
  );
};

/**
 * Hook to check if liquid-glass theme is active.
 * Useful for inline conditional logic in components.
 */
export function useIsGlassTheme() {
  const { theme } = useTheme();
  return theme === 'liquid-glass';
}
