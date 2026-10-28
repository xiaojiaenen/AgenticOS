import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { AlertCircle, Loader2, Send } from 'lucide-react';
import type { UserInputRequest } from '../../services/agentService';
import { cn } from '../../lib/utils';

interface UserInputPanelProps {
  request: UserInputRequest | null;
  onSubmit: (values: Record<string, string>) => Promise<void>;
  onDismiss: () => void;
}

export const UserInputPanel = ({ request, onSubmit, onDismiss }: UserInputPanelProps) => {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLFormElement>(null);
  const dismissRef = useRef<() => void>(onDismiss);
  dismissRef.current = onDismiss;

  // 打开时聚焦第一个输入框；Esc 忽略；字段过多时限制高度内部滚动，
  // 避免浮层无限向上膨胀遮挡整个消息流
  useEffect(() => {
    if (!request) return;
    const firstField = panelRef.current?.querySelector<HTMLInputElement>('input:not([type="hidden"])');
    firstField?.focus();
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        dismissRef.current();
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [request]);

  if (!request) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 检查必填字段
    const missing = request.fields.filter(f => f.required && !values[f.key]?.trim());
    if (missing.length > 0) {
      setError(`请填写必填字段：${missing.map(f => f.label || f.key).join('、')}`);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const setField = (key: string, value: string) => {
    setValues(prev => ({ ...prev, [key]: value }));
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="max-h-[60dvh] overflow-y-auto rounded-xl border border-[var(--border-medium)] bg-[var(--surface-3)] p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-[var(--foreground)]">
            需要输入参数
          </p>
          <p className="mt-0.5 text-xs font-medium text-[var(--muted-foreground)]">
            {request.api_display_name || request.api_name}
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-lg px-2.5 py-1 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          忽略
        </button>
      </div>

      {request.message && (
        <p className="mb-3 text-xs font-medium text-[var(--muted-foreground)]">{request.message}</p>
      )}

      <form ref={panelRef} onSubmit={handleSubmit} className="space-y-2.5">
        {request.fields.map((field) => (
          <div key={field.key}>
            <label className="mb-1 block text-xs font-medium text-[var(--muted-foreground)]">
              {field.label || field.key}
              {field.required && <span className="ml-0.5 text-rose-500">*</span>}
            </label>
            {field.type === 'password' ? (
              <input
                type="password"
                value={values[field.key] || ''}
                onChange={(e) => setField(field.key, e.target.value)}
                placeholder={field.description || `输入${field.label || field.key}`}
                className="admin-input w-full text-sm"
                autoComplete="off"
              />
            ) : (
              <input
                type="text"
                value={values[field.key] || ''}
                onChange={(e) => setField(field.key, e.target.value)}
                placeholder={field.description || `输入${field.label || field.key}`}
                className="admin-input w-full text-sm"
              />
            )}
          </div>
        ))}

        {error && (
          <div role="alert" className="flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700 dark:bg-red-500/10 dark:text-red-300">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-all active:scale-[0.98] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]",
            submitting
              ? "bg-[var(--primary)] opacity-60 text-[var(--primary-foreground)]"
              : "bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90"
          )}
        >
          {submitting ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Send size={16} />
          )}
          提交
        </button>
      </form>
    </motion.div>
  );
};
