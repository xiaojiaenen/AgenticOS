import React from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { RandomMascot } from '../ui/RandomMascot';
import { AuroraBackground } from '../backgrounds/AuroraBackground';

interface AuthShellProps {
  /** 返回按钮文案与目标；不传则不渲染返回按钮 */
  backLabel?: string;
  backTo?: string;
  children: React.ReactNode;
}

/**
 * 登录/注册共用页面壳：极光背景 + 角落吉祥物水印 + 返回按钮 + 居中卡片槽位。
 * 之前两页各复制一份（类名还有细微漂移），改样式要改两处 —— 收敛到这里。
 *
 * 注意根节点 initial={false}：整页可见性不依赖 motion 入场，
 * 防止 AnimatePresence(mode=wait) + 懒加载竞态把页面卡在 opacity:0（白屏）。
 */
export const AuthShell: React.FC<AuthShellProps> = ({ backLabel, backTo = '/', children }) => {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={false}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      className="relative min-h-screen overflow-hidden bg-[var(--surface-0)] flex items-center justify-center p-4"
    >
      <AuroraBackground className="fixed" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <RandomMascot
          size={400}
          className="absolute -bottom-20 -right-20 text-[var(--foreground)] opacity-[0.03]"
        />
      </div>

      {backLabel && (
        <button
          onClick={() => navigate(backTo)}
          className="fixed top-4 left-4 sm:top-6 sm:left-6 z-20 flex items-center gap-2 px-4 py-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 text-sm font-medium text-[var(--muted-foreground)] shadow-sm transition-all hover:border-[var(--border-strong)] hover:text-[var(--foreground)] hover:shadow-md group focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
          aria-label={backLabel}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:-translate-x-1"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          {backLabel}
        </button>
      )}

      <main id="main-content" className="w-full max-w-md relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          {children}
        </motion.div>
      </main>
    </motion.div>
  );
};
