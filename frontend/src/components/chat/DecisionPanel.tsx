import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { HelpCircle, Send, ChevronRight } from 'lucide-react';

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
  if (options.length < 2) return null;
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

  const handleCustomInput = (decisionId: string, value: string) => {
    setCustomInputs((prev) => ({ ...prev, [decisionId]: value }));
  };

  const handleSubmitCustom = (decisionId: string) => {
    const value = customInputs[decisionId]?.trim();
    if (value) {
      onDecision(decisionId, value);
      setCustomInputs((prev) => {
        const next = { ...prev };
        delete next[decisionId];
        return next;
      });
    }
  };

  return (
    <AnimatePresence>
      {decisions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          className="mb-0 rounded-2xl border border-[var(--border-strong)] bg-[var(--surface-3)] shadow-xl backdrop-blur-2xl px-5 py-4"
        >
          <div className="mb-2 flex items-center gap-2 text-slate-700">
            <HelpCircle size={17} />
            <span className="text-xs font-black uppercase tracking-[0.16em]">需要你的决策</span>
          </div>
          <div className="flex flex-col gap-3">
            {decisions.map((decision) => (
              <div
                key={decision.decision_id}
                className="flex flex-col gap-3 rounded-2xl border border-white/70 bg-white/76 px-3 py-3"
              >
                <div>
                  <p className="text-sm font-semibold text-slate-800">{decision.question}</p>
                  {decision.context && (
                    <p className="mt-1 text-xs text-slate-500">{decision.context}</p>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  {decision.options.map((option, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => onDecision(decision.decision_id, option)}
                      className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent-send)] px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-[var(--accent-send-hover)] active:scale-95"
                    >
                      <ChevronRight size={12} />
                      {option}
                    </button>
                  ))}
                </div>

                {decision.allow_custom !== false && (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      placeholder="或输入自定义答案..."
                      value={customInputs[decision.decision_id] || ''}
                      onChange={(e) => handleCustomInput(decision.decision_id, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSubmitCustom(decision.decision_id);
                      }}
                      className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                    />
                    <button
                      type="button"
                      onClick={() => handleSubmitCustom(decision.decision_id)}
                      disabled={!customInputs[decision.decision_id]?.trim()}
                      className="rounded-lg p-1.5 text-blue-600 transition-colors hover:bg-blue-100 disabled:opacity-40"
                      aria-label="发送自定义答案"
                    >
                      <Send size={14} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
