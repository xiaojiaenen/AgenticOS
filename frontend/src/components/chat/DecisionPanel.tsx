import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { HelpCircle, Send, ChevronRight } from 'lucide-react';
import { useIsGlassTheme } from '../liquid-glass';
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';
import { cn } from '../../lib/utils';

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
  const isGlass = useIsGlassTheme();
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

  const decisionsContent = decisions.length > 0 ? (
    <>
      <div className={cn("mb-2 flex items-center gap-2", isGlass ? "text-white/70" : "text-slate-700")}>
        <HelpCircle size={17} />
        <span className="text-xs font-black uppercase tracking-[0.16em]">需要你的决策</span>
      </div>
      <div className="flex flex-col gap-3">
        {decisions.map((decision) => (
          <div
            key={decision.decision_id}
            className={cn("flex flex-col gap-3 rounded-2xl px-3 py-3", isGlass ? "bg-white/8" : "border border-white/70 bg-white/76")}
          >
            <div>
              <p className={cn("text-sm font-semibold", isGlass ? "text-white" : "text-slate-800")}>{decision.question}</p>
              {decision.context && (
                <div className={cn("mt-2 max-h-60 overflow-y-auto rounded-lg p-2.5", isGlass ? "bg-white/5" : "border border-slate-200/60 bg-slate-50/50")}>
                  <pre className={cn("whitespace-pre-wrap break-words text-xs leading-relaxed font-mono", isGlass ? "text-white/60" : "text-slate-600")}>{decision.context}</pre>
                </div>
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
                  className={cn("flex-1 rounded-xl border px-3 py-1.5 text-xs outline-none transition-colors focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20", isGlass ? "bg-white/10 border-white/20 text-white placeholder:text-white/40" : "border-slate-200 bg-white")}
                />
                <button
                  type="button"
                  onClick={() => handleSubmitCustom(decision.decision_id)}
                  disabled={!customInputs[decision.decision_id]?.trim()}
                  className={cn("rounded-lg p-1.5 transition-colors disabled:opacity-40", isGlass ? "text-sky-400 hover:bg-white/10" : "text-blue-600 hover:bg-blue-100")}
                  aria-label="发送自定义答案"
                >
                  <Send size={14} />
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
          className={cn("mb-0", isGlass ? "" : "rounded-2xl border border-[var(--border-strong)] bg-[var(--surface-3)] shadow-xl backdrop-blur-2xl px-5 py-4")}
        >
          {isGlass ? (
            <LiquidGlass {...glassPresets.card} tint="rgba(255,255,255,0.08)" radius={16} style={{ width: '100%', padding: '16px' }}>
              {decisionsContent}
            </LiquidGlass>
          ) : (
            <div className="w-full">{decisionsContent}</div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
};
