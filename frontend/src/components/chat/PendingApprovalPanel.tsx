import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, Loader2, MessageSquarePlus, Pencil, ShieldAlert, X } from 'lucide-react';
import { ToolCall } from '../../types';

type ApprovalDecisionStatus = 'approved' | 'rejected' | 'respond';

type PendingApprovalPanelProps = {
  approvals: ToolCall[];
  /**
   * 决策回调。第 5 参按调用类型二选一：
   * - status=respond 时是 response（人工代答文本，战线 A3）
   * - status=approved 且用户编辑过参数时是 modifiedArguments 的 JSON 字符串
   *   （战线 3G.1：改参=edit 决策；后端 ApprovalManager 写入 modified_arguments）
   */
  onDecision: (approvalId: string, status: ApprovalDecisionStatus, isApiApproval?: boolean, allowAll?: boolean, payload?: string) => void;
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
 *
 * 3. **改参（edit 决策）**：参数是 JSON 时展示「改参数」入口，展开一个
 *    JSON 文本域；编辑后的 JSON 作为 modified_arguments 提交，工具按改后
 *    参数执行（后端 EngineApprovalPolicy → ApprovalOutcome(arguments=modified)）。
 *    JSON 解析失败时禁止提交并提示 —— 与 EmailPreviewPanel 的专用改参 UI
 *    等价，但面向任意工具参数。
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

  const [respondDraft, setRespondDraft] = useState<Record<string, string>>({});
  // 改参编辑态：approvalId → { open, draft, parsed, error }
  const [editState, setEditState] = useState<Record<string, { open: boolean; draft: string; parsed: Record<string, unknown> | null; error: string | null }>>({});

  const getEdit = (approvalId: string) =>
    editState[approvalId] ?? { open: false, draft: '', parsed: null, error: null };

  const setEdit = (
    approvalId: string,
    patch: Partial<{ open: boolean; draft: string; parsed: Record<string, unknown> | null; error: string | null }>,
  ) => {
    setEditState((prev) => ({ ...prev, [approvalId]: { ...getEdit(approvalId), ...patch } }));
  };

  /** 从工具调用的 result 字段提取当前参数 JSON（后端下发的是 arguments 的格式化 JSON）。 */
  const argsJsonOf = (approval: ToolCall): string | null => {
    const raw = approval.result;
    if (!raw || typeof raw !== 'string') return null;
    const trimmed = raw.trim();
    if (!trimmed.startsWith('{')) return null;
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return JSON.stringify(parsed, null, 2);
      }
    } catch {
      /* 不是 JSON 参数（如说明文案），不提供改参入口 */
    }
    return null;
  };

  const decide = (
    approvalId: string,
    status: ApprovalDecisionStatus,
    isApiApproval?: boolean,
    allowAll?: boolean,
    payload?: string,
  ) => {
    if (submitting[approvalId]) return;
    if (status === 'respond' && !(respondDraft[approvalId] || '').trim()) return;
    setSubmitting((prev) => ({ ...prev, [approvalId]: true }));
    onDecision(approvalId, status, isApiApproval, allowAll, payload);
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

              const edit = getEdit(approvalId);
              const editableJson = argsJsonOf(approval);
              const hasEdits = edit.parsed != null;

              const buttonBase =
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors active:scale-95 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] disabled:cursor-not-allowed disabled:opacity-60';

              return (
                <div
                  key={approvalId}
                  className="flex flex-col gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/85 px-3 py-3"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs font-medium text-[var(--foreground)]">{approval.name}</div>
                      <div className="mt-1 max-w-xl truncate text-[11px] text-[var(--muted-foreground)]">
                        {approval.result || '等待你确认后继续执行。'}
                      </div>
                    </div>
                    <div className="flex flex-shrink-0 flex-wrap items-center gap-2">
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
                      {editableJson && !edit.open && (
                        <button
                          type="button"
                          disabled={pending}
                          onClick={() => setEdit(approvalId, { open: true, draft: editableJson, parsed: null, error: null })}
                          className={`${buttonBase} border border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--foreground)] hover:bg-[var(--surface-3)]`}
                          aria-label="修改工具参数"
                        >
                          <Pencil size={13} />
                          改参数
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={pending}
                        onClick={() =>
                          decide(
                            approvalId,
                            'approved',
                            approval.isApiApproval,
                            undefined,
                            hasEdits && edit.parsed ? JSON.stringify(edit.parsed) : undefined,
                          )
                        }
                        className={`${buttonBase} bg-[var(--primary)] text-[var(--primary-foreground)] hover:bg-[var(--primary)]/90 focus-visible:ring-[var(--ring)]`}
                        aria-label={hasEdits ? '按修改后的参数批准' : '批准工具调用'}
                      >
                        {pending ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                        {hasEdits ? '按新参数批准' : '批准'}
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

                  {/* 改参编辑区（3G.1：edit 决策的通用 UI；JSON 校验不过禁止提交） */}
                  {edit.open && (
                    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/60 p-2.5">
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
                          修改参数（JSON）—— 留空错误时「按新参数批准」才可用
                        </span>
                        <button
                          type="button"
                          onClick={() => setEdit(approvalId, { open: false, parsed: null, error: null })}
                          className="text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                          aria-label="取消修改参数"
                        >
                          取消修改
                        </button>
                      </div>
                      <textarea
                        value={edit.draft}
                        onChange={(e) => {
                          const draft = e.target.value;
                          // 实时校验：合法 JSON → parsed（「按新参数批准」立即可用）；
                          // 非法 → error 提示且按钮保持禁用语义（hasEdits=false）
                          try {
                            const parsed = JSON.parse(draft);
                            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                              setEdit(approvalId, { draft, parsed: parsed as Record<string, unknown>, error: null });
                              return;
                            }
                            setEdit(approvalId, { draft, parsed: null, error: '参数必须是 JSON 对象' });
                          } catch {
                            setEdit(approvalId, { draft, parsed: null, error: 'JSON 语法错误' });
                          }
                        }}
                        rows={Math.min(10, Math.max(3, edit.draft.split('\n').length))}
                        spellCheck={false}
                        className="w-full resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-2.5 py-2 font-mono text-[11px] leading-relaxed text-[var(--foreground)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-halo)]"
                        aria-label="工具参数 JSON"
                      />
                      {edit.error && (
                        <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-400">{edit.error}</p>
                      )}
                    </div>
                  )}

                  {/* 人工代答（战线 A3，DeepAgents respond 决策）：工具不执行，
                      用户答案作为工具结果回灌给模型。放底部独立一行。 */}
                  <div className="flex items-center gap-2 border-t border-[var(--border-subtle)] pt-2">
                    <input
                      type="text"
                      value={respondDraft[approvalId] ?? ''}
                      onChange={(e) => setRespondDraft((prev) => ({ ...prev, [approvalId]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') decide(approvalId, 'respond', approval.isApiApproval, false, respondDraft[approvalId]);
                      }}
                      placeholder="或直接代答（工具不再执行，答案回传给 AI）…"
                      className="min-w-0 flex-1 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-1.5 text-[11px] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-halo)]"
                    />
                    <button
                      type="button"
                      disabled={pending || !(respondDraft[approvalId] || '').trim()}
                      onClick={() => decide(approvalId, 'respond', approval.isApiApproval, false, respondDraft[approvalId])}
                      className={`${buttonBase} border border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--foreground)] hover:bg-[var(--surface-3)] disabled:opacity-50`}
                      aria-label="人工代答"
                    >
                      {pending ? <Loader2 size={13} className="animate-spin" /> : <MessageSquarePlus size={13} />}
                      代答
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
