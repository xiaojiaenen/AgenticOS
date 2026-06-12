import React from 'react';
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';
import { BorderGlow, glowPresets } from './BorderGlow';

interface GlassWithGlowProps {
  children: React.ReactNode;
  /** LiquidGlass 预设 */
  preset?: keyof typeof glassPresets;
  /** 发光颜色预设 */
  glowColor?: keyof typeof glowPresets | string;
  /** 发光大小 */
  glowSize?: number;
  /** 圆角半径 */
  radius?: number;
  /** 色调 */
  tint?: string;
  /** 是否禁用发光效果 */
  disableGlow?: boolean;
  /** 自定义样式 */
  style?: React.CSSProperties;
  /** 自定义类名 */
  className?: string;
  /** 点击事件 */
  onClick?: () => void;
  /** 其他属性 */
  [key: string]: any;
}

export const GlassWithGlow: React.FC<GlassWithGlowProps> = ({
  children,
  preset = 'control',
  glowColor = 'blue',
  glowSize = 8,
  radius = 16,
  tint,
  disableGlow = false,
  style = {},
  className = '',
  onClick,
  ...props
}) => {
  const presetConfig = glassPresets[preset];
  const glowColorValue = glowPresets[glowColor as keyof typeof glowPresets] || glowColor;

  const glassElement = (
    <LiquidGlass
      {...presetConfig}
      tint={tint || 'rgba(255,255,255,0.08)'}
      radius={radius}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
      onClick={onClick}
      className={className}
      {...props}
    >
      {children}
    </LiquidGlass>
  );

  if (disableGlow) {
    return glassElement;
  }

  return (
    <BorderGlow
      color={glowColorValue}
      glowSize={glowSize}
      style={{ borderRadius: radius }}
    >
      {glassElement}
    </BorderGlow>
  );
};

// 便捷预设组件
export const GlassButtonWithGlow: React.FC<Omit<GlassWithGlowProps, 'preset'>> = (props) => (
  <GlassWithGlow preset="control" {...props} />
);

export const GlassCardWithGlow: React.FC<Omit<GlassWithGlowProps, 'preset'>> = (props) => (
  <GlassWithGlow preset="card" {...props} />
);
