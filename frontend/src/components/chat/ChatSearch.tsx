import React, { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';

interface ChatSearchProps {
  showSearch: boolean;
  searchQuery: string;
  setSearchQuery: (val: string) => void;
  searchCurrentIndex: number;
  searchMatchesCount: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}

export const ChatSearch: React.FC<ChatSearchProps> = ({
  showSearch,
  searchQuery,
  setSearchQuery,
  searchCurrentIndex,
  searchMatchesCount,
  onPrev,
  onNext,
  onClose
}) => {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // Esc 关闭搜索浮层；匹配数通过 aria-live 播报给读屏用户
  useEffect(() => {
    if (!showSearch) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeRef.current();
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [showSearch]);

  const hasMatches = searchMatchesCount > 0;

  return (
    <AnimatePresence>
      {showSearch && (
        <motion.div
          initial={{ opacity: 0, y: -20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -20, scale: 0.95 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="fixed inset-0 z-50 flex justify-center items-start w-full px-4 pt-4"
          onMouseDown={(e) => {
            // 点击浮层外的空白区域收起搜索
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            initial={{ y: -12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -12, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1], delay: 0.04 }}
            className="w-full max-w-lg"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="bg-[var(--surface-1)] backdrop-blur-3xl border border-[var(--border-subtle)] shadow-2xl shadow-black/10 rounded-[2rem] px-6 py-2 flex items-center gap-3 w-full focus-within:ring-[3px] focus-within:ring-[var(--ring-halo)] transition-all">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--muted-foreground)]" aria-hidden="true">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
              </svg>
              <input
                autoFocus
                type="text"
                placeholder="在当前会话中搜索..."
                className="bg-transparent border-none outline-none w-full text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] font-medium py-2"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="搜索当前会话消息"
              />

              {searchQuery && (
                <div className="flex items-center gap-2 pr-2 border-r border-[var(--border-subtle)] mr-2">
                  <span
                    className="text-[10px] font-semibold bg-[var(--surface-2)] text-[var(--muted-foreground)] px-2.5 py-1 rounded-lg tabular-nums whitespace-nowrap"
                    aria-live="polite"
                  >
                    {searchMatchesCount > 0 ? `${searchCurrentIndex} / ${searchMatchesCount}` : '无匹配'}
                  </span>
                  <div className="flex items-center">
                    <button
                      onClick={onPrev}
                      disabled={!hasMatches}
                      className="p-1.5 hover:bg-[var(--surface-2)] rounded-lg text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      title="上一个"
                      aria-label="上一个匹配"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="rotate-180" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
                    </button>
                    <button
                      onClick={onNext}
                      disabled={!hasMatches}
                      className="p-1.5 hover:bg-[var(--surface-2)] rounded-lg text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      title="下一个"
                      aria-label="下一个匹配"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
                    </button>
                  </div>
                </div>
              )}

              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="p-1 hover:bg-[var(--surface-2)] rounded-full text-[var(--muted-foreground)]"
                  aria-label="清除搜索"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              )}
              <button
                onClick={onClose}
                className="text-xs font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] px-3 py-1 bg-[var(--surface-2)] hover:bg-[var(--surface-1)] rounded-full transition-colors whitespace-nowrap"
                aria-label="关闭搜索"
              >
                取消
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
