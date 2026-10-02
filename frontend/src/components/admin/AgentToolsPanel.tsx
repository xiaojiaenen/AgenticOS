/**
 * 智能体配置：编辑弹窗右栏「工具与审批」面板。
 * 从 AgentManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import type { UseFormReturn } from 'react-hook-form';
import { Check, X } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { cn } from '@/lib/utils';
import type { AgentProfileTool } from '@/services/agentProfileService';
import type { ToolCatalogItem } from '@/services/toolConfigService';
import type { AgentFormValues } from './agentHelpers';

// ---------------------------------------------------------------------------
// Toggle 开关（视觉与旧版一致）
// ---------------------------------------------------------------------------

function Toggle({
  checked,
  disabled,
  onClick,
}: {
  checked: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex h-8 w-14 items-center rounded-full p-1 transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'justify-end bg-zinc-900 shadow-md' : 'justify-start bg-zinc-200 hover:bg-zinc-300',
      )}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--surface-1)] shadow-sm">
        {checked ? <Check size={12} className="text-[var(--foreground)]" /> : <X size={12} className="text-[var(--muted-foreground)]" />}
      </span>
    </button>
  );
}

export function AgentToolsPanel({
  form,
  catalog,
  expandedTools,
  onToggleToolExpand,
}: {
  form: UseFormReturn<AgentFormValues>;
  catalog: ToolCatalogItem[];
  expandedTools: Set<string>;
  onToggleToolExpand: (toolName: string) => void;
}) {
  const tools = form.watch('tools');

  const catalogByName = new Map(catalog.map((item) => [item.name, item]));

  const updateTool = (toolName: string, patch: Partial<AgentProfileTool>) => {
    const current = form.getValues('tools');
    form.setValue(
      'tools',
      current.map((tool) => (tool.tool_name === toolName ? { ...tool, ...patch } : tool)),
      { shouldDirty: true },
    );
  };

  const toggleSubToolApproval = (toolName: string, subToolName: string) => {
    const current = form.getValues('tools');
    form.setValue(
      'tools',
      current.map((tool) => {
        if (tool.tool_name !== toolName) return tool;
        const currentSubs = tool.approval_sub_tools;
        const next = currentSubs.includes(subToolName)
          ? currentSubs.filter((s) => s !== subToolName)
          : [...currentSubs, subToolName];
        return { ...tool, approval_sub_tools: next, requires_approval: true };
      }),
      { shouldDirty: true },
    );
  };

  const enabledTools = tools.filter((tool) => tool.enabled).length;

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-700">
            工具与审批
          </p>
          <h4 className="mt-1 text-base font-semibold text-[var(--foreground)]">启用状态与审批开关</h4>
        </div>
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-semibold text-[var(--muted-foreground)]">
          已启用 {enabledTools}/{tools.length}
        </span>
      </div>

      <div className="space-y-3">
        {tools.map((tool) => {
          const meta = catalogByName.get(tool.tool_name);
          const isSkillTool = tool.tool_name === 'skill';
          const subTools = meta?.sub_tools || [];
          const hasSubTools = subTools.length > 1;
          const isExpanded = expandedTools.has(tool.tool_name);
          const approvedSubTools = tool.approval_sub_tools;

          return (
            <div key={tool.tool_name} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-[var(--foreground)]">
                      {meta?.label || tool.tool_name}
                    </p>
                    <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--muted-foreground)]">
                      {tool.tool_name}
                    </span>
                  </div>
                  <p className="mt-1 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                    {meta?.description}
                  </p>
                  {isSkillTool && (
                    <p className="mt-2 text-xs font-semibold text-amber-700">
                      Wuwei 已内建 skill 脚本执行审批、超时和路径校验；这里保留的是工具启用开关。
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-4 flex items-center gap-3">
                <div className="flex flex-1 items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5">
                  <span className="text-sm font-semibold text-zinc-700">启用</span>
                  <Toggle
                    checked={tool.enabled}
                    onClick={() => updateTool(tool.tool_name, { enabled: !tool.enabled })}
                  />
                </div>
                {hasSubTools ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onToggleToolExpand(tool.tool_name)}
                    className={cn('gap-2', isExpanded && 'border-zinc-900 text-zinc-800')}
                  >
                    子工具审批
                    <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-semibold">
                      {subTools.length}
                    </span>
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      className={cn('transition-transform', isExpanded && 'rotate-180')}
                    >
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </Button>
                ) : (
                  <div className="flex flex-1 items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5">
                    <span className="text-sm font-semibold text-zinc-700">需要审批</span>
                    <Toggle
                      checked={isSkillTool ? true : tool.requires_approval}
                      disabled={!tool.enabled || isSkillTool}
                      onClick={() =>
                        updateTool(tool.tool_name, {
                          requires_approval: !tool.requires_approval,
                        })
                      }
                    />
                  </div>
                )}
              </div>

              {hasSubTools && isExpanded && (
                <div className="mt-4 space-y-2 overflow-hidden border-t border-zinc-100 pt-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-xs font-medium text-[var(--muted-foreground)]">
                      点击子工具可跳过审批直接执行
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      className="text-zinc-700"
                      onClick={() => {
                        const allNeedApproval =
                          tool.requires_approval && approvedSubTools.length === 0;
                        if (allNeedApproval) {
                          updateTool(tool.tool_name, { requires_approval: false });
                        } else {
                          updateTool(tool.tool_name, {
                            requires_approval: true,
                            approval_sub_tools: [],
                          });
                        }
                      }}
                    >
                      {tool.requires_approval && approvedSubTools.length === 0
                        ? '全部跳过审批'
                        : '全部需要审批'}
                    </Button>
                  </div>
                  {subTools.map((sub) => {
                    const isSkipped =
                      tool.requires_approval &&
                      approvedSubTools.length > 0 &&
                      !approvedSubTools.includes(sub.name);
                    const isApproved = tool.requires_approval && !isSkipped;
                    return (
                      <div
                        key={sub.name}
                        className={cn(
                          'flex items-center justify-between rounded-lg border px-3 py-2 transition-colors',
                          isApproved
                            ? 'border-amber-200/80 bg-amber-50/60'
                            : 'border-[var(--border-subtle)] bg-[var(--surface-1)]',
                        )}
                      >
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-[var(--foreground)]">{sub.label}</p>
                          <p className="text-[10px] font-medium text-[var(--muted-foreground)]">{sub.name}</p>
                        </div>
                        <Toggle
                          checked={isApproved}
                          disabled={!tool.enabled}
                          onClick={() => toggleSubToolApproval(tool.tool_name, sub.name)}
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
