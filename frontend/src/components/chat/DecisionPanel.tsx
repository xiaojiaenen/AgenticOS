import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { ChevronRight, HelpCircle, Loader2, Send } from 'lucide-react';

export type UserDecision = {
  decision_id: string;
  question: string;
  options: string[];
  context?: string;
  allow_custom?: boolean;
};

export function normalizeDecision(raw: unknown): UserDecision | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Record<string, unknown>;
  if (typeof d.decision_id !== 'string' || typeof d.question !== 'string') return null;
  // options 可能是 JSON 字符串、逗号分隔字符串或非数组，统一处理
  let options: string[] = [];
  if (Array.isArray(d.options)) {
    options = d.options.filter((o): o is string => typeof o === 'string');
  } else if (typeof d.options === 'string') {
    // 先尝试 JSON 解析
    try {
      const parsed = JSON.parse(d.options);
      if (Array.isArray(parsed)) {
        options = parsed.filter((o): o is string => typeof o === 'string');
      }
    } catch {
      // JSON 解析失败，尝试逗号分隔
      options = d.options.split(',').map((s: string) => s.trim()).filter(Boolean);
    }
  }
  // 注意：不再因 options < 2 丢弃决策。后端工具会阻塞等待该 decision，
  // 静默丢弃等于 Agent 永久挂起且用户看不到任何面板；选项不足时由 UI
  // 降级为"仅自定义回答"。
  return {
    decision_id: d.decision_id,
    question: d.question,
    options,
    context: typeof d.context === 'string' ? d.context : undefined,
    allow_custom: d.allow_custom !== false,
  };
}

type DecisionPanelProps = {
  decisions: UserDecision[];
  onDecision: (decisionId: string, answer: string) => void;
};

export const DecisionPanel: React.FC<DecisionPanelProps> = ({ decisions, onDecision }) => {
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});
  // 提交中的决策：点击后立刻禁用，避免连点把同一个 decision 提交多遍
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const alive = new Set(decisions.map((d) => d.decision_id));
    setSubmitting((prev) => {
      const next: Record<string, boolean> = {};
      let changed = false;
      for (const [id, value] of Object.entries(prev)) {
        if (alive.has(id)) next[id] = value;
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [decisions]);

  const answer = (decisionId: string, value: string) => {
    if (submitting[decisionId]) return;
    setSubmitting((prev) => ({ ...prev, [decisionId]: true }));
    onDecision(decisionId, value);
  };

  const handleCustomInput = (decisionId: string, value: string) => {
    setCustomInputs((prev) => ({ ...prev, [decisionId]: value }));
  };

  const handleSubmitCustom = (decisionId: string) => {
    const value = customInputs[decisionId]?.trim();
    if (value) {
      answer(decisionId, value);
      setCustomInputs((prev) => {
        const next = { ...prev };
        delete next[decisionId];
        return next;
      });
    }
  };

  const decisionsContent = decisions.length > 0 ? (
    <>
      <div className={cn("mb-2 flex items-center gap-2", "text-[var(--muted-foreground)]")}>
        <HelpCircle size={17} />
        <span className="text-xs font-semibold uppercase tracking-[0.16em]">需要你的决策</span>
      </div>
      <div className="flex flex-col gap-3">
        {decisions.map((decision) => (
          <div
            key={decision.decision_id}
            className={cn("flex flex-col gap-3 rounded-2xl px-3 py-3", "border border-[var(--border-subtle)] bg-[var(--surface-1)]")}
          >
            <div>
              <p className={cn("text-sm font-semibold", "text-[var(--foreground)]")}>{decision.question}</p>
              {decision.context && (
                <div className={cn("mt-2 max-h-60 overflow-y-auto rounded-lg p-2.5", "border border-[var(--border-subtle)] bg-[var(--surface-2)]")}>
                  <pre className={cn("whitespace-pre-wrap break-words text-xs leading-relaxed font-mono", "text-[var(--muted-foreground)]")}>{decision.context}</pre>
                </div>
              )}
            </div>

            {decision.options.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {decision.options.map((option, idx) => {
                  const pending = Boolean(submitting[decision.decision_id]);
                  return (
                    <button
                      key={idx}
                      type="button"
                      disabled={pending}
                      onClick={() => answer(decision.decision_id, option)}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60',
                        'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
                      )}
                    >
                      {pending ? <Loader2 size={12} className="animate-spin" /> : <ChevronRight size={12} />}
                      {option}
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-[var(--muted-foreground)]">
                该决策未提供预设选项，请在下方输入你的回答。
              </p>
            )}

            {decision.allow_custom !== false && (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="或输入自定义答案..."
                  aria-label={`自定义回答：${decision.question}`}
                  disabled={Boolean(submitting[decision.decision_id])}
                  value={customInputs[decision.decision_id] || ''}
                  onChange={(e) => handleCustomInput(decision.decision_id, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSubmitCustom(decision.decision_id);
                  }}
                  className={cn("flex-1 rounded-xl border px-3 py-1.5 text-xs outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] disabled:opacity-60", "border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]")}
                />
                <button
                  type="button"
                  onClick={() => handleSubmitCustom(decision.decision_id)}
                  disabled={!customInputs[decision.decision_id]?.trim() || submitting[decision.decision_id]}
                  className={cn("rounded-lg p-1.5 transition-colors disabled:opacity-40", "text-[var(--foreground)] hover:bg-[var(--surface-2)]")}
                  aria-label="发送自定义答案"
                >
                  {submitting[decision.decision_id] ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Send size={14} />
                  )}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  ) : null;

  return (
    <AnimatePresence>
      {decisions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          className={cn("mb-0", "rounded-2xl border border-[var(--border-strong)] bg-[var(--surface-3)] shadow-xl backdrop-blur-2xl px-5 py-4")}
        >
          <div className="w-full">{decisionsContent}</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
