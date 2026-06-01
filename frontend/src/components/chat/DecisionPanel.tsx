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
          className="mb-3 rounded-3xl border border-blue-200/80 bg-blue-50/85 px-4 py-3 shadow-[0_18px_42px_rgba(59,130,246,0.14)] backdrop-blur-xl"
        >
          <div className="mb-2 flex items-center gap-2 text-blue-900">
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
                  <p className="text-sm font-bold text-slate-800">{decision.question}</p>
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
                      className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-blue-700 active:scale-95"
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
