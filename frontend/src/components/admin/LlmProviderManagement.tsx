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
  Download,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Star,
  Trash2,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
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
import {
  AdminPageHeader,
  AdminPanel,
  AdminToolbar,
  ErrorBanner,
  SectionHeading,
  StatusPill,
} from './shared';
import { Pagination } from './Pagination';
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

const PAGE_SIZE = 10;

function relativeTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

/**
 * 测试结论 → toast。
 *
 * 测试结果是一次性反馈，**不该占列表位置**：之前把它渲染成常驻结果条，
 * 一条失败就能把后面几个提供商挤下去（实测截图里整屏被一块错误占满）。
 * toast 承载「一句话结论 + 一句建议」；上游原文（几百字符 JSON）放不进 toast，
 * 也不该放 —— 需要原文的场景是排障，那里有 `console` 与各阶段的 detail。
 */
function toastTestResult(result: ProviderTestResult, deep: boolean) {
  const label = deep ? '深度检测' : '连通性测试';
  const seconds = result.elapsed_ms ? `（${result.elapsed_ms}ms）` : '';

  if (result.ok) {
    const parts = [`可用模型 ${result.model_count ?? 0} 个`];
    if (deep) {
      const stream = result.stages.find((stage) => stage.stage === 'stream');
      const tools = result.stages.find((stage) => stage.stage === 'tools');
      if (stream?.frames) parts.push(`流式 ${stream.frames} 帧`);
      if (tools?.ok) parts.push('工具调用可用');
    }
    if (result.configured_model_available === false) {
      parts.push('注意：配置的模型不在返回列表里');
    }
    toast.success(`${label}通过${seconds}`, { description: parts.join(' · ') });
    if (result.note) {
      toast.info('补充说明', { description: result.note });
    }
    return;
  }

  // 失败：标题只放结论，描述放建议 —— 长原文不进 toast
  const description = [result.hint, result.note].filter(Boolean).join(' · ') || undefined;
  toast.error(`${label}失败：${result.message || '未知原因'}`, { description });
}
export function LlmProviderManagement() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<LlmProvider | null>(null);
  const [expanded, setExpanded] = useState<{ id: number; tab: 'accounts' | 'models' } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<LlmProvider | null>(null);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);

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
      toastTestResult(result, vars.deep);
    },
    onError: (err: Error, vars) => {
      toastTestResult(
        { ok: false, stage: 'client', message: err.message, stages: [] },
        vars.deep,
      );
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

  // 本地过滤 + 客户端分页：提供商一般是个位数到几十条，
  // 直接一次拉全量比做服务端分页简单，也不会出现「翻页时筛选项丢失」。
  const visible = providers.filter((provider) => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return true;
    return [provider.name, provider.slug, provider.base_url, provider.model, provider.provider_type_label]
      .join(' ')
      .toLowerCase()
      .includes(needle);
  });
  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageItems = visible.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  if (providersQuery.isError) {
    // 不整页替换：整页 return 会把页头、刷新、导入、新建按钮一起带走，
    // 用户看到一条红色横幅却连「重试」都点不到 —— 只能刷新整个浏览器。
    // 这里保留完整页面骨架，把错误降级成页头下方的一条可恢复横幅。
    return (
      <div className="space-y-3">
        <AdminPageHeader
          kicker="AI Providers"
          title="AI 提供商"
          description="全站共用的大模型后端。切换默认提供商后，所有智能体与提示词优化都改用它。"
        />
        <ErrorBanner
          message={toastError(providersQuery.error, '提供商列表加载失败')}
          onRetry={() => void providersQuery.refetch()}
        />
        <AdminToolbar>
          <Button variant="outline" size="sm" className="h-8 gap-1.5" onClick={invalidate}>
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </Button>
          <Button size="sm" className="h-8 gap-1.5" onClick={openCreate}>
            <Plus className="h-3.5 w-3.5" />
            新建提供商
          </Button>
        </AdminToolbar>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <AdminPageHeader
        kicker="AI Providers"
        title="AI 提供商"
        description="全站共用的大模型后端。切换默认提供商后，所有智能体与提示词优化都改用它。"
      />

      {/* 当前生效来源：一条紧凑的状态带，不占整张卡片 */}
      {active ? (
        active.source === 'env' ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 dark:border-amber-500/40 dark:bg-amber-500/10">
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
          <div className="flex items-center gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 dark:border-emerald-500/40 dark:bg-emerald-500/10">
            <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-300" />
            <p className="min-w-0 text-sm font-medium text-emerald-800 dark:text-emerald-200">
              生效中：<span className="font-semibold">{active.name}</span>
              <span className="ml-2 font-mono text-xs opacity-80">{active.base_url}</span>
              {active.model ? <span className="ml-2 text-xs opacity-80">{active.model}</span> : null}
            </p>
          </div>
        )
      ) : null}

      {/* 工具条：搜索 + 统计 + 刷新，替代原来单独一张筛选卡片 */}
      <AdminToolbar>
        <div className="relative">
          <Search
            size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
          />
          <Input
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              setPage(1);
            }}
            placeholder="搜索名称 / 地址 / 模型"
            aria-label="搜索提供商"
            className="h-8 w-60 pl-7 text-xs"
          />
        </div>
        <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
          共 {providers.length} 个
          {visible.length !== providers.length ? ` · 命中 ${visible.length}` : ''}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5"
            onClick={invalidate}
            disabled={providersQuery.isFetching}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${providersQuery.isFetching ? 'animate-spin' : ''}`}
            />
            刷新
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5"
            onClick={() => importMutation.mutate()}
            disabled={importMutation.isPending}
          >
            {importMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            从环境变量导入
          </Button>
          <Button size="sm" className="h-8 gap-1.5" onClick={openCreate}>
            <Plus className="h-3.5 w-3.5" />
            新建提供商
          </Button>
        </div>
      </AdminToolbar>

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
      ) : visible.length === 0 ? (
        <AdminPanel className="px-4 py-12 text-center">
          <p className="text-sm font-medium text-[var(--foreground)]">没有匹配的提供商</p>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">换个关键词，或清空搜索框</p>
          <Button size="sm" variant="outline" className="mt-3" onClick={() => setFilter('')}>
            清空搜索
          </Button>
        </AdminPanel>
      ) : (
        <AdminPanel>
          <SectionHeading
            title={`提供商 · ${visible.length}`}
            description="测试 = 轻量（网络/凭据/模型清单）；深度检测 = 再真发对话、流式与工具调用"
          />
          <ul className="divide-y divide-[var(--border-subtle)]">
          {pageItems.map((provider) => {
            const activeTab = expanded?.id === provider.id ? expanded.tab : null;
            const testing = testMutation.isPending && testMutation.variables?.id === provider.id;
            return (
              <li key={provider.id} className="transition-colors hover:bg-[var(--surface-2)]/60">
                <div className="flex flex-col gap-2.5 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h3 className="text-sm font-semibold text-[var(--foreground)]">
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
                    {/* 一行放完地址与元信息：卡片式布局里这些各占一行，长列表要一直往下滚 */}
                    <p className="mt-1 truncate font-mono text-[11px] font-medium text-[var(--muted-foreground)]">
                      {provider.base_url}
                      {provider.model ? ` · ${provider.model}` : ''}
                      <span className="ml-2 opacity-70">{provider.slug}</span>
                      <span className="ml-2 opacity-70">更新 {relativeTime(provider.updated_at)}</span>
                    </p>
                    {provider.description ? (
                      <p className="mt-0.5 truncate text-[11px] font-medium text-[var(--muted-foreground)] opacity-80">
                        {provider.description}
                      </p>
                    ) : null}
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1.5 px-2.5"
                      onClick={() => testMutation.mutate({ id: provider.id, deep: false })}
                      disabled={testMutation.isPending}
                      title="轻量检测：只验证网络可达 + 凭据被接受 + 模型清单，不消耗上游额度"
                    >
                      {testing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Zap className="h-3.5 w-3.5" />
                      )}
                      测试
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1.5 px-2.5"
                      onClick={() => testMutation.mutate({ id: provider.id, deep: true })}
                      disabled={testMutation.isPending}
                      title="深度检测：轻量检测通过后，再真实发一条对话、一条流式请求、一次带 tools 的请求。能验证「模型名对不对、流式能不能用、工具调用透不透传」，但会消耗上游额度。"
                    >
                      {testing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Activity className="h-3.5 w-3.5" />
                      )}
                      深度检测
                    </Button>
                    {!provider.is_default ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5 px-2.5"
                        onClick={() => defaultMutation.mutate(provider.id)}
                        disabled={defaultMutation.isPending || !provider.enabled}
                        title="设为默认提供商"
                      >
                        <Star className="h-3.5 w-3.5" />
                        设为默认
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant={activeTab === 'models' ? 'secondary' : 'outline'}
                      className="h-8 px-2.5"
                      onClick={() =>
                        setExpanded(activeTab === 'models' ? null : { id: provider.id, tab: 'models' })
                      }
                    >
                      模型
                    </Button>
                    {provider.needs_cookie ? (
                      <Button
                        size="sm"
                        variant={activeTab === 'accounts' ? 'secondary' : 'outline'}
                        className="h-8 px-2.5"
                        onClick={() =>
                          setExpanded(
                            activeTab === 'accounts' ? null : { id: provider.id, tab: 'accounts' },
                          )
                        }
                      >
                        账号{provider.account_count ? ` ${provider.account_count}` : ''}
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2.5"
                      onClick={() => openEdit(provider)}
                    >
                      编辑
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      className="h-8 w-8 text-red-600 hover:text-red-700 dark:text-red-400"
                      onClick={() => setPendingDelete(provider)}
                      aria-label={`删除 ${provider.name}`}
                      title="删除"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {activeTab ? (
                  <div className="border-t border-[var(--border-subtle)] bg-[var(--surface-2)] p-4">
                    {activeTab === 'models' ? (
                      <LlmProviderModelPanel provider={provider} />
                    ) : (
                      <LlmProviderCredentialPanel provider={provider} />
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
          </ul>
          <Pagination
            currentPage={safePage}
            totalPages={totalPages}
            onPageChange={setPage}
            totalLabel={`共 ${visible.length} 个提供商`}
          />
        </AdminPanel>
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
