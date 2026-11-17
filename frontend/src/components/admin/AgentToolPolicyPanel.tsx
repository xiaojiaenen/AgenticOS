/**
 * 智能体能力限制（管理员统一控制用户自建智能体能用什么）。
 *
 * 背景：用户可以自建智能体、自选工具与 Skill。平台里有几类能力不该由普通用户
 * 自由启用 —— 能写文件、能跑命令的工具等于代码执行权限。这里是**平台级收口**：
 * 标记为受限的工具只对管理员拥有的智能体与平台内置可用。
 *
 * 默认只限制危险写操作（不是全限）：全限会让每个新工具上线就"坏了"，
 * 管理员得逐个放行，没人会维护这份名单。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Lock, RotateCcw, Save, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

import { AdminPageHeader, ErrorBanner } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Badge } from '@/components/ui/Badge';
import {
  fetchAgentToolPolicy,
  updateAgentToolPolicy,
  type AgentToolPolicy,
} from '@/services/toolConfigService';

export const AgentToolPolicyPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin', 'agent-tool-policy'],
    queryFn: fetchAgentToolPolicy,
    staleTime: 30_000,
  });

  // 本地编辑副本：服务端值变化时同步（避免用 useEffect 造成额外渲染循环）
  const [restricted, setRestricted] = React.useState<Set<string>>(new Set());
  const [filter, setFilter] = React.useState('');
  const [syncedFrom, setSyncedFrom] = React.useState<AgentToolPolicy | null>(null);

  if (data && data !== syncedFrom) {
    setSyncedFrom(data);
    setRestricted(new Set(data.restricted_tools));
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      updateAgentToolPolicy({ restricted_tools: Array.from(restricted).sort() }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['admin', 'agent-tool-policy'], undefined);
      queryClient.invalidateQueries({ queryKey: ['admin', 'agent-tool-policy'] });
      toast.success(`已保存：${saved.restricted_tools.length} 个工具仅管理员可用`);
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : '保存失败');
    },
  });

  const available = data?.available_tools ?? [];
  const filtered = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return available;
    return available.filter(
      (item) =>
        item.name.toLowerCase().includes(q) || item.label.toLowerCase().includes(q),
    );
  }, [available, filter]);

  const toggle = (name: string) => {
    setRestricted((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const resetToDefault = () => {
    setRestricted(new Set(data?.default_restricted_tools ?? []));
    toast.message('已恢复默认名单，点「保存」生效');
  };

  const dirty = React.useMemo(() => {
    if (!data) return false;
    const current = Array.from(restricted).sort().join(',');
    return current !== [...data.restricted_tools].sort().join(',');
  }, [data, restricted]);

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="智能体与能力"
        title="智能体能力限制"
        description="标记为受限的工具只对管理员拥有的智能体与平台内置可用；普通用户自建的智能体即使勾选也拿不到。"
      />

      {error ? <ErrorBanner message="限制策略加载失败，请刷新重试" /> : null}

      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
        <div className="flex items-start gap-2.5">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="space-y-1 text-sm text-[var(--muted-foreground)]">
            <p className="font-medium text-[var(--foreground)]">
              这是黑名单：勾上的工具被限制，未勾选的正常可用。
            </p>
            <p>
              默认只限制<strong>写文件</strong>与<strong>执行命令</strong>这类等价于代码执行的工具。
              全量限制会让每个新工具上线即不可用，反而没人维护。
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="搜索工具名或中文名…"
          className="h-9 max-w-xs"
        />
        <Badge variant="warning" className="font-medium">
          已限制 {restricted.size} 个
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={resetToDefault}
            disabled={isLoading || saveMutation.isPending}
          >
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            恢复默认
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={!dirty || saveMutation.isPending}
          >
            {saveMutation.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-3.5 w-3.5" />
            )}
            保存
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-[var(--muted-foreground)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在加载工具清单…
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((item) => {
            const on = restricted.has(item.name);
            return (
              <button
                key={item.name}
                type="button"
                onClick={() => toggle(item.name)}
                aria-pressed={on}
                className={[
                  'flex items-start gap-2.5 rounded-lg border p-3 text-left transition-colors',
                  on
                    ? 'border-amber-400/70 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10'
                    : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:bg-[var(--surface-2)]',
                ].join(' ')}
              >
                <span
                  className={[
                    'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                    on
                      ? 'border-amber-600 bg-amber-600 text-white dark:border-amber-400 dark:bg-amber-500'
                      : 'border-[var(--border-medium)]',
                  ].join(' ')}
                >
                  {on ? <Lock className="h-2.5 w-2.5" /> : null}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-[var(--foreground)]">
                    {item.label}
                  </span>
                  <span className="block truncate font-mono text-[11px] text-[var(--muted-foreground)]">
                    {item.name}
                  </span>
                </span>
              </button>
            );
          })}
          {filtered.length === 0 ? (
            <p className="col-span-full py-6 text-center text-sm text-[var(--muted-foreground)]">
              没有匹配的工具
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
};
