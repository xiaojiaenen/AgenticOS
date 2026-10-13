/**
 * 执行策略入口：把「审批档位」与「计划模式」合并到一个按钮里。
 *
 * 之前输入框里有独立的审批三档 + 计划模式两个控件，加上附件/智能体/
 * 润色/发送共 6 个，视觉噪音大且两者本质都是"这轮怎么执行"的设置，
 * 因此合并为一个入口：按钮上直接显示当前状态，展开后可切换。
 */
import React from 'react';
import { Check, ClipboardList, ShieldCheck, ShieldQuestion, Zap } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '../shadcn/popover';

export type ApprovalMode = 'ask' | 'auto' | 'full';

const APPROVAL_OPTIONS: {
  value: ApprovalMode;
  label: string;
  hint: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}[] = [
  {
    value: 'ask',
    label: '逐次确认',
    hint: '需要审批的工具每次都问你',
    icon: ShieldQuestion,
  },
  {
    value: 'auto',
    label: '只读放行',
    hint: '查询类工具自动执行，写操作仍确认',
    icon: ShieldCheck,
  },
  {
    value: 'full',
    label: '全部放行',
    hint: '所有工具自动执行（仅管理员生效）',
    icon: Zap,
  },
];

export const ExecutionPolicyMenu: React.FC<{
  approvalMode: ApprovalMode;
  onApprovalModeChange: (mode: ApprovalMode) => void;
  planMode: boolean;
  onPlanModeChange: (on: boolean) => void;
  isAdmin?: boolean;
  disabled?: boolean;
}> = ({
  approvalMode,
  onApprovalModeChange,
  planMode,
  onPlanModeChange,
  isAdmin = false,
  disabled = false,
}) => {
  const options = isAdmin ? APPROVAL_OPTIONS : APPROVAL_OPTIONS.filter((o) => o.value !== 'full');
  const current = options.find((o) => o.value === approvalMode) ?? options[0];
  const Icon = planMode ? ClipboardList : current.icon;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label={`执行策略：${planMode ? '计划模式' : current.label}`}
          className={cn(
            'flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold transition-all active:scale-95',
            planMode
              ? 'border-sky-500 bg-sky-500/15 text-sky-700 dark:text-sky-300'
              : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
            disabled && 'opacity-50',
          )}
        >
          <Icon size={14} />
          <span className="hidden lg:inline">{planMode ? '计划' : current.label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" sideOffset={8} className="w-72 p-3">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
          审批档位
        </p>
        <div className="space-y-1">
          {options.map((option) => {
            const active = !planMode && approvalMode === option.value;
            const OptionIcon = option.icon;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onApprovalModeChange(option.value)}
                className={cn(
                  'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors',
                  active ? 'bg-brand-500/10' : 'hover:bg-[var(--surface-2)]',
                )}
              >
                <OptionIcon size={14} className="mt-0.5 shrink-0 text-[var(--muted-foreground)]" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-[var(--foreground)]">
                    {option.label}
                    {active && <Check size={11} className="text-brand-600" />}
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    {option.hint}
                  </span>
                </span>
              </button>
            );
          })}
        </div>

        <div className="my-3 h-px bg-[var(--border-subtle)]" />

        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
          计划模式
        </p>
        <button
          type="button"
          onClick={() => onPlanModeChange(!planMode)}
          className={cn(
            'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors',
            planMode ? 'bg-sky-500/10' : 'hover:bg-[var(--surface-2)]',
          )}
        >
          <ClipboardList
            size={14}
            className={cn(
              'mt-0.5 shrink-0',
              planMode ? 'text-sky-600' : 'text-[var(--muted-foreground)]',
            )}
          />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-[var(--foreground)]">
              先出计划再执行
              {planMode && <Check size={11} className="text-sky-600" />}
            </span>
            <span className="mt-0.5 block text-[11px] leading-relaxed text-[var(--muted-foreground)]">
              Agent 只做只读调研并输出计划，批准后才动手
            </span>
          </span>
        </button>
      </PopoverContent>
    </Popover>
  );
};