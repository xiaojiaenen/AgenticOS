/**
 * AI 提供商管理（管理员）。
 *
 * 这一屏要回答三个问题，顺序不能乱：
 *   1. **现在实际在用哪个？** —— 顶部「生效中」条。没有提供商时明确显示
 *      「正在使用环境变量兜底」，否则管理员会以为配置没生效。
 *   2. **有哪些可切换？** —— 列表 + 设为默认。
 *   3. **这个到底通不通？** —— 连通性测试，直接给出阶段与原因。
 *
 * 所有响应都只回答「有没有 Key / 有没有 Cookie」，界面上不提供「查看密钥」
 * 这类交互 —— 后端根本不返回，做了也是假的。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Star,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/shadcn/alert-dialog';
import { AdminPageHeader, ErrorBanner, StatusPill } from './shared';
import { EmptyState } from '@/components/ui/EmptyState';
import { ListSkeleton } from '@/components/ui/Skeletons';
import { LlmProviderDialog } from './LlmProviderDialog';
import { LlmProviderCredentialPanel } from './LlmProviderCredentialPanel';
import { LlmProviderModelPanel } from './LlmProviderModelPanel';
import {
  deleteLlmProvider,
  importLlmProviderFromEnv,
  listLlmProviders,
  setDefaultLlmProvider,
  testLlmProvider,
  type LlmProvider,
  type ProviderTestResult,
} from '@/services/llmProviderService';
import { toastError } from '../../lib/errors';

function relativeTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

/** 测试结果按 stage 给出可执行的话，而不是回显 HTTP 状态码 */
function describeTest(result: ProviderTestResult): string {
  if (result.ok) {
    const models = result.model_count ? `，可用模型 ${result.model_count} 个` : '';
    const mismatch =
      result.configured_model_available === false
        ? '（注意：配置的模型不在返回列表里，调用可能失败）'
        : '';
    return `连接正常${models}${mismatch}`;
  }
  if (result.stage === 'network') return result.message || '网络不可达';
  if (result.stage === 'auth') return result.message || '认证被拒绝';
  return result.message || `HTTP ${result.status_code ?? '?'}`;
}

const STAGE_LABELS: Record<string, string> = {
  network: '网络',
  auth: '认证',
  chat: '对话',
  stream: '流式',
  tools: '工具调用',
  client: '客户端',
};

/**
 * 分阶段结果。
 *
 * 只显示「失败在第几步、这一步说明什么」—— 排障时最有价值的不是 HTTP 码，
 * 而是「TLS 没过」和「认证过了但模型名不对」这种可直接行动的区分。
 */
function TestStages({ stages }: { stages: ProviderTestResult['stages'] }) {
  if (!stages || stages.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5">
      {stages.map((stage) => (
        <li key={stage.stage} className="flex flex-wrap items-baseline gap-1.5">
          <span
            className={
              stage.ok ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-600 dark:text-red-400'
            }
          >
            {stage.ok ? '✓' : '✕'}
          </span>
          <span className="font-semibold">{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
          <span className="opacity-80">
            {stage.ok
              ? stage.stage === 'tools'
                ? stage.message || '接受 tools 字段'
                : stage.stage === 'stream'
                  ? `收到 ${stage.frames ?? 0} 帧${stage.content ? ` · 首字 ${stage.content}` : ''}`
                  : stage.stage === 'chat'
                    ? `回复 ${stage.content || '（空）'}${stage.total_tokens ? ` · ${stage.total_tokens} tokens` : ''}`
                    : stage.stage === 'network'
                      ? `HTTP ${stage.status_code ?? '—'}`
                      : `通过${stage.model_count ? ` · ${stage.model_count} 个模型` : ''}`
              : stage.message || '失败'}
          </span>
          {stage.hint ? <span className="opacity-70">（{stage.hint}）</span> : null}
          <span className="opacity-50">{stage.elapsed_ms}ms</span>
        </li>
      ))}
    </ul>
  );
}

export function LlmProviderManagement() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<LlmProvider | null>(null);
  const [expanded, setExpanded] = useState<{ id: number; tab: 'accounts' | 'models' } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<LlmProvider | null>(null);
  const [testResults, setTestResults] = useState<Record<number, ProviderTestResult>>({});

  const providersQuery = useQuery({
    queryKey: ['admin', 'llm-providers'],
    queryFn: listLlmProviders,
  });

  const data = providersQuery.data;
  const providers = data?.items ?? [];
  const active = data?.active;
  const env = data?.env_fallback;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['admin', 'llm-providers'] });
  };

  const defaultMutation = useMutation({
    mutationFn: (id: number) => setDefaultLlmProvider(id),
    onSuccess: () => {
      toast.success('已切换默认提供商');
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '切换失败')),
  });

  const testMutation = useMutation({
    mutationFn: ({ id, deep }: { id: number; deep: boolean }) => testLlmProvider(id, deep),
    onSuccess: (result, vars) => {
      setTestResults((prev) => ({ ...prev, [vars.id]: result }));
    },
    onError: (err: Error, vars) => {
      setTestResults((prev) => ({
        ...prev,
        [vars.id]: { ok: false, stage: 'client', message: err.message, stages: [] },
      }));
    },
  });

  const importMutation = useMutation({
    mutationFn: importLlmProviderFromEnv,
    onSuccess: () => {
      toast.success('已按环境变量创建提供商');
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '导入失败')),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteLlmProvider(id),
    onSuccess: () => {
      toast.success('提供商已删除');
      setPendingDelete(null);
      invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '删除失败')),
  });

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (provider: LlmProvider) => {
    setEditing(provider);
    setDialogOpen(true);
  };

  if (providersQuery.isError) {
    // 不整页替换：整页 return 会把页头、刷新、导入、新建按钮一起带走，
    // 用户看到一条红色横幅却连「重试」都点不到 —— 只能刷新整个浏览器。
    // 这里保留完整页面骨架，把错误降级成页头下方的一条可恢复横幅。
    return (
      <div className="space-y-4">
        <AdminPageHeader
          kicker="AI Providers"
          title="AI 提供商"
          description="全站共用的大模型后端。切换默认提供商后，所有智能体与提示词优化都改用它。"
          actions={
            <>
              <Button variant="outline" size="sm" onClick={invalidate}>
                <RefreshCw className="mr-1.5 h-4 w-4" />
                刷新
              </Button>
              <Button size="sm" onClick={openCreate}>
                <Plus className="mr-1.5 h-4 w-4" />
                新建提供商
              </Button>
            </>
          }
        />
        <ErrorBanner
          message={toastError(providersQuery.error, '提供商列表加载失败')}
          onRetry={() => void providersQuery.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="AI Providers"
        title="AI 提供商"
        description="全站共用的大模型后端。切换默认提供商后，所有智能体与提示词优化都改用它。"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={invalidate}>
              <RefreshCw className="mr-1.5 h-4 w-4" />
              刷新
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => importMutation.mutate()}
              disabled={importMutation.isPending}
            >
              {importMutation.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-1.5 h-4 w-4" />
              )}
              从环境变量导入
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Plus className="mr-1.5 h-4 w-4" />
              新建提供商
            </Button>
          </>
        }
      />

      {/* 当前生效来源 */}
      {active ? (
        active.source === 'env' ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-500/40 dark:bg-amber-500/10">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-300" />
            <div className="min-w-0 text-sm">
              <p className="font-semibold text-amber-800 dark:text-amber-200">
                当前没有启用的提供商，正在使用环境变量兜底
              </p>
              <p className="mt-0.5 font-medium text-amber-700 dark:text-amber-300">
                {env?.base_url || '（未配置 OPENAI_BASE_URL）'}
                {env?.model ? ` · ${env.model}` : ''}
                {env?.usable ? '' : ' · 未配置 Key，调用会失败'}
              </p>
              <p className="mt-1 text-xs font-medium text-amber-700/80 dark:text-amber-300/80">
                新建一个提供商后即可脱离 .env 独立维护；也可以用「从环境变量导入」一键搬过来。
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-500/40 dark:bg-emerald-500/10">
            <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-300" />
            <p className="min-w-0 text-sm font-medium text-emerald-800 dark:text-emerald-200">
              生效中：<span className="font-semibold">{active.name}</span>
              <span className="ml-2 font-mono text-xs opacity-80">{active.base_url}</span>
              {active.model ? <span className="ml-2 text-xs opacity-80">{active.model}</span> : null}
            </p>
          </div>
        )
      ) : null}

      {/* 列表 */}
      {providersQuery.isLoading ? (
        <ListSkeleton rows={3} columns={3} />
      ) : providers.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-1)]">
          <EmptyState
            icon={<Zap className="size-5" />}
            title="还没有配置提供商"
            description="系统当前使用环境变量里的 LLM 配置，功能可用。新建一个提供商后即可脱离 .env 独立维护，也可以先从环境变量一键导入。"
            action={{ label: '新建提供商', onClick: openCreate }}
            secondaryAction={{ label: '从环境变量导入', onClick: () => importMutation.mutate() }}
          />
        </div>
      ) : (
        <div className="space-y-3">
          {providers.map((provider) => {
            const test = testResults[provider.id];
            const activeTab = expanded?.id === provider.id ? expanded.tab : null;
            const testing = testMutation.isPending && testMutation.variables?.id === provider.id;
            return (
              <section
                key={provider.id}
                className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm"
              >
                <div className="flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-semibold text-[var(--foreground)]">
                        {provider.name}
                      </h3>
                      {provider.is_active ? (
                        <StatusPill tone="active">生效中</StatusPill>
                      ) : provider.is_default ? (
                        <StatusPill tone="info">默认（未启用）</StatusPill>
                      ) : null}
                      {!provider.enabled ? <StatusPill tone="inactive">已停用</StatusPill> : null}
                      <StatusPill tone="info">{provider.provider_type_label}</StatusPill>
                      {provider.needs_cookie ? (
                        <StatusPill
                          tone={
                            provider.credential?.status === 'active'
                              ? 'active'
                              : provider.credential?.status === 'pending'
                                ? 'inactive'
                                : 'warning'
                          }
                        >
                          登录态：{provider.credential?.status ?? 'pending'}
                        </StatusPill>
                      ) : provider.has_api_key ? (
                        <StatusPill tone="active">已配 Key</StatusPill>
                      ) : (
                        <StatusPill tone="warning">缺 Key</StatusPill>
                      )}
                    </div>
                    <p className="break-all font-mono text-xs font-medium text-[var(--muted-foreground)]">
                      {provider.base_url}
                      {provider.model ? ` · ${provider.model}` : ''}
                      <span className="ml-2 opacity-70">slug: {provider.slug}</span>
                    </p>
                    {provider.description ? (
                      <p className="text-xs font-medium text-[var(--muted-foreground)]">
                        {provider.description}
                      </p>
                    ) : null}
                    <p className="text-[11px] font-medium text-[var(--muted-foreground)] opacity-70">
                      更新于 {relativeTime(provider.updated_at)}
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => testMutation.mutate({ id: provider.id, deep: false })}
                      disabled={testMutation.isPending}
                    >
                      {testing ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      测试
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => testMutation.mutate({ id: provider.id, deep: true })}
                      disabled={testMutation.isPending}
                      title="真实发一条对话并验证 function calling（会消耗上游额度）"
                    >
                      {testing ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Activity className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      深度检测
                    </Button>
                    {!provider.is_default ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => defaultMutation.mutate(provider.id)}
                        disabled={defaultMutation.isPending || !provider.enabled}
                      >
                        <Star className="mr-1.5 h-3.5 w-3.5" />
                        设为默认
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant={activeTab === 'models' ? 'secondary' : 'outline'}
                      onClick={() =>
                        setExpanded(activeTab === 'models' ? null : { id: provider.id, tab: 'models' })
                      }
                    >
                      {activeTab === 'models' ? '收起模型' : '模型'}
                    </Button>
                    {provider.needs_cookie ? (
                      <Button
                        size="sm"
                        variant={activeTab === 'accounts' ? 'secondary' : 'outline'}
                        onClick={() =>
                          setExpanded(
                            activeTab === 'accounts' ? null : { id: provider.id, tab: 'accounts' },
                          )
                        }
                      >
                        {activeTab === 'accounts'
                          ? '收起账号'
                          : `账号池${provider.account_count ? ` (${provider.account_count})` : ''}`}
                      </Button>
                    ) : null}
                    <Button size="sm" variant="outline" onClick={() => openEdit(provider)}>
                      编辑
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-600 hover:text-red-700 dark:text-red-400"
                      onClick={() => setPendingDelete(provider)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {test ? (
                  <div
                    className={
                      test.ok
                        ? 'border-t border-[var(--border-subtle)] bg-emerald-50/60 px-4 py-2.5 text-xs font-medium text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200'
                        : 'border-t border-[var(--border-subtle)] bg-amber-50/60 px-4 py-2.5 text-xs font-medium text-amber-800 dark:bg-amber-500/10 dark:text-amber-200'
                    }
                  >
                    <div className="flex items-start gap-2">
                      {test.ok ? (
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      ) : (
                        <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      )}
                      <span className="min-w-0 break-words">
                        {describeTest(test)}
                        {typeof test.elapsed_ms === 'number' ? ` · ${test.elapsed_ms}ms` : ''}
                        {test.hint ? <span className="ml-2 opacity-80">{test.hint}</span> : null}
                      </span>
                    </div>
                    <div className="pl-[22px]">
                      <TestStages stages={test.stages} />
                    </div>
                  </div>
                ) : null}

                {activeTab ? (
                  <div className="border-t border-[var(--border-subtle)] bg-[var(--surface-2)] p-4">
                    {activeTab === 'models' ? (
                      <LlmProviderModelPanel provider={provider} />
                    ) : (
                      <LlmProviderCredentialPanel provider={provider} />
                    )}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      )}

      <LlmProviderDialog
        open={dialogOpen}
        provider={editing}
        providerTypes={data?.provider_types ?? []}
        presets={data?.presets ?? []}
        onClose={() => setDialogOpen(false)}
      />

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(next) => (!next ? setPendingDelete(null) : undefined)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除提供商「{pendingDelete?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会同时删除它保存的 API Key 与登录凭据，无法恢复。
              {pendingDelete?.is_default
                ? ' 它当前是默认提供商，删除后系统会落到其它启用的提供商，或回退到环境变量配置。'
                : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
