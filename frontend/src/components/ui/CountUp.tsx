/**
 * 数字滚动 —— 进入视口后从 0 计数到目标值。
 *
 * - spring 近似 easeOutQuint 的收尾感（前快后慢）；
 * - value 变化（如切换年份）时从当前值继续滚动，不回零；
 * - `prefers-reduced-motion` 直接渲染终值（不走 spring）；
 * - `format` 接项目的数字格式化函数（formatNumber / formatTokenNumber /
 *   formatLatency 等，都是「纯函数 of 数字」），保证与静态渲染同口径。
 */
import { useEffect, useRef } from 'react';
import { motion, useInView, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react';

const IDENTITY = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

export function CountUp({
  value,
  format,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  // once: true —— 首次进入视口即触发，之后不因滚动来回重放
  const inView = useInView(ref, { once: true, margin: '-10% 0px' });
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 90, damping: 24, mass: 0.6 });
  const text = useTransform(spring, (v) => (format ?? IDENTITY)(Math.round(v)));

  useEffect(() => {
    if (!reduced && inView) mv.set(value);
  }, [inView, value, reduced, mv]);

  if (reduced) {
    // 终值直出：hooks 已全部在上方调用，这里只是渲染分支
    return <span ref={ref} className={className}>{(format ?? IDENTITY)(value)}</span>;
  }
  return (
    <motion.span ref={ref} className={className}>
      {text}
    </motion.span>
  );
}
