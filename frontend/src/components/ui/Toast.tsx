import React, { useEffect, useState, useCallback, useId } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';

type ToastVariant = 'success' | 'error' | 'warning' | 'info';

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
  duration?: number;
}

let toastId = 0;
const listeners = new Set<(toasts: ToastItem[]) => void>();
let currentToasts: ToastItem[] = [];

function notify() {
  listeners.forEach((fn) => fn([...currentToasts]));
}

export function toast(message: string, options?: { variant?: ToastVariant; duration?: number }): number {
  toastId += 1;
  const item: ToastItem = {
    id: toastId,
    message,
    variant: options?.variant || 'info',
    duration: options?.duration ?? 4000,
  };
  currentToasts = [...currentToasts, item];
  notify();
  return item.id;
}

export function dismissToast(id: number) {
  currentToasts = currentToasts.filter((t) => t.id !== id);
  notify();
}

const variantStyles: Record<ToastVariant, { bg: string; border: string; text: string; icon: string }> = {
  success: {
    bg: 'bg-emerald-50/95',
    border: 'border-emerald-200',
    text: 'text-emerald-800',
    icon: 'text-emerald-500',
  },
  error: {
    bg: 'bg-rose-50/95',
    border: 'border-rose-200',
    text: 'text-rose-800',
    icon: 'text-rose-500',
  },
  warning: {
    bg: 'bg-amber-50/95',
    border: 'border-amber-200',
    text: 'text-amber-800',
    icon: 'text-amber-500',
  },
  info: {
    bg: 'bg-brand-50/95',
    border: 'border-brand-200',
    text: 'text-brand-800',
    icon: 'text-brand-500',
  },
};

const variantIcons: Record<ToastVariant, React.ReactNode> = {
  success: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
    </svg>
  ),
  error: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
    </svg>
  ),
  warning: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  info: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
  ),
};

function useAutoDismiss(toasts: ToastItem[], onDismiss: (id: number) => void) {
  useEffect(() => {
    const timers = toasts.map((item) =>
      setTimeout(() => onDismiss(item.id), item.duration ?? 4000)
    );
    return () => timers.forEach(clearTimeout);
  }, [toasts, onDismiss]);
}

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const alertId = useId();

  useEffect(() => {
    const handler = (next: ToastItem[]) => setToasts(next);
    listeners.add(handler);
    return () => { listeners.delete(handler); };
  }, []);

  const dismiss = useCallback((id: number) => {
    dismissToast(id);
  }, []);

  useAutoDismiss(toasts, dismiss);

  return (
    <div className="fixed bottom-6 right-6 z-[999] flex flex-col-reverse gap-3 pointer-events-none" aria-live="polite">
      <AnimatePresence>
        {toasts.map((item) => {
          const style = variantStyles[item.variant];
          return (
            <motion.div
              key={item.id}
              role="alert"
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 50, scale: 0.96 }}
              className={cn(
                'pointer-events-auto flex items-center gap-3 rounded-2xl border px-5 py-3.5 shadow-lg backdrop-blur-xl max-w-[380px]',
                style.bg, style.border,
              )}
            >
              <span className={cn('flex-shrink-0', style.icon)}>
                {variantIcons[item.variant]}
              </span>
              <p className={cn('text-sm font-bold break-words min-w-0', style.text)}>{item.message}</p>
              <button
                onClick={() => dismiss(item.id)}
                className={cn('ml-2 flex-shrink-0 rounded-lg p-1 transition-colors hover:bg-black/5', style.text)}
                aria-label="关闭通知"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
};
