/**
 * 计划模式开关：开启后 Agent 只做只读调研并产出计划，
 * 用户批准后才执行写/部署等操作。借鉴 Open WebUI 的 Plan mode。
 */
import React from 'react';
import { ClipboardList } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../shadcn/tooltip';

export const PlanModeToggle: React.FC<{
  enabled: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
}> = ({ enabled, onChange, disabled = false }) => (
  <TooltipProvider delayDuration={250} skipDelayDuration={400}>
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(!enabled)}
          aria-pressed={enabled}
          aria-label="计划模式"
          className={cn(
            'flex h-9 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold transition-all active:scale-95',
            enabled
              ? 'border-sky-500 bg-sky-500/15 text-sky-700 dark:text-sky-300'
              : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
            disabled && 'opacity-50',
          )}
        >
          <ClipboardList size={14} />
          <span className="hidden lg:inline">计划</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" sideOffset={6}>
        {enabled
          ? '计划模式：只调研并输出计划，批准后才执行'
          : '开启计划模式：先出计划再动手'}
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
);
