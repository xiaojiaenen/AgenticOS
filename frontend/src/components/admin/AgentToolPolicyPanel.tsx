/**
 * 智能体能力限制（管理员统一控制用户自建智能体能用什么）。
 *
 * 背景：用户可以自建智能体、自选工具与 Skill。平台里有几类能力不该由普通用户
 * 自由启用 —— 能写文件、能跑命令的工具等于代码执行权限。这里是**平台级收口**：
 * 标记为受限的工具 / Skill 只对管理员拥有的智能体与平台内置可用。
 *
 * 默认只限制危险写操作（不是全限）：全限会让每个新工具上线就"坏了"，
 * 管理员得逐个放行，没人会维护这份名单。
 *
 * 三层防护（后端）：看不见（catalog 过滤）→ 带不出来（已存配置过滤）
 * → 存不进去（保存 403）。这个面板只负责维护那份名单。
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

/** 一个可勾选的受限项（工具与 Skill 共用同一套卡片视觉）。 */
const RestrictionCard: React.FC<{
  active: boolean;
  label: string;
  sub: string;
  onToggle: () => void;
}> = ({ active, label, sub, onToggle }) => (
  <button
    type="button"
    onClick={onToggle}
    aria-pressed={active}
    className={[
      'flex items-start gap-2.5 rounded-lg border p-3 text-left transition-colors',
      active
        ? 'border-amber-400/70 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10'
        : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:bg-[var(--surface-2)]',
    ].join(' ')}
  >
    <span
      className={[
        'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border',
        active
          ? 'border-amber-600 bg-amber-600 text-white dark:border-amber-400 dark:bg-amber-500'
          : 'border-[var(--border-medium)]',
      ].join(' ')}
    >
      {active ? <Lock className="h-2.5 w-2.5" /> : null}
    </span>
    <span className="min-w-0">
      <span className="block truncate text-sm font-medium text-[var(--foreground)]">{label}</span>
      <span className="block truncate font-mono text-[11px] text-[var(--muted-foreground)]">
        {sub}
      </span>
    </span>
  </button>
);

export const AgentToolPolicyPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin', 'agent-tool-policy'],
    queryFn: fetchAgentToolPolicy,
    staleTime: 30_000,
  });

  // 本地编辑副本：服务端值变化时同步（避免用 useEffect 造成额外渲染循环）
  const [restrictedTools, setRestrictedTools] = React.useState<Set<string>>(new Set());
  const [restrictedSkills, setRestrictedSkills] = React.useState<Set<string>>(new Set());
  const [filter, setFilter] = React.useState('');
  const [syncedFrom, setSyncedFrom] = React.useState<AgentToolPolicy | null>(null);

  if (data && data !== syncedFrom) {
    setSyncedFrom(data);
    setRestrictedTools(new Set(data.restricted_tools));
    setRestrictedSkills(new Set(data.restricted_skills));
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      updateAgentToolPolicy({
        restricted_tools: Array.from(restrictedTools).sort(),
        restricted_skills: Array.from(restrictedSkills).sort(),
      }),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'agent-tool-policy'] });
      toast.success(
        `已保存：${saved.restricted_tools.length} 个工具、${saved.restricted_skills.length} 个 Skill 仅管理员可用`,
      );
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : '保存失败');
    },
  });

  const availableTools = data?.available_tools ?? [];
  const availableSkills = data?.available_skills ?? [];

  const filteredTools = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return availableTools;
    return availableTools.filter(
      (item) => item.name.toLowerCase().includes(q) || item.label.toLowerCase().includes(q),
    );
  }, [availableTools, filter]);

  const filteredSkills = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return availableSkills;
    return availableSkills.filter(
      (item) => item.slug.toLowerCase().includes(q) || item.name.toLowerCase().includes(q),
    );
  }, [availableSkills, filter]);

  const toggle = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, name: string) => {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const resetToDefault = () => {
    setRestrictedTools(new Set(data?.default_restricted_tools ?? []));
    setRestrictedSkills(new Set());
    toast.message('已恢复默认名单，点「保存」生效');
  };

  const dirty = React.useMemo(() => {
    if (!data) return false;
    const t = Array.from(restrictedTools).sort().join(',');
    const s = Array.from(restrictedSkills).sort().join(',');
    return (
      t !== [...data.restricted_tools].sort().join(',') ||
      s !== [...data.restricted_skills].sort().join(',')
    );
  }, [data, restrictedTools, restrictedSkills]);

  const totalSelected = restrictedTools.size + restrictedSkills.size;

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="智能体与能力"
        title="能力限制"
        description="标记为受限的工具与 Skill 只对管理员拥有的智能体与平台内置可用。普通用户自建的智能体既看不到它们，也勾不上。"
      />

      {error ? <ErrorBanner message="限制策略加载失败，请刷新重试" /> : null}

      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
        <div className="flex items-start gap-2.5">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="space-y-1 text-sm text-[var(--muted-foreground)]">
            <p className="font-medium text-[var(--foreground)]">
              这是黑名单：勾上的被限制，未勾选的正常可用。
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
          placeholder="搜索工具名、中文名或 Skill…"
          className="h-9 max-w-xs"
        />
        <Badge variant="warning" className="font-medium">
          已限制 {totalSelected} 项
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
          正在加载清单…
        </div>
      ) : (
        <>
          <section className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--foreground)]">
              工具{' '}
              <span className="font-normal text-[var(--muted-foreground)]">
                （{restrictedTools.size} 项受限）
              </span>
            </h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {filteredTools.map((item) => (
                <RestrictionCard
                  key={item.name}
                  active={restrictedTools.has(item.name)}
                  label={item.label}
                  sub={item.name}
                  onToggle={() => toggle(setRestrictedTools, item.name)}
                />
              ))}
              {filteredTools.length === 0 ? (
                <p className="col-span-full py-4 text-center text-sm text-[var(--muted-foreground)]">
                  没有匹配的工具
                </p>
              ) : null}
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--foreground)]">
              Skill{' '}
              <span className="font-normal text-[var(--muted-foreground)]">
                （{restrictedSkills.size} 项受限）
              </span>
            </h3>
            {availableSkills.length === 0 ? (
              <p className="py-4 text-sm text-[var(--muted-foreground)]">
                平台还没有 Skill，或技能表读取失败。到「Skill 管理」上传后会出现在这里。
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {filteredSkills.map((item) => (
                  <RestrictionCard
                    key={item.slug}
                    active={restrictedSkills.has(item.slug)}
                    label={item.name}
                    sub={item.enabled ? item.slug : `${item.slug}（已停用）`}
                    onToggle={() => toggle(setRestrictedSkills, item.slug)}
                  />
                ))}
                {filteredSkills.length === 0 ? (
                  <p className="col-span-full py-4 text-center text-sm text-[var(--muted-foreground)]">
                    没有匹配的 Skill
                  </p>
                ) : null}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};
