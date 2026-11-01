/**
 * 运行追踪面板（LLMOps）：一次 agent run 的步骤瀑布。
 *
 * 数据来自 agent_run_traces —— orchestrator 在事件循环里同步采集
 * （工具开始/结束、HITL、产物、token、时长），run 结束落库一行。
 * 列表选一条看瀑布：每步一条横条（按时间比例定位），可展开看参数/输出摘要。
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Bot, ChevronDown, ChevronRight, Clock, Gauge, Loader2, ShieldQuestion, Wrench } from 'lucide-react';
import { ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts';
import { getTrace, getTraceTrend, listTraces, type TraceStep, type TraceSummary, type TraceTrendPoint } from '../../services/llmopsService';
import { toastError } from '../../lib/errors';

const STEP_META: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  tool_start: { color: 'bg-sky-400', icon: <Wrench size={13} />, label: '工具' },
  tool_end: { color: 'bg-emerald-400', icon: <Wrench size={13} />, label: '完成' },
  tool_error: { color: 'bg-rose-400', icon: <AlertTriangle size={13} />, label: '出错' },
  error: { color: 'bg-rose-500', icon: <AlertTriangle size={13} />, label: '失败' },
  hitl: { color: 'bg-amber-400', icon: <ShieldQuestion size={13} />, label: '审批' },
  artifact: { color: 'bg-violet-400', icon: <Bot size={13} />, label: '产物' },
};

function stepMeta(kind: string) {
  return STEP_META[kind] ?? { color: 'bg-slate-300', icon: <Clock size={13} />, label: kind };
}

const StatusBadge = ({ status }: { status: TraceSummary['status'] }) => {
  const map = {
    done: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    running: 'bg-sky-50 text-sky-700 border-sky-200',
    error: 'bg-rose-50 text-rose-700 border-rose-200',
  } as const;
  const label = { done: '完成', running: '进行中', error: '失败' }[status];
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${map[status]}`}>{label}</span>;
};

const WaterfallRow = ({ step, totalMs }: { step: TraceStep; totalMs: number }) => {
  const [open, setOpen] = useState(false);
  const meta = stepMeta(step.kind);
  const left = totalMs > 0 ? Math.min(100, (step.ts_ms / totalMs) * 100) : 0;
  return (
    <div className="border-b border-[var(--border-subtle)] last:border-0">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-[var(--surface-2)]"
        onClick={() => setOpen((prev) => !prev)}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded ${meta.color} bg-opacity-15 text-[var(--foreground)]`}>
          {meta.icon}
        </span>
        <span className="w-14 shrink-0 text-xs text-[var(--muted-foreground)]">
          {(step.ts_ms / 1000).toFixed(1)}s
        </span>
        <span className="w-40 shrink-0 truncate text-sm font-medium">{step.name || meta.label}</span>
        <span className="relative h-1.5 flex-1 rounded-full bg-[var(--surface-2)]">
          <span
            className={`absolute inset-y-0 left-0 rounded-full ${meta.color}`}
            style={{ width: `${Math.max(1.5, left)}%` }}
          />
        </span>
      </button>
      {open && step.detail && (
        <pre className="mx-3 mb-2 max-h-44 overflow-auto whitespace-pre-wrap break-all rounded-md bg-[var(--surface-2)] p-2 text-xs leading-relaxed text-[var(--muted-foreground)]">
          {step.detail}
        </pre>
      )}
    </div>
  );
};

const TrendChart = ({ days }: { days: number }) => {
  const trendQuery = useQuery({
    queryKey: ['llmops', 'trend', days],
    queryFn: () => getTraceTrend(days),
    refetchInterval: 30000,
  });
  const data: TraceTrendPoint[] = trendQuery.data?.items ?? [];
  if (trendQuery.isLoading) {
    return <div className="flex h-40 items-center justify-center"><Loader2 className="animate-spin" /></div>;
  }
  if (data.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-[var(--muted-foreground)]">
        ?? {days} ????????
      </div>
    );
  }
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} tickFormatter={(v: string) => v.slice(5)} />
          <YAxis yAxisId="runs" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
          <YAxis yAxisId="ms" orientation="right" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} />
          <Tooltip
            contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border-subtle)', borderRadius: 8, fontSize: 12 }}
            formatter={(value, name) => [
              String(name).includes('??') ? `${(Number(value) / 1000).toFixed(1)}s` : String(value),
              String(name),
            ] as [string, string]}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar yAxisId="runs" dataKey="runs" name="????" fill="#2b87c2" radius={[3, 3, 0, 0]} barSize={18} />
          <Bar yAxisId="runs" dataKey="errors" name="??" fill="#f43f5e" radius={[3, 3, 0, 0]} barSize={18} />
          <Line yAxisId="ms" dataKey="avg_latency_ms" name="????" stroke="#10b981" strokeWidth={2} dot={false} />
          <Line yAxisId="ms" dataKey="p95_latency_ms" name="P95 ??" stroke="#f59e0b" strokeWidth={2} strokeDasharray="4 3" dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

export const TracePanel = () => {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [trendDays, setTrendDays] = useState(7);

  const listQuery = useQuery({
    queryKey: ['llmops', 'traces'],
    queryFn: () => listTraces({ limit: 50 }),
    refetchInterval: 15000,
  });

  const detailQuery = useQuery({
    queryKey: ['llmops', 'trace', selectedId],
    queryFn: () => getTrace(selectedId!),
    enabled: selectedId !== null,
  });

  if (listQuery.isLoading) {
    return <div className="flex h-40 items-center justify-center"><Loader2 className="animate-spin" /></div>;
  }
  if (listQuery.isError) {
    return <div className="p-4 text-sm text-rose-600">{toastError(listQuery.error, '加载失败')}</div>;
  }

  const traces = listQuery.data?.items ?? [];
  const detail = detailQuery.data;
  const totalMs = detail?.latency_ms ?? 0;

  return (
    <div className="space-y-4">
    <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">????</h3>
        <div className="flex gap-1">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              type="button"
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                trendDays === d ? 'bg-[#2b87c2] text-white' : 'bg-[var(--surface-2)] text-[var(--muted-foreground)]'
              }`}
              onClick={() => setTrendDays(d)}
            >
              {d} ?
            </button>
          ))}
        </div>
      </div>
      <TrendChart days={trendDays} />
    </div>
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <h3 className="text-sm font-semibold">运行记录</h3>
          <span className="text-xs text-[var(--muted-foreground)]">共 {listQuery.data?.total ?? 0} 次</span>
        </div>
        <div className="max-h-[560px] overflow-y-auto">
          {traces.length === 0 && (
            <div className="p-6 text-center text-sm text-[var(--muted-foreground)]">
              还没有运行记录 —— 对话一次后这里会出现每次运行的完整步骤瀑布
            </div>
          )}
          {traces.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`flex w-full flex-col gap-1 border-b border-[var(--border-subtle)] px-4 py-3 text-left hover:bg-[var(--surface-2)] ${
                selectedId === t.id ? 'bg-[var(--surface-2)]' : ''
              }`}
              onClick={() => setSelectedId(t.id)}
            >
              <div className="flex w-full items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">
                  {t.mode} · #{t.id}
                </span>
                <StatusBadge status={t.status} />
              </div>
              <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
                <span className="inline-flex items-center gap-1">
                  <Gauge size={11} /> {(t.latency_ms / 1000).toFixed(1)}s
                </span>
                <span>工具 {t.tool_calls}</span>
                <span>token {t.input_tokens + t.output_tokens}</span>
              </div>
              {t.error && <div className="truncate text-xs text-rose-600">{t.error}</div>}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] shadow-sm">
        <div className="border-b border-[var(--border-subtle)] px-4 py-3">
          <h3 className="text-sm font-semibold">步骤瀑布</h3>
        </div>
        {!detail ? (
          <div className="flex h-64 items-center justify-center text-sm text-[var(--muted-foreground)]">
            左侧选择一次运行查看完整步骤
          </div>
        ) : detailQuery.isLoading ? (
          <div className="flex h-40 items-center justify-center"><Loader2 className="animate-spin" /></div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 px-4 py-2 text-xs text-[var(--muted-foreground)]">
              <StatusBadge status={detail.status} />
              <span>会话 {detail.session_id}</span>
              <span>文本 {detail.text_chars} 字</span>
              <span>思考 {detail.reasoning_chars} 字</span>
              <span>工具 {detail.tool_calls} 次</span>
              <span>token {detail.input_tokens}+{detail.output_tokens}</span>
              <span className="inline-flex items-center gap-1">
                <Clock size={11} /> {(detail.latency_ms / 1000).toFixed(1)}s
              </span>
            </div>
            {detail.error && (
              <div className="mx-4 mb-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {detail.error}
              </div>
            )}
            <div className="max-h-[520px] overflow-y-auto">
              {(detail.steps ?? []).length === 0 ? (
                <div className="p-6 text-center text-sm text-[var(--muted-foreground)]">该次运行没有记录到步骤</div>
              ) : (
                (detail.steps ?? []).map((step, i) => (
                  <WaterfallRow key={`${step.ts_ms}-${i}`} step={step} totalMs={totalMs} />
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
    </div>
  );
};

export default TracePanel;
