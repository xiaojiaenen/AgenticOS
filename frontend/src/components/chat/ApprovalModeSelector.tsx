/**
 * 审批模式切换器（输入框内，紧邻智能体选择器）。
 *
 * 三档语义：
 * - ask：需要审批的工具逐次询问
 * - auto：**只读工具自动放行**，写/执行仍逐次确认（推荐）
 * - full：全部自动放行（仅管理员可见且生效）
 */
import React from 'react';
import { ShieldCheck, ShieldQuestion, Zap } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../shadcn/tooltip';

export type ApprovalMode = 'ask' | 'auto' | 'full';

const OPTIONS: {
  value: ApprovalMode;
  label: string;
  hint: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  activeClass: string;
}[] = [
  {
    value: 'ask',
    label: '逐次确认',
    hint: '每个需审批的工具都问你一次',
    icon: ShieldQuestion,
    activeClass: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  },
  {
    value: 'auto',
    label: '只读放行',
    hint: '查询类工具自动执行，写操作仍要你确认',
    icon: ShieldCheck,
    activeClass: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  },
  {
    value: 'full',
    label: '全部放行',
    hint: '所有工具自动执行（仅管理员生效，谨慎使用）',
    icon: Zap,
    activeClass: 'bg-rose-500/15 text-rose-700 dark:text-rose-300',
  },
];

interface ApprovalModeSelectorProps {
  mode: ApprovalMode;
  onChange: (mode: ApprovalMode) => void;
  isAdmin?: boolean;
  disabled?: boolean;
}

export const ApprovalModeSelector: React.FC<ApprovalModeSelectorProps> = ({
  mode,
  onChange,
  isAdmin = false,
  disabled = false,
}) => {
  const options = isAdmin ? OPTIONS : OPTIONS.filter((o) => o.value !== 'full');
  const current = options.find((o) => o.value === mode) ?? options[0];

  return (
    <TooltipProvider delayDuration={250} skipDelayDuration={400}>
      <div
        className={cn(
          'flex items-center gap-0.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] p-0.5',
          disabled && 'opacity-50',
        )}
        role="group"
        aria-label="工具审批模式"
      >
        {options.map(({ value, label, hint, icon: Icon, activeClass }) => {
          const active = mode === value;
          return (
            <Tooltip key={value}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(value)}
                  aria-pressed={active}
                  aria-label={`审批模式：${label}`}
                  className={cn(
                    'flex h-8 items-center gap-1 rounded-full px-2 text-[11px] font-semibold transition-colors',
                    active
                      ? activeClass
                      : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]',
                  )}
                >
                  <Icon size={13} />
                  <span className="hidden lg:inline">{active ? label : label.slice(0, 2)}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" sideOffset={6}>
                {label} —— {hint}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
      <span className="sr-only" aria-live="polite">
        当前审批模式：{current.label}
      </span>
    </TooltipProvider>
  );
};