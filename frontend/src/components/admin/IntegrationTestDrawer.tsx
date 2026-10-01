/**
 * 集成管理：接口测试抽屉。
 * 从 IntegrationManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { Loader2, TestTube, X } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { cn } from '@/lib/utils';
import { IntegrationApi, IntegrationTestResult } from '@/services/integrationService';

export type TestState = {
  apiId: number;
  params: Record<string, string>;
  result: IntegrationTestResult | null;
  loading: boolean;
};

export function TestDrawer({
  state,
  api,
  onClose,
  onParamChange,
  onRun,
}: {
  state: TestState;
  api: IntegrationApi | undefined;
  onClose: () => void;
  onParamChange: (name: string, value: string) => void;
  onRun: () => void;
}) {
  if (!api) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onMouseDown={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-[var(--border-subtle)] bg-[var(--surface-1)] p-6 shadow-lg"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[var(--foreground)]">测试: {api.display_name}</h3>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X size={18} />
          </Button>
        </div>
        <div className="mt-5 space-y-3">
          {api.params.map((p) => (
            <div key={p.name} className="space-y-1.5">
              <Label>
                {p.name} {p.required && <span className="text-rose-500">*</span>}
              </Label>
              <Input
                className="text-sm"
                value={state.params[p.name] ?? ''}
                onChange={(e) => onParamChange(p.name, e.target.value)}
                placeholder={p.description || p.name}
              />
            </div>
          ))}
          <Button onClick={onRun} disabled={state.loading} className="w-full gap-2">
            {state.loading ? <Loader2 size={16} className="animate-spin" /> : <TestTube size={16} />}
            发送请求
          </Button>
        </div>
        {state.result && (
          <div className="mt-5">
            <div
              className={cn(
                'rounded-lg border p-4',
                state.result.success ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50',
              )}
            >
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    'text-sm font-semibold',
                    state.result.success ? 'text-emerald-700' : 'text-rose-700',
                  )}
                >
                  {state.result.success ? '成功' : '失败'}
                  {state.result.status_code > 0 ? ` (${state.result.status_code})` : ''}
                </span>
                <span className="text-xs font-medium text-[var(--muted-foreground)]">{state.result.elapsed_ms}ms</span>
              </div>
              <pre className="mt-3 max-h-[300px] overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">
                {state.result.body}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
