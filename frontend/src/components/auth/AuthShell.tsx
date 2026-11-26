import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { RandomMascot } from '../ui/RandomMascot';

interface AuthShellProps {
  /** 返回按钮文案与目标；不传则不渲染返回按钮 */
  backLabel?: string;
  backTo?: string;
  children: React.ReactNode;
}

/**
 * 登录/注册共用页面壳：统一通透光感背景 + 轻盈动态 SVG 星环 + 毛玻璃返回胶囊 + 居中卡片槽位。
 */
export const AuthShell: React.FC<AuthShellProps> = ({ backLabel, backTo = '/', children }) => {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={false}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      className="relative min-h-screen overflow-hidden bg-[var(--background)] flex items-center justify-center p-4"
    >
      <div className="aos-ambient-bg" aria-hidden="true" />
      <div className="aos-ambient-dots" aria-hidden="true" />

      {/* 居中微动态星环装饰 */}
      <svg
        className="pointer-events-none fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[680px] max-w-[95vw] h-[420px] opacity-45 z-0"
        viewBox="0 0 680 420"
        fill="none"
        aria-hidden="true"
      >
        <ellipse cx="340" cy="210" rx="300" ry="120" stroke="#EA580C" strokeOpacity="0.18" strokeWidth="1" className="aos-svg-flow" />
        <ellipse cx="340" cy="210" rx="220" ry="86" stroke="#0284C7" strokeOpacity="0.16" strokeWidth="1" strokeDasharray="4 7" />
      </svg>

      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <RandomMascot
          size={360}
          className="absolute -bottom-20 -right-20 text-[var(--foreground)] opacity-[0.03]"
        />
      </div>

      {backLabel && (
        <button
          onClick={() => navigate(backTo)}
          className="aos-glass-surface fixed top-4 left-4 sm:top-6 sm:left-6 z-20 flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium text-[var(--muted-foreground)] transition-all hover:text-[var(--foreground)] hover:shadow-md group cursor-pointer focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
          aria-label={backLabel}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:-translate-x-1"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          {backLabel}
        </button>
      )}

      <main id="main-content" className="w-full max-w-md relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
        >
          {children}
        </motion.div>
      </main>
    </motion.div>
  );
};
