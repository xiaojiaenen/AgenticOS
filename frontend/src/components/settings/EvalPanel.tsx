/**
 * 评测面板（LLMOps）：数据集 → 用例 → 对指定智能体跑回归 → 通过率结果。
 *
 * 评分 MVP 规则：expected.contains / not_contains 关键词匹配；
 * 每个用例真实跑一轮完整 agent（工具可用），所以结果可信但较慢
 * （后台执行，前端轮询 run 状态）。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, Play, Plus, Trash2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
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
  type EvalCaseResult,
  } from '../../services/llmopsService';
  import { getAgentProfiles } from '../../services/agentProfileService';
import { toastError } from '../../lib/errors';
import { Button } from '../shadcn/button';
import { Input } from '../shadcn/input';

const ResultRow = ({ result }: { result: EvalCaseResult }) => (
  <div className="border-b border-[var(--border-subtle)] px-4 py-3 last:border-0">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="mb-1 line-clamp-2 text-sm font-medium">{result.input}</div>
        <div className="line-clamp-3 text-xs leading-relaxed text-[var(--muted-foreground)]">
          {result.output || result.error || '（无输出）'}
        </div>
        {result.reason && <div className="mt-1 text-xs text-amber-600">{result.reason}</div>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {result.passed ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600">
            <CheckCircle2 size={14} /> 通过
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-600">
            <XCircle size={14} /> 未通过
          </span>
        )}
        <span className="text-xs text-[var(--muted-foreground)]">
          {(result.duration_ms / 1000).toFixed(1)}s · 工具 {result.tool_calls}
        </span>
      </div>
    </div>
  </div>
);

export const EvalPanel = () => {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState('');
  const [selectedDataset, setSelectedDataset] = useState<number | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<number | null>(null);
  const [newCase, setNewCase] = useState({ input: '', contains: '' });
  const [lastRunId, setLastRunId] = useState<number | null>(null);

  const datasetsQuery = useQuery({ queryKey: ['llmops', 'eval-datasets'], queryFn: listEvalDatasets });
  const profilesQuery = useQuery({
    queryKey: ['admin', 'agents'],
    queryFn: getAgentProfiles,
  });
  const datasetQuery = useQuery({
    queryKey: ['llmops', 'eval-dataset', selectedDataset],
    queryFn: () => getEvalDataset(selectedDataset!),
    enabled: selectedDataset !== null,
  });
  const runsQuery = useQuery({
    queryKey: ['llmops', 'eval-runs'],
    queryFn: () => listEvalRuns(),
    refetchInterval: 5000,
  });
  const runQuery = useQuery({
    queryKey: ['llmops', 'eval-run', lastRunId],
    queryFn: () => getEvalRun(lastRunId!),
    enabled: lastRunId !== null,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });

  const createDatasetMutation = useMutation({
    mutationFn: () => createEvalDataset({ name: newName.trim() }),
    onSuccess: () => {
      toast.success('数据集已创建');
      setNewName('');
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'eval-datasets'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '创建失败')),
  });

  const addCaseMutation = useMutation({
    mutationFn: () =>
      addEvalCase(selectedDataset!, {
        input: newCase.input.trim(),
        expected: newCase.contains.trim()
          ? { contains: newCase.contains.split(/[,，]/).map((s) => s.trim()).filter(Boolean) }
          : {},
      }),
    onSuccess: () => {
      toast.success('用例已添加');
      setNewCase({ input: '', contains: '' });
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'eval-dataset', selectedDataset] });
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'eval-datasets'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '添加失败')),
  });

  const runMutation = useMutation({
    mutationFn: () => startEvalRun(selectedDataset!, selectedProfile!),
    onSuccess: (data) => {
      toast.success('评测已启动（后台逐用例执行）');
      setLastRunId(data.run_id);
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'eval-runs'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '启动失败')),
  });

  const deleteDatasetMutation = useMutation({
    mutationFn: deleteEvalDataset,
    onSuccess: () => {
      toast.success('数据集已删除');
      if (selectedDataset) setSelectedDataset(null);
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'eval-datasets'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '删除失败')),
  });

  const profiles = profilesQuery.data?.items ?? [];
  const runs = runsQuery.data?.items ?? [];
  const run = runQuery.data;

  return (
    <div className="space-y-4">
      {/* 数据集管理 */}
      <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="mr-auto text-sm font-semibold">评测数据集</h3>
          <Input
            className="h-8 w-48"
            placeholder="新数据集名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <Button
            size="sm"
            className="gap-1"
            disabled={!newName.trim() || createDatasetMutation.isPending}
            onClick={() => createDatasetMutation.mutate()}
          >
            <Plus size={14} /> 创建
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {(datasetsQuery.data?.items ?? []).map((d) => (
            <span
              key={d.id}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${
                selectedDataset === d.id
                  ? 'border-sky-300 bg-sky-50 text-sky-800'
                  : 'border-[var(--border-subtle)] bg-[var(--surface-2)]'
              }`}
            >
              <button type="button" className="font-medium" onClick={() => setSelectedDataset(d.id)}>
                {d.name}（{d.case_count} 用例）
              </button>
              <button
                type="button"
                aria-label="删除数据集"
                className="text-[var(--muted-foreground)] hover:text-rose-600"
                onClick={() => {
                  if (window.confirm(`删除数据集「${d.name}」及其全部用例？`)) deleteDatasetMutation.mutate(d.id);
                }}
              >
                <Trash2 size={13} />
              </button>
            </span>
          ))}
          {(datasetsQuery.data?.items ?? []).length === 0 && (
            <span className="text-sm text-[var(--muted-foreground)]">
              还没有数据集 —— 创建一个，把用户常问的问题和期望回答里的关键词放进去
            </span>
          )}
        </div>
      </div>

      {/* 用例编辑 + 运行 */}
      {selectedDataset !== null && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] p-4 shadow-sm">
            <h3 className="mb-3 text-sm font-semibold">添加用例</h3>
            <textarea
              className="mb-2 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] p-2 text-sm"
              rows={3}
              placeholder="用户输入（会真实发给智能体）"
              value={newCase.input}
              onChange={(e) => setNewCase((prev) => ({ ...prev, input: e.target.value }))}
            />
            <Input
              className="mb-2"
              placeholder="期望包含的关键词（逗号分隔，可空）"
              value={newCase.contains}
              onChange={(e) => setNewCase((prev) => ({ ...prev, contains: e.target.value }))}
            />
            <Button
              size="sm"
              className="gap-1"
              disabled={!newCase.input.trim() || addCaseMutation.isPending}
              onClick={() => addCaseMutation.mutate()}
            >
              <Plus size={14} /> 添加用例
            </Button>

            <div className="mt-4 max-h-64 space-y-2 overflow-y-auto">
              {(datasetQuery.data?.cases ?? []).map((c) => (
                <div key={c.id} className="flex items-start justify-between gap-2 rounded-md bg-[var(--surface-2)] px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{c.input}</div>
                    {(c.expected.contains ?? []).length > 0 && (
                      <div className="text-xs text-[var(--muted-foreground)]">
                        期望包含：{(c.expected.contains ?? []).join('、')}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    aria-label="删除用例"
                    className="text-[var(--muted-foreground)] hover:text-rose-600"
                    onClick={() => {
                      void deleteEvalCase(c.id).then(() =>
                        queryClient.invalidateQueries({ queryKey: ['llmops', 'eval-dataset', selectedDataset] }),
                      );
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] p-4 shadow-sm">
            <h3 className="mb-3 text-sm font-semibold">运行评测</h3>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <select
                className="h-8 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 text-sm"
                value={selectedProfile ?? ''}
                onChange={(e) => setSelectedProfile(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">选择智能体…</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                className="gap-1"
                disabled={!selectedProfile || runMutation.isPending}
                onClick={() => runMutation.mutate()}
              >
                {runMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                开始评测
              </Button>
            </div>

            {run && (
              <div className="rounded-md border border-[var(--border-subtle)]">
                <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2 text-sm">
                  {run.status === 'running' && <Loader2 size={14} className="animate-spin text-sky-600" />}
                  <span className="font-medium">
                    运行 #{run.id} · {run.status === 'running' ? '执行中' : run.status === 'done' ? '已完成' : '出错'}
                  </span>
                  <span className="ml-auto text-xs text-[var(--muted-foreground)]">
                    通过 {run.passed}/{run.total || (run.results?.length ?? 0)}
                  </span>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {(run.results ?? []).map((r) => (
                    <ResultRow key={r.case_id} result={r} />
                  ))}
                  {run.status === 'running' && (run.results?.length ?? 0) === 0 && (
                    <div className="p-4 text-center text-sm text-[var(--muted-foreground)]">
                      正在逐用例执行（每个用例真实跑一轮，请稍候）…
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="mt-4 max-h-40 overflow-y-auto">
              {runs.slice(0, 8).map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-[var(--surface-2)]"
                  onClick={() => setLastRunId(r.id)}
                >
                  <span className="font-medium">#{r.id}</span>
                  <span className="text-[var(--muted-foreground)]">
                    数据集 {r.dataset_id} · 智能体 {r.profile_id}
                  </span>
                  <span className="ml-auto">
                    {r.passed}/{r.total} {r.status === 'running' ? '· 执行中' : ''}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EvalPanel;
