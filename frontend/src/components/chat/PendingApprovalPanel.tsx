import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, Loader2, ShieldAlert, X } from 'lucide-react';
import { ToolCall } from '../../types';

type PendingApprovalPanelProps = {
  approvals: ToolCall[];
  onDecision: (approvalId: string, status: 'approved' | 'rejected', isApiApproval?: boolean, allowAll?: boolean) => void;
};

/**
 * 待审批工具调用面板。
 *
 * 两个刻意的设计：
 * 1. **提交后立刻进入 pending 态**。审批是本产品风险最高的一次点击，
 *    原来没有 loading / disabled，用户可以连点「批准」多次，把同一个
 *    approvalId 提交多遍 —— 后端每次都当成新决策处理。
 * 2. **approvalId 缺失时不再静默丢弃**。原来的 `return null` 会让这条待审批
 *    从界面上消失，用户既看不到也点不掉，只能干等。改成显示一条「无法提交」
 *    的说明，至少让人知道流程卡在哪。
 */
export const PendingApprovalPanel: React.FC<PendingApprovalPanelProps> = ({ approvals, onDecision }) => {
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});

  // 审批项消失（已处理）时清掉 pending，避免状态残留
  useEffect(() => {
    const alive = new Set(approvals.map((a) => a.approvalId).filter(Boolean) as string[]);
    setSubmitting((prev) => {
      const next: Record<string, boolean> = {};
      let changed = false;
      for (const [id, value] of Object.entries(prev)) {
        if (alive.has(id)) next[id] = value;
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [approvals]);

  const decide = (approvalId: string, status: 'approved' | 'rejected', isApiApproval?: boolean, allowAll?: boolean) => {
    if (submitting[approvalId]) return;
    setSubmitting((prev) => ({ ...prev, [approvalId]: true }));
    onDecision(approvalId, status, isApiApproval, allowAll);
  };

  return (
    <AnimatePresence>
      {approvals.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          className="mb-3 rounded-3xl border border-amber-300/70 bg-amber-50/85 px-4 py-3 shadow-[0_18px_42px_rgba(180,83,9,0.14)] backdrop-blur-xl dark:border-amber-500/40 dark:bg-amber-500/10 dark:shadow-none"
        >
          <div className="mb-2 flex items-center gap-2 text-amber-900 dark:text-amber-200">
            <ShieldAlert size={17} />
            <span className="text-xs font-semibold uppercase tracking-[0.16em]">需要审批的工具调用</span>
          </div>
          <div className="flex flex-col gap-2">
            {approvals.map((approval, index) => {
              const approvalId = approval.approvalId;
              const pending = approvalId ? Boolean(submitting[approvalId]) : false;

              // 没有 approvalId 就无法提交决策：明确说出来，而不是静默消失
              if (!approvalId) {
                return (
                  <div
                    key={`unaddressable-${approval.id ?? index}`}
                    className="flex flex-col gap-1 rounded-2xl border border-dashed border-amber-300/70 bg-[var(--surface-1)]/85 px-3 py-3"
                  >
                    <div className="truncate font-mono text-xs font-medium text-[var(--foreground)]">
                      {approval.name}
                    </div>
                    <p className="text-[11px] text-amber-800 dark:text-amber-200">
                      这条审批缺少标识，无法提交决策。刷新页面可重新发起。
                    </p>
                  </div>
                );
              }

              const buttonBase =
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors active:scale-95 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] disabled:cursor-not-allowed disabled:opacity-60';

              return (
                <div
                  key={approvalId}
                  className="flex flex-col gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/85 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="truncate font-mono text-xs font-medium text-[var(--foreground)]">{approval.name}</div>
                    <div className="mt-1 max-w-xl truncate text-[11px] text-[var(--muted-foreground)]">
                      {approval.result || '等待你确认后继续执行。'}
                    </div>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    {approval.isApiApproval && (
                      <button
                        type="button"
                        disabled={pending}
                        onClick={() => decide(approvalId, 'approved', true, true)}
                        className={`${buttonBase} bg-emerald-600 text-white hover:bg-emerald-700 focus-visible:ring-emerald-400`}
                        aria-label="本次会话全部允许"
                      >
                        {pending ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                        全部允许
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => decide(approvalId, 'approved', approval.isApiApproval)}
                      className={`${buttonBase} bg-[var(--primary)] text-[var(--primary-foreground)] hover:bg-[var(--primary)]/90 focus-visible:ring-[var(--ring)]`}
                      aria-label="批准工具调用"
                    >
                      {pending ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                      批准
                    </button>
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => decide(approvalId, 'rejected', approval.isApiApproval)}
                      className={`${buttonBase} border border-rose-200 bg-[var(--surface-1)] text-rose-600 hover:bg-rose-50 focus-visible:ring-rose-300 dark:border-rose-500/40 dark:hover:bg-rose-500/15`}
                      aria-label="拒绝工具调用"
                    >
                      {pending ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />}
                      拒绝
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
