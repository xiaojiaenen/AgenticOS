import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, ShieldAlert, X } from 'lucide-react';
import { ToolCall } from '../../types';

type PendingApprovalPanelProps = {
  approvals: ToolCall[];
  onDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
};

export const PendingApprovalPanel: React.FC<PendingApprovalPanelProps> = ({ approvals, onDecision }) => {
  return (
    <AnimatePresence>
      {approvals.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          className="mb-3 rounded-[1.35rem] border border-amber-200/80 bg-amber-50/85 px-4 py-3 shadow-[0_18px_42px_rgba(180,83,9,0.14)] backdrop-blur-xl"
        >
          <div className="mb-2 flex items-center gap-2 text-amber-900">
            <ShieldAlert size={17} />
            <span className="text-xs font-black uppercase tracking-[0.16em]">需要审批的工具调用</span>
          </div>
          <div className="flex flex-col gap-2">
            {approvals.map((approval) => (
              <div
                key={approval.approvalId}
                className="flex flex-col gap-3 rounded-2xl border border-white/70 bg-white/76 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs font-bold text-zinc-900">{approval.name}</div>
                  <div className="mt-1 max-w-xl truncate text-[11px] text-slate-500">
                    {approval.result || '等待你确认后继续执行。'}
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onDecision(approval.approvalId!, 'approved')}
                    className="inline-flex items-center gap-1.5 rounded-full bg-zinc-900 px-3 py-1.5 text-[11px] font-bold text-white transition-colors hover:bg-zinc-800 active:scale-95"
                  >
                    <Check size={13} />
                    批准
                  </button>
                  <button
                    type="button"
                    onClick={() => onDecision(approval.approvalId!, 'rejected')}
                    className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-white px-3 py-1.5 text-[11px] font-bold text-rose-600 transition-colors hover:bg-rose-50 active:scale-95"
                  >
                    <X size={13} />
                    拒绝
                  </button>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
