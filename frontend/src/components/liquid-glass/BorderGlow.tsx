import React, { useRef, useState, useCallback } from 'react';

interface BorderGlowProps {
  children: React.ReactNode;
  color?: string;
  glowSize?: number;
  className?: string;
  style?: React.CSSProperties;
}

export const BorderGlow: React.FC<BorderGlowProps> = ({
  children,
  color = 'rgba(10, 132, 255, 0.6)',
  glowSize = 8,
  className = '',
  style = {},
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setPosition({ x, y });
  }, []);

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
  }, []);

  return (
    <div
      ref={containerRef}
      className={`relative ${className}`}
      style={{
        ...style,
        position: 'relative',
        overflow: 'hidden',
      }}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* 发光边框效果 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 'inherit',
          padding: 1,
          background: isHovered
            ? `radial-gradient(circle at ${position.x}px ${position.y}px, ${color}, transparent 70%)`
            : 'none',
          WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
          pointerEvents: 'none',
          transition: 'opacity 0.3s ease',
          opacity: isHovered ? 1 : 0,
        }}
      />

      {/* 外发光效果 */}
      <div
        style={{
          position: 'absolute',
          inset: -glowSize,
          borderRadius: 'inherit',
          background: isHovered
            ? `radial-gradient(circle at ${position.x}px ${position.y}px, ${color}, transparent 70%)`
            : 'none',
          opacity: isHovered ? 0.3 : 0,
          filter: `blur(${glowSize}px)`,
          pointerEvents: 'none',
          transition: 'opacity 0.3s ease',
        }}
      />

      {/* 内容 */}
      <div style={{ position: 'relative', zIndex: 1 }}>
        {children}
      </div>
    </div>
  );
};

// 预设颜色
export const glowPresets = {
  blue: 'rgba(10, 132, 255, 0.6)',
  purple: 'rgba(191, 90, 242, 0.6)',
  green: 'rgba(48, 209, 88, 0.6)',
  orange: 'rgba(255, 159, 10, 0.6)',
  pink: 'rgba(255, 55, 95, 0.6)',
  teal: 'rgba(64, 200, 224, 0.6)',
  white: 'rgba(255, 255, 255, 0.6)',
  gold: 'rgba(255, 215, 0, 0.6)',
};
