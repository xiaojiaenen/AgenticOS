/**
 * 提供商的模型目录与用途绑定。
 *
 * 存在的理由：上游的「模型 ID」和「请求体要填的模型名」经常不是同一个东西
 * （上游常见 `qwen3.6-35b` vs `Qwen3.6-35B-A3B`）。靠人手填只有一个结局 ——
 * 调用时报 404 `Model Not Exist`，而界面上完全看不出是名字写错了。
 *
 * 所以这一屏做三件事：
 *   1. **从上游同步清单**（企业网关是公开注册表，OpenAI 兼容是 /models）；
 *   2. **让模型名可选而不是可背**；
 *   3. **按用途绑定** —— 对话 / 轻任务 / 深度思考 / 图像理解 / 文生图各用一个
 *      模型。企业网关的资源是按模型配的，混用会白烧额度。
 */
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, Loader2, RefreshCw, Save, Trash2 } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { StatusPill } from './shared';
import {
  deleteProviderModel,
  discoverProviderModels,
  listProviderModels,
  updateProviderRoles,
  type DiscoveredModel,
  type LlmProvider,
} from '@/services/llmProviderService';
import { toastError } from '../../lib/errors';

/** 引用稳定的空数组：直接写 ``?? []`` 会让 useMemo 的依赖每次渲染都变 */
const NO_MODELS: DiscoveredModel[] = [];

const TASK_LABELS: Record<string, string> = {
  'text-generation': '文本生成',
  'image-text-to-text': '图像理解',
  'text-to-image': '文生图',
  'any-to-any': '多模态',
};

/** 用途说明。和 presets.MODEL_ROLES 保持一致，措辞面向使用者而非开发者 */
const ROLE_HINTS: Record<string, string> = {
  chat: '主对话与 Agent 编排，质量最敏感',
  reasoner: '复杂推理、长链路规划，通常更慢更贵',
  fast: '会话标题、摘要、提示词润色等轻任务',
  vision: '读图、读扫描件',
  image: '文生图',
};

const EMPTY_VALUE = '__unset__';

export function LlmProviderModelPanel({ provider }: { provider: LlmProvider }) {
  const queryClient = useQueryClient();
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);

  const modelsQuery = useQuery({
    queryKey: ['admin', 'llm-provider-models', provider.id],
    queryFn: () => listProviderModels(provider.id),
  });

  const models = modelsQuery.data?.items ?? NO_MODELS;
  const roleOptions = modelsQuery.data?.role_options ?? [];

  /** 目录里的模型名去重：同一 name 可能有 base / thinking 两个入口 */
  const modelNames = useMemo(
    () => Array.from(new Set(models.map((item) => item.model_name))).sort(),
    [models],
  );

  useEffect(() => {
    if (modelsQuery.data && !dirty) {
      setRoles(modelsQuery.data.roles ?? {});
    }
  }, [modelsQuery.data, dirty]);

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: ['admin', 'llm-provider-models', provider.id],
    });
  };

  const discoverMutation = useMutation({
    mutationFn: () => discoverProviderModels(provider.id, true),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success(`已同步 ${result.models.length} 个模型（新增 ${result.added}）`);
        setDirty(false);
        invalidate();
      } else {
        toast.error(result.meta?.message || '同步失败');
      }
    },
    onError: (err: Error) => toast.error(toastError(err, '同步失败')),
  });

  const saveRolesMutation = useMutation({
    mutationFn: () => updateProviderRoles(provider.id, roles),
    onSuccess: () => {
      toast.success('用途绑定已保存');
      setDirty(false);
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ['admin', 'llm-providers'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '保存失败')),
  });

  const deleteModelMutation = useMutation({
    mutationFn: (modelId: number) => deleteProviderModel(provider.id, modelId),
    onSuccess: () => {
      toast.success('已从目录移除');
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '删除失败')),
  });

  const setRole = (role: string, value: string) => {
    setDirty(true);
    setRoles((prev) => {
      const next = { ...prev };
      if (value === EMPTY_VALUE) delete next[role];
      else next[role] = value;
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-[var(--foreground)]">模型目录</span>
        {modelsQuery.isLoading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--muted-foreground)]" />
        ) : (
          <StatusPill tone={models.length > 0 ? 'info' : 'inactive'}>
            {models.length} 个模型
          </StatusPill>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => discoverMutation.mutate()}
          disabled={discoverMutation.isPending}
        >
          {discoverMutation.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          )}
          从上游同步
        </Button>
        {provider.preset ? (
          <span className="text-xs font-medium text-[var(--muted-foreground)]">
            预设：{provider.preset}
          </span>
        ) : null}
      </div>

      {models.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3.5 py-4 text-xs font-medium text-[var(--muted-foreground)]">
          还没有同步过模型。点「从上游同步」会按提供商配置的探测方式拉取清单
          （企业网关常是站点下的静态注册表，而不是 /models）。
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
          <table className="w-full text-xs">
            <thead className="bg-[var(--surface-2)] text-left font-semibold text-[var(--muted-foreground)]">
              <tr>
                <th className="px-3 py-2">请求体里的模型名</th>
                <th className="px-3 py-2">上游 ID</th>
                <th className="px-3 py-2">类型</th>
                <th className="px-3 py-2">上下文</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.id} className="border-t border-[var(--border-subtle)]">
                  <td className="px-3 py-2 font-mono font-semibold text-[var(--foreground)]">
                    {model.model_name}
                  </td>
                  <td className="px-3 py-2 font-mono text-[var(--muted-foreground)]">
                    {model.model_key}
                  </td>
                  <td className="px-3 py-2 font-medium text-[var(--muted-foreground)]">
                    {TASK_LABELS[model.task_type] ?? model.task_type ?? '—'}
                  </td>
                  <td className="px-3 py-2 font-medium text-[var(--muted-foreground)]">
                    {model.max_tokens ? Math.round(model.max_tokens / 1024) + 'K' : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-600 hover:text-red-700 dark:text-red-400"
                      onClick={() => deleteModelMutation.mutate(model.id)}
                      disabled={deleteModelMutation.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-2.5 rounded-lg border border-[var(--border-subtle)] p-3.5">
        <div>
          <p className="text-sm font-semibold text-[var(--foreground)]">按用途绑定模型</p>
          <p className="text-xs font-medium text-[var(--muted-foreground)]">
            留空表示「跟随主模型」。只有在你确实想区分时再绑 —— 大多数部署一个模型就够。
          </p>
        </div>

        {modelNames.length === 0 ? (
          <p className="flex items-start gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>先同步模型目录，才有可选的名字（也可以直接在主表单里手填模型名）。</span>
          </p>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2">
          {roleOptions.map((role) => (
            <div key={role.value} className="grid gap-1.5">
              <div className="flex flex-wrap items-baseline gap-1.5">
                <span className="text-xs font-semibold text-[var(--foreground)]">{role.label}</span>
                <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
                  {ROLE_HINTS[role.value] ?? ''}
                </span>
              </div>
              <Select
                value={roles[role.value] ?? EMPTY_VALUE}
                onValueChange={(value) => setRole(role.value, value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="跟随主模型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={EMPTY_VALUE}>跟随主模型</SelectItem>
                  {modelNames.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}
        </div>

        <Button
          size="sm"
          onClick={() => saveRolesMutation.mutate()}
          disabled={saveRolesMutation.isPending || !dirty}
        >
          {saveRolesMutation.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" />
          )}
          保存绑定
        </Button>
      </div>
    </div>
  );
}
