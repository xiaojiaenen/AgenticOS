import React, { useState } from 'react';
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
      className="rounded-xl border border-sky-200/80 bg-sky-50 p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-sky-800">
            需要输入参数
          </p>
          <p className="mt-0.5 text-xs font-medium text-sky-600">
            {request.api_display_name || request.api_name}
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-lg px-2.5 py-1 text-xs font-medium text-sky-600 transition-colors hover:bg-sky-100"
        >
          忽略
        </button>
      </div>

      {request.message && (
        <p className="mb-3 text-xs font-medium text-sky-700">{request.message}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-2.5">
        {request.fields.map((field) => (
          <div key={field.key}>
            <label className="mb-1 block text-xs font-medium text-sky-700">
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
          <div className="flex items-center gap-1.5 rounded-lg bg-rose-50 px-3 py-2 text-xs font-medium text-rose-600">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white transition-all active:scale-[0.98]",
            submitting ? "bg-sky-400" : "bg-sky-500 hover:bg-sky-600"
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
