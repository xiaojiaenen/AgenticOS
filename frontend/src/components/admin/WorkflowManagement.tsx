/**
 * 工作流管理（P0-3 v1 的管理端最小界面）：
 * 列表 / JSON 编辑 / 启停 / 运行 / 运行记录 / 人工输入恢复。
 *
 * v1 刻意用「JSON 文本域」而不是画布：节点图 DSL 稳定后（引擎有 46 个
 * 测试钉住校验语义），画布只是同一份 JSON 的可视化编辑器，后补不破坏
 * 任何东西。后端校验把**全部**问题一次报回，这里原样展示。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Skeleton } from '@/components/shadcn/skeleton';
import { Switch } from '@/components/shadcn/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
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
import { AdminPageHeader, AdminPanel, ErrorBanner, StatusPill } from './shared';
import { WorkflowGraphEditor } from './WorkflowGraphEditor';
import { WorkflowCanvas } from './WorkflowCanvas';
import {
  createWorkflow,
  deleteWorkflow,
  getWorkflow,
  getWorkflowRun,
  listWorkflowRuns,
  listWorkflows,
  resumeWorkflowRun,
  runWorkflow,
  setWorkflowEnabled,
  updateWorkflow,
  type Workflow,
  type WorkflowRun,
  type WorkflowSummary,
} from '@/services/workflowService';
import { toastError } from '@/lib/errors';
import { cn } from '@/lib/utils';

const QUERY_KEY = ['admin', 'workflows'] as const;

const RUN_STATUS_TONE: Record<WorkflowRun['status'], 'active' | 'inactive' | 'warning' | 'info'> = {
  succeeded: 'active',
  failed: 'warning',
  waiting_input: 'info',
  running: 'info',
};

const RUN_STATUS_LABEL: Record<WorkflowRun['status'], string> = {
  succeeded: '成功',
  failed: '失败',
  waiting_input: '等待人工输入',
  running: '运行中',
};

function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** 演示用最小图：新建时给一个能直接跑通的骨架，降低第一次上手门槛。 */
const STARTER_GRAPH = JSON.stringify(
  {
    nodes: [
      { id: 'start', type: 'start' },
      { id: 't', type: 'template', params: { template: '你好 {{inputs.name}}' } },
      { id: 'end', type: 'end', params: { output: '{{nodes.t.output}}' } },
    ],
    edges: [
      { from: 'start', to: 't' },
      { from: 't', to: 'end' },
    ],
  },
  null,
  2,
);

interface EditorState {
  id: number | null;
  name: string;
  description: string;
  enabled: boolean;
  graphText: string;
}

function editorFromWorkflow(wf: Workflow | null): EditorState {
  return {
    id: wf?.id ?? null,
    name: wf?.name ?? '',
    description: wf?.description ?? '',
    enabled: wf?.enabled ?? false,
    graphText: wf ? JSON.stringify(wf.graph, null, 2) : STARTER_GRAPH,
  };
}

export function WorkflowManagement() {
  const queryClient = useQueryClient();
  const [editorState, setEditorState] = React.useState<EditorState | null>(null);
  // 编辑模式：canvas=拖拽画布 / form=结构化表单 / json=直接改 JSON
  const [editMode, setEditMode] = React.useState<'canvas' | 'form' | 'json'>('canvas');
  const [runningWf, setRunningWf] = React.useState<WorkflowSummary | null>(null);
  const [runInputsText, setRunInputsText] = React.useState('{}');
  const [runResult, setRunResult] = React.useState<WorkflowRun | null>(null);
  const [resumeValueText, setResumeValueText] = React.useState('');
  const [runsFor, setRunsFor] = React.useState<WorkflowSummary | null>(null);
  const [deleting, setDeleting] = React.useState<WorkflowSummary | null>(null);

  const listQuery = useQuery({ queryKey: QUERY_KEY, queryFn: listWorkflows });
  const workflows = listQuery.data?.items ?? [];

  const runsQuery = useQuery({
    queryKey: [...QUERY_KEY, 'runs', runsFor?.id],
    queryFn: () => listWorkflowRuns(runsFor!.id),
    enabled: runsFor != null,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const saveMutation = useMutation({
    mutationFn: (state: EditorState) => {
      const graph = JSON.parse(state.graphText) as Workflow['graph'];
      const payload = {
        name: state.name.trim(),
        description: state.description.trim(),
        graph,
        enabled: state.enabled,
      };
      return state.id != null ? updateWorkflow(state.id, payload) : createWorkflow(payload);
    },
    onSuccess: (_data, state) => {
      toast.success(state.id != null ? '工作流已保存' : '工作流已创建');
      setEditorState(null);
      void invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '保存失败')),
  });

  const toggleMutation = useMutation({
    mutationFn: (payload: { id: number; enabled: boolean }) =>
      setWorkflowEnabled(payload.id, payload.enabled),
    onSuccess: (_d, variables) => {
      toast.success(variables.enabled ? '已启用（智能体下次构建时挂载工具）' : '已停用');
      void invalidate();
    },
    onError: (err: Error) => {
      toast.error(toastError(err, '状态更新失败'));
      void invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteWorkflow(id),
    onSuccess: () => {
      toast.success('工作流已删除');
      setDeleting(null);
      void invalidate();
    },
    onError: (err: Error) => toast.error(toastError(err, '删除失败')),
  });

  const runMutation = useMutation({
    mutationFn: (payload: { id: number; inputs: Record<string, unknown> }) =>
      runWorkflow(payload.id, payload.inputs),
    onSuccess: (run) => {
      setRunResult(run);
      void invalidate();
      if (runsFor) void queryClient.invalidateQueries({ queryKey: [...QUERY_KEY, 'runs', runsFor.id] });
    },
    onError: (err: Error) => toast.error(toastError(err, '运行失败')),
  });

  // 后台执行：run 处于 running 时每 1.5s 轮询详情，到终态自动停
  const runId = runResult?.id;
  const runStatus = runResult?.status;
  React.useEffect(() => {
    if (runId == null || runStatus !== 'running') return;
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const latest = await getWorkflowRun(runId);
          setRunResult((prev) => (prev != null && prev.id === runId ? latest : prev));
        } catch {
          // 单次轮询失败不打断，下一轮再试
        }
      })();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [runId, runStatus]);

  const resumeMutation = useMutation({
    mutationFn: (payload: { runId: number; value: unknown }) =>
      resumeWorkflowRun(payload.runId, payload.value),
    onSuccess: (run) => {
      setRunResult(run);
      if (runsFor) void queryClient.invalidateQueries({ queryKey: [...QUERY_KEY, 'runs', runsFor.id] });
      toast.success(run.status === 'succeeded' ? '已恢复并执行完成' : `已恢复，当前状态：${RUN_STATUS_LABEL[run.status]}`);
    },
    onError: (err: Error) => toast.error(toastError(err, '恢复失败')),
  });

  const openEdit = async (wf: WorkflowSummary) => {
    // 编辑需要全量 graph：详情接口拿一次（列表不带图，减少传输）
    try {
      const full = await getWorkflow(wf.id);
      setEditorState(editorFromWorkflow(full));
    } catch (err) {
      toast.error(toastError(err, '加载工作流详情失败'));
    }
  };

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="智能体与能力"
        title="工作流"
        description="把预编排的节点流程（检索 → 判断 → 生成）打包成能力：已启用的工作流会自动挂载为智能体工具，对话里即可调用；也支持人工输入暂停/恢复。"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void listQuery.refetch()}>
              <RefreshCw className="mr-1.5 size-3.5" /> 刷新
            </Button>
            <Button size="sm" onClick={() => setEditorState(editorFromWorkflow(null))}>
              <Plus className="mr-1.5 size-3.5" /> 新建工作流
            </Button>
          </>
        }
      />

      <AdminPanel>
        {listQuery.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : listQuery.isError ? (
          <ErrorBanner
            message={`工作流列表加载失败：${String((listQuery.error as Error)?.message ?? '')}`}
            onRetry={() => void listQuery.refetch()}
          />
        ) : workflows.length === 0 ? (
          <div className="p-8 text-center text-sm font-medium text-[var(--muted-foreground)]">
            还没有工作流。点「新建工作流」创建第一个 —— 模板图开箱即跑。
          </div>
        ) : (
          <ul className="divide-y divide-[var(--border-subtle)]">
            {workflows.map((wf) => (
              <li key={wf.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-[var(--foreground)]">{wf.name}</span>
                    <StatusPill tone={wf.enabled ? 'active' : 'inactive'}>
                      {wf.enabled ? '已启用' : '停用'}
                    </StatusPill>
                    <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
                      {wf.node_count} 个节点
                    </span>
                  </div>
                  {wf.description ? (
                    <p className="mt-0.5 line-clamp-1 text-xs font-medium text-[var(--muted-foreground)]">
                      {wf.description}
                    </p>
                  ) : null}
                  <p className="mt-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                    更新于 {formatTime(wf.updated_at)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <div className="flex items-center gap-1.5">
                    <Switch
                      checked={wf.enabled}
                      onCheckedChange={(checked) =>
                        toggleMutation.mutate({ id: wf.id, enabled: checked })
                      }
                      disabled={toggleMutation.isPending}
                      aria-label={`启停 ${wf.name}`}
                    />
                  </div>
                  <Button variant="outline" size="sm" onClick={() => void openEdit(wf)}>
                    编辑
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setRunningWf(wf);
                      setRunInputsText('{}');
                      setRunResult(null);
                      runMutation.mutate({ id: wf.id, inputs: {} });
                    }}
                  >
                    运行
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setRunsFor(wf)}>
                    运行记录
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setDeleting(wf)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </AdminPanel>

      {/* 编辑 / 新建 */}
      <Dialog open={editorState != null} onOpenChange={(open) => !open && setEditorState(null)}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>{editorState?.id != null ? '编辑工作流' : '新建工作流'}</DialogTitle>
            <DialogDescription>
              节点图用 JSON 描述（保存时后端会一次性报出全部结构问题）。变量写法：
              {'{{inputs.x}}'} 与 {'{{nodes.<节点id>.output}}'}。
            </DialogDescription>
          </DialogHeader>
          {editorState != null ? (
            <div className="space-y-3">
              <div className="grid gap-2">
                <Label htmlFor="wf-name">名称</Label>
                <Input
                  id="wf-name"
                  value={editorState.name}
                  onChange={(e) => setEditorState({ ...editorState, name: e.target.value })}
                  placeholder="例如：报销制度问答"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="wf-desc">描述（会进入智能体工具的说明）</Label>
                <Input
                  id="wf-desc"
                  value={editorState.description}
                  onChange={(e) => setEditorState({ ...editorState, description: e.target.value })}
                  placeholder="一句话说明这条流程做什么"
                />
              </div>
              <div className="grid gap-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="wf-graph">节点图</Label>
                  <div className="flex items-center gap-1">
                    {(['canvas', 'form', 'json'] as const).map((mode) => (
                      <Button
                        key={mode}
                        variant={editMode === mode ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => {
                          if (mode === 'json') {
                            setEditMode('json');
                            return;
                          }
                          // 回画布/表单前确认 JSON 合法（画布按结构渲染）
                          try {
                            JSON.parse(editorState.graphText);
                            setEditMode(mode);
                          } catch {
                            toast.error('JSON 尚不合法，修正后才能切回可视化编辑');
                          }
                        }}
                      >
                        {mode === 'canvas' ? '画布' : mode === 'form' ? '表单' : 'JSON'}
                      </Button>
                    ))}
                  </div>
                </div>
                {editMode === 'json' ? (
                  <textarea
                    id="wf-graph"
                    value={editorState.graphText}
                    onChange={(e) => setEditorState({ ...editorState, graphText: e.target.value })}
                    spellCheck={false}
                    className={cn(
                      'h-72 w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3',
                      'font-mono text-xs leading-5 text-[var(--foreground)]',
                      'focus:outline-none focus:ring-2 focus:ring-[var(--ring)]',
                    )}
                  />
                ) : editMode === 'canvas' ? (
                  <WorkflowCanvas
                    graphText={editorState.graphText}
                    onChange={(next) => setEditorState({ ...editorState, graphText: next })}
                  />
                ) : (
                  <WorkflowGraphEditor
                    graphText={editorState.graphText}
                    onChange={(next) => setEditorState({ ...editorState, graphText: next })}
                  />
                )}
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Switch
                    checked={editorState.enabled}
                    onCheckedChange={(checked) => setEditorState({ ...editorState, enabled: checked })}
                    id="wf-enabled"
                  />
                  <Label htmlFor="wf-enabled">启用（启用后自动挂载为智能体工具）</Label>
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditorState(null)}>
              取消
            </Button>
            <Button
              disabled={editorState == null || saveMutation.isPending}
              onClick={() => {
                if (editorState == null) return;
                try {
                  JSON.parse(editorState.graphText);
                } catch {
                  toast.error('节点图不是合法 JSON，请先修正');
                  return;
                }
                if (!editorState.name.trim()) {
                  toast.error('请填写名称');
                  return;
                }
                saveMutation.mutate(editorState);
              }}
            >
              {saveMutation.isPending ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 运行 */}
      <Dialog open={runningWf != null} onOpenChange={(open) => !open && setRunningWf(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>运行：{runningWf?.name}</DialogTitle>
            <DialogDescription>
              inputs 是传给流程的对象（对应 {'{{inputs.x}}'}）。运行同步执行，受节点/总超时约束。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid gap-2">
              <Label htmlFor="wf-inputs">inputs（JSON 对象）</Label>
              <Input
                id="wf-inputs"
                value={runInputsText}
                onChange={(e) => setRunInputsText(e.target.value)}
                className="font-mono text-xs"
                placeholder='{"name": "小 AG"}'
              />
            </div>
            {runMutation.isPending ? (
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3 text-xs font-medium text-[var(--muted-foreground)]">
                执行中…（节点级 60s / 整条流 300s 上限）
              </div>
            ) : null}
            {runResult != null ? (
              <RunResultCard
                run={runResult}
                resumeValueText={resumeValueText}
                onResumeValueChange={setResumeValueText}
                onResume={() => {
                  if (runResult.status !== 'waiting_input') return;
                  let value: unknown = resumeValueText;
                  try {
                    value = JSON.parse(resumeValueText);
                  } catch {
                    // 非合法 JSON 按纯文本回复
                  }
                  resumeMutation.mutate({ runId: runResult.id, value });
                }}
                resuming={resumeMutation.isPending}
              />
            ) : null}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                if (runningWf == null) return;
                let inputs: Record<string, unknown> = {};
                try {
                  inputs = JSON.parse(runInputsText) as Record<string, unknown>;
                } catch {
                  toast.error('inputs 不是合法 JSON');
                  return;
                }
                setRunResult(null);
                setResumeValueText('');
                runMutation.mutate({ id: runningWf.id, inputs });
              }}
              disabled={runMutation.isPending}
            >
              重新运行
            </Button>
            <Button onClick={() => setRunningWf(null)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 运行记录 */}
      <Dialog open={runsFor != null} onOpenChange={(open) => !open && setRunsFor(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>运行记录：{runsFor?.name}</DialogTitle>
            <DialogDescription>最近 50 次；「等待人工输入」的运行可以在此恢复。</DialogDescription>
          </DialogHeader>
          <RunsList
            runs={runsQuery.data?.items ?? []}
            loading={runsQuery.isLoading}
            onResume={(run) => {
              setRunningWf(null);
              setRunResult(run);
              setResumeValueText('');
            }}
          />
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <AlertDialog open={deleting != null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除工作流「{deleting?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              运行记录会一并删除，智能体下次构建时不再挂载该工具。此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleting != null && deleteMutation.mutate(deleting.id)}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function RunResultCard({
  run,
  resumeValueText,
  onResumeValueChange,
  onResume,
  resuming,
}: {
  run: WorkflowRun;
  resumeValueText: string;
  onResumeValueChange: (value: string) => void;
  onResume: () => void;
  resuming: boolean;
}) {
  return (
    <div className="space-y-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3">
      <div className="flex items-center gap-2">
        <StatusPill tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</StatusPill>
        <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
          run #{run.id} · 耗时 {formatTime(run.started_at)}
        </span>
      </div>
      {run.status === 'succeeded' ? (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md bg-[var(--surface-1)] p-2 font-mono text-xs">
          {typeof run.outputs === 'string' ? run.outputs : JSON.stringify(run.outputs, null, 2)}
        </pre>
      ) : null}
      {run.status === 'waiting_input' ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-[var(--foreground)]">
            流程提问：{run.waiting_prompt ?? '（无提示）'}
          </p>
          <div className="flex gap-2">
            <Input
              value={resumeValueText}
              onChange={(e) => onResumeValueChange(e.target.value)}
              placeholder={'答复内容（支持 JSON，如 {"confirmed": true}）'}
              className="font-mono text-xs"
            />
            <Button size="sm" onClick={onResume} disabled={resuming || !resumeValueText.trim()}>
              {resuming ? '恢复中…' : '答复并恢复'}
            </Button>
          </div>
        </div>
      ) : null}
      {run.status === 'failed' ? (
        <p className="text-xs font-medium text-destructive">{run.error}</p>
      ) : null}
      {run.steps && run.steps.length > 0 ? (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold text-[var(--muted-foreground)]">
            步骤轨迹（{run.steps.length}）
          </summary>
          <ul className="mt-1 space-y-1">
            {run.steps.map((s) => (
              <li key={`${s.node_id}-${s.status}`} className="flex items-center gap-2">
                <StatusPill
                  tone={s.status === 'done' ? 'active' : s.status === 'failed' ? 'warning' : 'inactive'}
                >
                  {s.status === 'done' ? '完成' : s.status === 'failed' ? '失败' : '跳过'}
                </StatusPill>
                <span className="font-mono text-[11px]">{s.node_id}</span>
                <span className="text-[11px] text-[var(--muted-foreground)]">{s.duration_ms}ms</span>
                {s.error ? <span className="text-[11px] text-destructive">{s.error}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function RunsList({
  runs,
  loading,
  onResume,
}: {
  runs: WorkflowRun[];
  loading: boolean;
  onResume: (run: WorkflowRun) => void;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <p className="py-4 text-center text-sm font-medium text-[var(--muted-foreground)]">
        还没有运行记录
      </p>
    );
  }
  return (
    <ul className="max-h-80 space-y-2 overflow-auto">
      {runs.map((run) => (
        <li
          key={run.id}
          className="flex items-center justify-between gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <StatusPill tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</StatusPill>
              <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
                #{run.id} · {formatTime(run.started_at)}
              </span>
            </div>
            {run.waiting_prompt ? (
              <p className="mt-0.5 line-clamp-1 text-xs font-medium text-[var(--muted-foreground)]">
                {run.waiting_prompt}
              </p>
            ) : null}
          </div>
          {run.status === 'waiting_input' ? (
            <Button size="sm" variant="outline" onClick={() => onResume(run)}>
              去恢复
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
