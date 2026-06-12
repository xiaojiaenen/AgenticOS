import React, { useEffect, useRef, useState } from 'react';

interface BorderGlowProps {
  children: React.ReactNode;
  color?: string;
  glowSize?: number;
  duration?: number;
  className?: string;
  style?: React.CSSProperties;
}

export const BorderGlow: React.FC<BorderGlowProps> = ({
  children,
  color = 'rgba(10, 132, 255, 0.6)',
  glowSize = 8,
  duration = 3,
  className = '',
  style = {},
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const animationRef = useRef<number>();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let angle = 0;
    const rect = container.getBoundingClientRect();

    const animate = () => {
      angle = (angle + 1) % 360;
      const radian = (angle * Math.PI) / 180;

      // 计算发光点在边框上的位置
      const x = Math.cos(radian) * (rect.width / 2) + rect.width / 2;
      const y = Math.sin(radian) * (rect.height / 2) + rect.height / 2;

      setPosition({ x, y });
      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
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
    >
      {/* 发光边框效果 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 'inherit',
          padding: 1,
          background: `radial-gradient(circle at ${position.x}px ${position.y}px, ${color}, transparent 70%)`,
          WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
          pointerEvents: 'none',
          transition: 'background 0.1s ease',
        }}
      />

      {/* 外发光效果 */}
      <div
        style={{
          position: 'absolute',
          inset: -glowSize,
          borderRadius: 'inherit',
          background: `radial-gradient(circle at ${position.x}px ${position.y}px, ${color}, transparent 70%)`,
          opacity: 0.3,
          filter: `blur(${glowSize}px)`,
          pointerEvents: 'none',
          transition: 'background 0.1s ease',
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
