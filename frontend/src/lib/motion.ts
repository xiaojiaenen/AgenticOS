/**
 * 全站共享 motion variants —— 统一动效语言。
 *
 * 基准：150-250ms 入场，easeOutQuint [0.16, 1, 0.3, 1]（与 .admin-page-stage、
 * AdminSidebar 既有曲线一致），位移 ≤ 12px，克制不抢戏。
 *
 * 使用约定：
 *  - 列表/卡片群入场：外层 <motion.div variants={staggerContainer} initial="hidden" animate="show">，
 *    子项 <motion.div variants={listItem}>，stagger 由容器统一控制。
 *  - 单元素入场：variants={fadeUp} 或直接用 transition 常量。
 *  - 全部遵循全局 prefers-reduced-motion（index.css 已有 CSS 层 kill-switch；
 *    motion 层用 useReducedMotion 自行降级为纯透明度）。
 */
import type { Transition, Variants } from 'motion/react';

/** 标准入场曲线（easeOutQuint）——与 admin-stage-in / AdminSidebar 既有实现一致 */
export const EASE_OUT_QUINT = [0.16, 1, 0.3, 1] as const;

/** 标准入场 transition（可 spread 到任意 variant） */
export const enterTransition: Transition = {
  duration: 0.24,
  ease: EASE_OUT_QUINT,
};

/** 更快的微交互 transition（hover 反馈、胶囊出现等） */
export const microTransition: Transition = {
  duration: 0.15,
  ease: EASE_OUT_QUINT,
};

/** 弹簧（用于 layoutId 指示器、可拖拽元素） */
export const springTransition: Transition = {
  type: 'spring',
  stiffness: 400,
  damping: 32,
};

/** 单元素淡入上移（8px，克制） */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: enterTransition },
};

/** 单元素纯淡入（reduced-motion 或无位移场景） */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: enterTransition },
};

/** 列表子项 —— 与 staggerContainer 配套（12px 位移，比单元素略明显） */
export const listItem: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: enterTransition },
};

/**
 * stagger 容器 —— 子项依次入场，每项间隔 0.045s，整体不超过 ~0.4s。
 * staggerChildren 上限受 maxStaggerDuration 约束，长列表不至于拖沓。
 */
export const staggerContainer: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.045,
      delayChildren: 0.04,
    },
  },
};

/**
 * 弹层内容入场（modal/drawer 内容块）：轻微缩放 + 上移，
 * 与 tw-animate-css 的 zoom-in-95/fade-in-0 视觉语言一致。
 */
export const popIn: Variants = {
  hidden: { opacity: 0, scale: 0.97, y: 8 },
  show: { opacity: 1, scale: 1, y: 0, transition: enterTransition },
  exit: { opacity: 0, scale: 0.98, y: 4, transition: { duration: 0.12, ease: 'easeIn' } },
};
