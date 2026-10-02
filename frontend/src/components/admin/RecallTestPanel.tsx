/**
 * 知识库召回测试。
 *
 * 借鉴 Dify / Cherry Studio 的做法：用一组问题跑批检索，报告命中率与
 * 平均命中排名。价值是让"改切片/改 TopK/改阈值"从试错变成可复现的回归。
 */
import { useState } from 'react';
import { AlertCircle, FlaskConical, Loader2 } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { cn } from '@/lib/utils';
import { runRecallTest, type RecallReport } from '@/services/knowledgeService';

export function RecallTestPanel({ kbId }: { kbId: number }) {
  const [questionsText, setQuestionsText] = useState('');
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState('');
  const [report, setReport] = useState<RecallReport | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setIsPending(true);
    setError(null);
    try {
      const questions = questionsText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      const data = await runRecallTest(kbId, {
        questions,
        topK,
        scoreThreshold: threshold ? Number(threshold) : undefined,
      });
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '召回测试失败');
      setReport(null);
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="space-y-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
            <FlaskConical className="h-4 w-4 text-violet-500" />
            召回测试
          </h3>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            一行一个问题，跑完给出命中率与平均命中排名。留空则用本页标题自动生成探针。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
            Top K
            <Input
              value={String(topK)}
              onChange={(e) => setTopK(Math.max(1, Math.min(50, Number(e.target.value) || 5)))}
              className="h-8 w-14 text-center"
              inputMode="numeric"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
            阈值
            <Input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="留空=不过滤"
              className="h-8 w-20"
              inputMode="decimal"
            />
          </label>
        </div>
      </div>

      <textarea
        value={questionsText}
        onChange={(e) => setQuestionsText(e.target.value)}
        rows={3}
        placeholder={'例如：\n数据库备份保留多久\n差旅报销标准是什么'}
        className="w-full resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm outline-none transition-colors focus:border-brand-400"
      />

      <div className="flex items-center justify-between gap-3">
        <Button onClick={handleRun} disabled={isPending} size="sm">
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
          运行测试
        </Button>
        {report && (
          <p className="text-xs text-[var(--muted-foreground)]">
            参数：Top K={report.params.top_k}
            {report.params.score_threshold != null && `，阈值=${report.params.score_threshold}`}
          </p>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {report && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-semibold text-[var(--foreground)]">
              命中 {report.matched} / {report.total}
            </span>
            <span
              className={cn(
                'rounded-full px-2.5 py-1 text-xs font-semibold',
                report.hit_rate >= 0.8
                  ? 'bg-emerald-100 text-emerald-700'
                  : report.hit_rate >= 0.5
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-rose-100 text-rose-700',
              )}
            >
              命中率 {(report.hit_rate * 100).toFixed(0)}%
            </span>
            {report.avg_rank != null && (
              <span className="text-xs text-[var(--muted-foreground)]">
                平均命中排名 #{report.avg_rank.toFixed(1)}
              </span>
            )}
          </div>

          <div className="space-y-2">
            {report.cases.map((c, index) => (
              <div
                key={index}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-[var(--foreground)]">{c.question}</span>
                  <span
                    className={cn(
                      'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold',
                      c.matched
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-rose-100 text-rose-700',
                    )}
                  >
                    {c.matched
                      ? `第 ${c.rank_of_first_expected} 位命中`
                      : '未命中'}
                  </span>
                </div>
                {c.hits.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5">
                    {c.hits.slice(0, 3).map((hit, i) => (
                      <li
                        key={hit.page_id ?? i}
                        className="flex items-center justify-between gap-2 text-[11px] text-[var(--muted-foreground)]"
                      >
                        <span className="truncate">
                          {i + 1}. {hit.title}
                        </span>
                        <span className="shrink-0 tabular-nums">{hit.score.toFixed(3)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}