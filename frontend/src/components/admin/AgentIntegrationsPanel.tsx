/**
 * 智能体配置：编辑弹窗右栏「外部系统集成」面板。
 * 从 AgentManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import type { UseFormReturn } from 'react-hook-form';
import { cn } from '@/lib/utils';
import type { IntegrationSystem } from '@/services/integrationService';
import type { AgentFormValues } from './agentHelpers';

export function AgentIntegrationsPanel({
  form,
  externalSystems,
}: {
  form: UseFormReturn<AgentFormValues>;
  externalSystems: IntegrationSystem[];
}) {
  const externalSystemsValue = form.watch('external_systems');

  const toggleExternalSystem = (systemId: number) => {
    const current = externalSystemsValue;
    const exists = current.some((es) => es.system_id === systemId);
    form.setValue(
      'external_systems',
      exists
        ? current.filter((es) => es.system_id !== systemId)
        : [...current, { system_id: systemId, enabled: true }],
      { shouldDirty: true },
    );
  };

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
            集成系统
          </p>
          <h4 className="mt-1 text-base font-semibold text-[var(--foreground)]">绑定外部系统</h4>
        </div>
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-semibold text-[var(--muted-foreground)]">
          已选 {externalSystemsValue.length}/{externalSystems.length}
        </span>
      </div>
      <div className="space-y-3">
        {externalSystems.length > 0 ? (
          externalSystems.map((sys) => {
            const selected = externalSystemsValue.some((es) => es.system_id === sys.id);
            return (
              <button
                key={sys.id}
                type="button"
                onClick={() => toggleExternalSystem(sys.id)}
                className={cn(
                  'w-full rounded-lg border p-3.5 text-left transition-all',
                  selected
                    ? 'border-emerald-300 bg-emerald-50/70 shadow-sm'
                    : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-zinc-300',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-[var(--foreground)]">{sys.name}</p>
                    <p className="mt-1 truncate text-[11px] font-semibold tracking-wide text-[var(--muted-foreground)]">
                      {sys.base_url}
                    </p>
                  </div>
                  <span
                    className={cn(
                      'rounded-full px-2 py-1 text-[10px] font-semibold',
                      selected ? 'bg-emerald-100 text-emerald-700' : 'bg-[var(--surface-2)] text-[var(--muted-foreground)]',
                    )}
                  >
                    {selected ? '已绑定' : '未绑定'}
                  </span>
                </div>
                <p className="mt-3 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                  {sys.description || '暂无描述'}
                </p>
                <div className="mt-2 flex gap-2">
                  <span className="rounded-full border border-zinc-100 bg-[var(--surface-2)] px-2.5 py-1 text-[10px] font-semibold text-zinc-600">
                    {sys.auth_type}
                  </span>
                  <span className="rounded-full border border-zinc-100 bg-[var(--surface-2)] px-2.5 py-1 text-[10px] font-semibold text-zinc-600">
                    {sys.api_count} API
                  </span>
                </div>
              </button>
            );
          })
        ) : (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-4 text-sm font-medium text-[var(--muted-foreground)]">
            还没有已启用的集成系统。
          </div>
        )}
      </div>
    </div>
  );
}
