/**
 * 评测面板（LLMOps）：数据集 → 用例 → 对指定智能体跑回归。
 *
 * 后端契约（backend/app/api/v1/endpoints/llmops.py）：
 * - GET    /agent/evals/datasets                    列表（只回 case_count，不含用例）
 * - GET    /agent/evals/datasets/{id}               详情（含 cases）
 * - POST   /agent/evals/datasets                    建集
 * - DELETE /agent/evals/datasets/{id}               删集
 * - POST   /agent/evals/datasets/{id}/cases         加用例（expected 为对象）
 * - DELETE /agent/evals/cases/{id}                  删用例
 * - POST   /agent/evals/datasets/{id}/run          异步起跑，立即回 { run_id, status: 'running' }
 * - GET    /agent/evals/runs/{id}                   轮询详情（running/done/error + 每用例结果）
 *
 * 关键点：run 是后台 asyncio 任务，接口不会等结果，必须轮询到终态。
 *
 * 视觉口径与管理后台其它页一致：AdminPageHeader + AdminPanel + shadcn Button/Input。
 */
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  CheckCircle2,
  ChevronRight,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react';

import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { AdminPageHeader, AdminPanel, ErrorBanner, SectionHeading } from '../admin/shared';
import { getAgentProfiles } from '../../services/agentProfileService';
import { cn } from '../../lib/utils';

import {
  addEvalCase,
  createEvalDataset,
  deleteEvalCase,
  deleteEvalDataset,
  getEvalDataset,
  getEvalRun,
  listEvalDatasets,
  listEvalRuns,
  startEvalRun,
  type EvalRun,
} from '../../services/llmopsService';
import { toastError } from '../../lib/errors';

const DATASETS_KEY = ['admin', 'eval', 'datasets'] as const;

/** 输入框/文本域的公共皮肤：与 shadcn Input 对齐。 */
const FIELD_CLASS =
  'h-9 w-full min-w-0 rounded-[10px] border border-[var(--border)] bg-transparent px-3 text-sm outline-none transition-[color,box-shadow,border-color] duration-150 placeholder:text-[var(--muted-foreground)] focus-visible:border-[var(--ring)] focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] disabled:cursor-not-allowed disabled:opacity-50';

const LABEL_CLASS =
  'text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--muted-foreground)]';

const RunStatusBadge = ({ run }: { run: EvalRun }) => {
  const label =
    run.status === 'running' ? '运行中' : run.status === 'done' ? '已完成' : '失败';
  const tone =
    run.status === 'running'
      ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300'
      : run.status === 'done'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
        : 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold',
        tone,
      )}
    >
      {run.status === 'running' ? <Loader2 size={11} className="animate-spin" /> : null}
      {label}
    </span>
  );
};

export const EvalPanel = () => {
  const queryClient = useQueryClient();

  const [selectedDatasetId, setSelectedDatasetId] = React.useState<number | null>(null);
  const [newDatasetName, setNewDatasetName] = React.useState('');
  const [caseInput, setCaseInput] = React.useState('');
  const [caseContains, setCaseContains] = React.useState('');
  const [caseNotContains, setCaseNotContains] = React.useState('');
  const [profileId, setProfileId] = React.useState<string>('');

  /** 当前关注的 run：起跑后写入，用于轮询。 */
  const [activeRunId, setActiveRunId] = React.useState<number | null>(null);

  const datasetsQuery = useQuery({
    queryKey: DATASETS_KEY,
    queryFn: listEvalDatasets,
  });
  const datasets = datasetsQuery.data?.items ?? [];

  const agentsQuery = useQuery({
    queryKey: ['admin', 'agent-profiles'],
    queryFn: getAgentProfiles,
  });
  const agents = agentsQuery.data?.items ?? [];

  // 数据集列表不含用例，选中后单独拉详情。
  const detailQuery = useQuery({
    queryKey: ['admin', 'eval', 'dataset', selectedDatasetId],
    queryFn: () => getEvalDataset(selectedDatasetId as number),
    enabled: selectedDatasetId !== null,
  });
  const detail = detailQuery.data;

  // 轮询：只有还在 running 时才继续拉，到终态自动停。
  const runQuery = useQuery({
    queryKey: ['admin', 'eval', 'run', activeRunId],
    queryFn: () => getEvalRun(activeRunId as number),
    enabled: activeRunId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'running' || status === undefined ? 1500 : false;
    },
  });
  const activeRun = runQuery.data;

  // run 一旦落地终态，刷新该数据集的运行历史。
  const runStatus = activeRun?.status;
  React.useEffect(() => {
    if (runStatus && runStatus !== 'running') {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'eval', 'runs'] });
    }
  }, [runStatus, queryClient]);

  const runsQuery = useQuery({
    queryKey: ['admin', 'eval', 'runs', selectedDatasetId],
    queryFn: () => listEvalRuns(selectedDatasetId ?? undefined),
    enabled: selectedDatasetId !== null,
  });
  const runs = runsQuery.data?.items ?? [];

  const invalidateDatasets = () =>
    queryClient.invalidateQueries({ queryKey: DATASETS_KEY });

  const shapeCaseExpected = () => {
    const contains = caseContains
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    const notContains = caseNotContains
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (contains.length === 0 && notContains.length === 0) return null;
    return {
      mode: 'keywords' as const,
      ...(contains.length ? { contains } : {}),
      ...(notContains.length ? { not_contains: notContains } : {}),
    };
  };

  const createDatasetMutation = useMutation({
    mutationFn: () => createEvalDataset({ name: newDatasetName.trim() }),
    onSuccess: (data) => {
      toast.success('数据集已创建');
      setNewDatasetName('');
      setSelectedDatasetId(data.id);
      void invalidateDatasets();
    },
    onError: (err) => toast.error(toastError(err, '创建数据集失败')),
  });

  const removeDatasetMutation = useMutation({
    mutationFn: (id: number) => deleteEvalDataset(id),
    onSuccess: (_data, id) => {
      toast.success('数据集已删除');
      if (selectedDatasetId === id) setSelectedDatasetId(null);
      void invalidateDatasets();
    },
    onError: (err) => toast.error(toastError(err, '删除数据集失败')),
  });

  const addCaseMutation = useMutation({
    mutationFn: () => {
      const expected = shapeCaseExpected();
      if (selectedDatasetId === null) throw new Error('请先选择数据集');
      if (!caseInput.trim()) throw new Error('请填写用例输入');
      if (!expected) {
        throw new Error('请至少填写一个「必须包含」或「禁止出现」关键词');
      }
      return addEvalCase(selectedDatasetId, { input: caseInput.trim(), expected });
    },
    onSuccess: () => {
      toast.success('用例已添加');
      setCaseInput('');
      setCaseContains('');
      setCaseNotContains('');
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'eval', 'dataset', selectedDatasetId],
      });
      void invalidateDatasets();
    },
    onError: (err) => toast.error(toastError(err, '添加用例失败')),
  });

  const removeCaseMutation = useMutation({
    mutationFn: (caseId: number) => deleteEvalCase(caseId),
    onSuccess: () => {
      toast.success('用例已删除');
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'eval', 'dataset', selectedDatasetId],
      });
      void invalidateDatasets();
    },
    onError: (err) => toast.error(toastError(err, '删除用例失败')),
  });

  const startRunMutation = useMutation({
    mutationFn: () => {
      if (selectedDatasetId === null) throw new Error('请先选择数据集');
      if (!profileId) throw new Error('请先选择要评测的智能体');
      return startEvalRun(selectedDatasetId, Number(profileId));
    },
    onSuccess: (data) => {
      toast.success('评测已启动，正在后台执行');
      setActiveRunId(data.run_id);
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'eval', 'runs', selectedDatasetId],
      });
    },
    onError: (err) => toast.error(toastError(err, '启动评测失败')),
  });

  const canCreateDataset = newDatasetName.trim().length > 0;
  const canRun = selectedDatasetId !== null && profileId !== '' && !startRunMutation.isPending;
  const isRunning = activeRun?.status === 'running';

  return (
    <div className="flex flex-col gap-5">
      <AdminPageHeader
        kicker="LLMOps"
        title="评测"
        description="把一组带期望输出的用例挂在数据集上，对指定智能体跑回归，观察通过率与逐条失分原因。"
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void datasetsQuery.refetch()}
              disabled={datasetsQuery.isFetching}
            >
              <RefreshCw size={13} className={datasetsQuery.isFetching ? 'animate-spin' : ''} />
              刷新
            </Button>
          </>
        }
      />

      {datasetsQuery.isError ? (
        <ErrorBanner
          message="数据集加载失败"
          onRetry={() => void datasetsQuery.refetch()}
          retryLabel="重试"
        />
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* ── 左栏：数据集列表 + 新建 ── */}
        <AdminPanel className="flex flex-col">
          <SectionHeading title="数据集" />
          <div className="flex flex-col gap-1.5 px-3 pb-3">
            {datasetsQuery.isLoading ? (
              <div className="flex items-center gap-2 px-2 py-6 text-xs font-medium text-[var(--muted-foreground)]">
                <Loader2 size={13} className="animate-spin" /> 加载中…
              </div>
            ) : datasets.length === 0 ? (
              <p className="px-2 py-6 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                还没有数据集。在下方新建一个，然后往里面加用例。
              </p>
            ) : (
              datasets.map((ds) => {
                const active = ds.id === selectedDatasetId;
                return (
                  <div
                    key={ds.id}
                    className={cn(
                      'group flex items-center gap-1 rounded-md transition-colors',
                      active ? 'bg-[var(--surface-2)]' : 'hover:bg-[var(--surface-2)]',
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedDatasetId(ds.id)}
                      className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left"
                    >
                      <ChevronRight
                        size={13}
                        className={cn(
                          'shrink-0 transition-transform',
                          active
                            ? 'text-[var(--foreground)]'
                            : 'text-[var(--muted-foreground)] group-hover:translate-x-0.5',
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span
                          className={cn(
                            'block truncate text-sm',
                            active
                              ? 'font-semibold text-[var(--foreground)]'
                              : 'font-medium text-[var(--foreground)]',
                          )}
                        >
                          {ds.name}
                        </span>
                        <span className="block text-[11px] font-medium text-[var(--muted-foreground)]">
                          {ds.case_count} 条用例
                        </span>
                      </span>
                    </button>
                    <button
                      type="button"
                      aria-label={`删除数据集 ${ds.name}`}
                      onClick={() => removeDatasetMutation.mutate(ds.id)}
                      disabled={removeDatasetMutation.isPending}
                      className="mr-1.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md text-[var(--muted-foreground)] opacity-0 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] group-hover:opacity-100 dark:hover:bg-red-500/10 dark:hover:text-red-300"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                );
              })
            )}
          </div>

          <div className="mt-auto border-t border-[var(--border-subtle)] p-3">
            <label className={LABEL_CLASS} htmlFor="new-dataset-name">
              新建数据集
            </label>
            <div className="mt-1.5 flex items-center gap-2">
              <Input
                id="new-dataset-name"
                value={newDatasetName}
                onChange={(e) => setNewDatasetName(e.target.value)}
                placeholder="如：客服回归集"
                className="h-9"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canCreateDataset) createDatasetMutation.mutate();
                }}
              />
              <Button
                size="sm"
                className="shrink-0 gap-1"
                disabled={!canCreateDataset || createDatasetMutation.isPending}
                onClick={() => createDatasetMutation.mutate()}
              >
                {createDatasetMutation.isPending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Plus size={13} />
                )}
                新建
              </Button>
            </div>
          </div>
        </AdminPanel>

        {/* ── 右栏：用例 + 跑批 + 结果 ── */}
        <div className="flex min-w-0 flex-col gap-5">
          {selectedDatasetId === null ? (
            <AdminPanel>
              <div className="flex flex-col items-center justify-center gap-1 px-6 py-16 text-center">
                <p className="text-sm font-semibold text-[var(--foreground)]">先在左侧选一个数据集</p>
                <p className="max-w-sm text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                  选中后可以维护用例、选择智能体跑回归，并查看每次运行里逐条用例的通过情况。
                </p>
              </div>
            </AdminPanel>
          ) : (
            <>
              {detailQuery.isError ? (
                <ErrorBanner
                  message="数据集详情加载失败"
                  onRetry={() => void detailQuery.refetch()}
                  retryLabel="重试"
                />
              ) : null}

              {/* 用例列表 */}
              <AdminPanel>
                <SectionHeading
                  title={detail?.name ?? '数据集'}
                  actions={
                    <span className="text-[11px] font-semibold text-[var(--muted-foreground)]">
                      {detail?.cases.length ?? 0} 条用例
                    </span>
                  }
                />
                {detail?.description ? (
                  <p className="px-4 pb-2 -mt-1 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                    {detail.description}
                  </p>
                ) : null}

                {detailQuery.isLoading ? (
                  <div className="flex items-center gap-2 px-4 py-8 text-xs font-medium text-[var(--muted-foreground)]">
                    <Loader2 size={13} className="animate-spin" /> 加载用例…
                  </div>
                ) : (detail?.cases.length ?? 0) === 0 ? (
                  <p className="px-4 pb-4 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                    这个数据集还没有用例。用下面的表单加第一条。
                  </p>
                ) : (
                  <ul className="border-t border-[var(--border-subtle)]">
                    {detail?.cases.map((c) => (
                      <li
                        key={c.id}
                        className="group flex items-start gap-3 border-b border-[var(--border-subtle)] px-4 py-2.5 last:border-b-0"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-[var(--foreground)]">
                            {c.input}
                          </p>
                          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                            {c.expected.contains?.length ? (
                              <span>必须包含：{c.expected.contains.join('、')}</span>
                            ) : null}
                            {c.expected.not_contains?.length ? (
                              <span>禁止出现：{c.expected.not_contains.join('、')}</span>
                            ) : null}
                            {!c.expected.contains?.length && !c.expected.not_contains?.length ? (
                              <span>无关键词约束</span>
                            ) : null}
                          </p>
                        </div>
                        <button
                          type="button"
                          aria-label="删除用例"
                          onClick={() => removeCaseMutation.mutate(c.id)}
                          disabled={removeCaseMutation.isPending}
                          className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-[var(--muted-foreground)] opacity-0 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] group-hover:opacity-100 dark:hover:bg-red-500/10 dark:hover:text-red-300"
                        >
                          <Trash2 size={13} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {/* 添加用例 */}
                <div className="border-t border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-3">
                  <p className={LABEL_CLASS}>添加用例</p>
                  <div className="mt-1.5 flex flex-col gap-2">
                    <textarea
                      value={caseInput}
                      onChange={(e) => setCaseInput(e.target.value)}
                      placeholder="用户输入，如：我的订单还没发货，帮我查一下"
                      rows={2}
                      className={cn(FIELD_CLASS, 'h-auto resize-y py-2 leading-5')}
                    />
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Input
                        value={caseContains}
                        onChange={(e) => setCaseContains(e.target.value)}
                        placeholder="必须包含（逗号分隔）"
                        className="h-9"
                      />
                      <Input
                        value={caseNotContains}
                        onChange={(e) => setCaseNotContains(e.target.value)}
                        placeholder="禁止出现（逗号分隔）"
                        className="h-9"
                      />
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-medium text-[var(--muted-foreground)]">
                        评分走关键词硬约束：全部 includes 命中且无 not_contains 命中才算通过。
                      </p>
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0 gap-1"
                        disabled={addCaseMutation.isPending}
                        onClick={() => addCaseMutation.mutate()}
                      >
                        {addCaseMutation.isPending ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : (
                          <Plus size={13} />
                        )}
                        添加
                      </Button>
                    </div>
                  </div>
                </div>
              </AdminPanel>

              {/* 跑批 */}
              <AdminPanel>
                <SectionHeading title="运行回归" />
                <div className="flex flex-col gap-3 px-4 pb-4 sm:flex-row sm:items-center">
                  <Select value={profileId} onValueChange={setProfileId}>
                    <SelectTrigger id="eval-agent" className="w-full sm:max-w-xs" aria-label="评测智能体">
                      <SelectValue placeholder="选择智能体…" />
                    </SelectTrigger>
                    <SelectContent>
                      {agents.length === 0 ? (
                        <div className="px-2 py-1.5 text-xs font-medium text-[var(--muted-foreground)]">
                          暂无可评测的智能体
                        </div>
                      ) : (
                        agents.map((a) => (
                          <SelectItem key={a.id} value={String(a.id)}>
                            {a.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    className="gap-1.5"
                    disabled={!canRun || isRunning}
                    onClick={() => startRunMutation.mutate()}
                  >
                    {isRunning || startRunMutation.isPending ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Play size={13} />
                    )}
                    {isRunning ? '评测进行中…' : '开始评测'}
                  </Button>
                  {agentsQuery.isError ? (
                    <span className="text-[11px] font-medium text-red-600 dark:text-red-400">
                      智能体列表加载失败
                    </span>
                  ) : null}
                </div>

                {/* 当前 run 的逐条结果 */}
                {activeRun ? (
                  <div className="border-t border-[var(--border-subtle)] px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold text-[var(--foreground)]">
                        本次运行 #{activeRun.id}
                      </span>
                      <RunStatusBadge run={activeRun} />
                      {activeRun.status !== 'running' ? (
                        <span className="text-xs font-medium text-[var(--muted-foreground)]">
                          {activeRun.passed}/{activeRun.total} 通过
                        </span>
                      ) : null}
                    </div>

                    {activeRun.status === 'error' && activeRun.error ? (
                      <p className="mt-2 text-xs font-medium text-red-600 dark:text-red-400">
                        {activeRun.error}
                      </p>
                    ) : null}

                    {activeRun.results?.length ? (
                      <ul className="mt-2 flex flex-col gap-1">
                        {activeRun.results.map((r) => (
                          <li
                            key={r.case_id}
                            className="rounded-md border border-[var(--border-subtle)] px-3 py-2"
                          >
                            <div className="flex items-start gap-2">
                              {r.passed ? (
                                <CheckCircle2
                                  size={14}
                                  className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400"
                                />
                              ) : (
                                <XCircle
                                  size={14}
                                  className="mt-0.5 shrink-0 text-red-600 dark:text-red-400"
                                />
                              )}
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-xs font-semibold text-[var(--foreground)]">
                                  {r.input}
                                </p>
                                {r.reason ? (
                                  <p className="mt-0.5 text-[11px] font-medium leading-4 text-[var(--muted-foreground)]">
                                    {r.reason}
                                  </p>
                                ) : null}
                                {r.error ? (
                                  <p className="mt-0.5 text-[11px] font-medium leading-4 text-red-600 dark:text-red-400">
                                    {r.error}
                                  </p>
                                ) : null}
                              </div>
                              <span className="shrink-0 text-[11px] font-medium text-[var(--muted-foreground)]">
                                {r.duration_ms}ms
                              </span>
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </AdminPanel>

              {/* 历史运行 */}
              <AdminPanel>
                <SectionHeading
                  title="运行历史"
                  actions={
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void runsQuery.refetch()}
                      disabled={runsQuery.isFetching}
                    >
                      <RefreshCw size={12} className={runsQuery.isFetching ? 'animate-spin' : ''} />
                      刷新
                    </Button>
                  }
                />
                {runsQuery.isLoading ? (
                  <div className="flex items-center gap-2 px-4 py-8 text-xs font-medium text-[var(--muted-foreground)]">
                    <Loader2 size={13} className="animate-spin" /> 加载运行记录…
                  </div>
                ) : runs.length === 0 ? (
                  <p className="px-4 pb-4 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                    还没有运行记录。
                  </p>
                ) : (
                  <ul className="border-t border-[var(--border-subtle)]">
                    {runs.map((run) => (
                      <li
                        key={run.id}
                        className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-4 py-2.5 last:border-b-0"
                      >
                        <span className="w-16 shrink-0 text-xs font-semibold text-[var(--foreground)]">
                          #{run.id}
                        </span>
                        <RunStatusBadge run={run} />
                        <span className="text-xs font-medium text-[var(--muted-foreground)]">
                          {run.status === 'running'
                            ? '执行中…'
                            : `${run.passed}/${run.total} 通过`}
                        </span>
                        <span className="ml-auto shrink-0 text-[11px] font-medium text-[var(--muted-foreground)]">
                          {run.created_at ? new Date(run.created_at).toLocaleString() : '—'}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="shrink-0"
                          onClick={() => setActiveRunId(run.id)}
                        >
                          详情
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </AdminPanel>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default EvalPanel;
