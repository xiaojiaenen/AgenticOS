/**
 * 知识库管理：搜索测试 Tab。
 * 展示相关度得分、命中通道与页内最佳片段，便于判断检索质量。
 */
import * as React from 'react';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { toast } from 'sonner';
import { RecallTestPanel } from './RecallTestPanel';
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
import { reindexKnowledgeBase, type SearchResult } from '@/services/knowledgeService';
import { toastError } from '../../lib/errors';

/** 把 0~1 的相关度换算成百分比，三档配色与召回测试报告保持一致 */
function relevanceTone(score: number): { label: string; className: string } {
  const pct = Math.round(score * 100);
  if (pct >= 70) {
    return { label: `${pct}%`, className: 'bg-emerald-100 text-emerald-700' };
  }
  if (pct >= 40) {
    return { label: `${pct}%`, className: 'bg-amber-100 text-amber-700' };
  }
  return { label: `${pct}%`, className: 'bg-[var(--surface-2)] text-[var(--muted-foreground)]' };
}

const CHANNEL_LABEL: Record<string, string> = {
  bm25: '关键词',
  vector: '语义',
  memory: '记忆',
};

export function KnowledgeSearchTab({
  kbId,
  query,
  results,
  isPending,
  onQueryChange,
  onSearch,
}: {
  kbId: number;
  query: string;
  results: SearchResult[];
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onSearch: (query: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && query.trim()) {
              onSearch(query.trim());
            }
          }}
          placeholder="输入查询内容测试检索效果…"
          aria-label="检索查询内容"
        />
        <Button
          onClick={() => query.trim() && onSearch(query.trim())}
          disabled={!query.trim() || isPending}
          aria-label="执行检索"
        >
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </Button>
      </div>

      {results.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-[var(--muted-foreground)]">
            {results.length} 条结果 · 相关度已归一化到 0~100%
          </p>
          {results.map((r) => {
            const tone = relevanceTone(r.score);
            return (
              <div
                key={r.page_id}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm"
              >
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--foreground)]">{r.title}</span>
                  <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs font-medium text-[var(--muted-foreground)]">
                    {r.page_type}
                  </span>
                  {r.matched_by?.map((ch) => (
                    <span
                      key={ch}
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        ch === 'vector'
                          ? 'bg-sky-100 text-sky-700'
                          : 'bg-[var(--surface-2)] text-[var(--muted-foreground)]'
                      }`}
                    >
                      {CHANNEL_LABEL[ch] ?? ch}
                    </span>
                  ))}
                  <span
                    className={`ml-auto rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${tone.className}`}
                    title={`原始相关度 ${r.score.toFixed(4)}`}
                  >
                    {tone.label}
                  </span>
                  <span className="text-xs font-medium text-[var(--muted-foreground)]">
                    {r.authority_level}
                  </span>
                </div>
                <p className="line-clamp-3 text-sm font-medium text-[var(--muted-foreground)]">
                  {r.snippet || r.content}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {results.length === 0 && query && !isPending && (
        <p className="py-8 text-center text-sm font-medium text-[var(--muted-foreground)]">
          无匹配结果，换个说法或降低召回测试里的阈值试试
        </p>
      )}

      <RecallTestPanel kbId={kbId} />

      <VectorIndexCard kbId={kbId} />
    </div>
  );
}

/**
 * 向量索引维护：语义召回依赖页级向量，换过 embedding 模型或导入早期数据后
 * 需要重建；没有这个入口，SQL 里那条 embedding 列永远是空的。
 */
function VectorIndexCard({ kbId }: { kbId: number }) {
  const [pending, setPending] = React.useState<'missing' | 'force' | null>(null);
  const [confirmForce, setConfirmForce] = React.useState(false);
  const [summary, setSummary] = React.useState<string | null>(null);

  const run = async (force: boolean) => {
    setPending(force ? 'force' : 'missing');
    try {
      const stats = await reindexKnowledgeBase(kbId, { force });
      if (!stats.enabled) {
        setSummary(stats.message || '向量检索未启用，本次未做任何处理');
        toast.warning(stats.message || '向量检索未启用');
        return;
      }
      const text = `检查 ${stats.checked} 页，新写入 ${stats.embedded}，跳过 ${stats.skipped}，失败 ${stats.failed}`;
      setSummary(text);
      if (stats.failed > 0) toast.warning(text);
      else toast.success(text);
    } catch (err) {
      toast.error(toastError(err, '重建索引失败'));
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[var(--foreground)]">向量索引</h3>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            语义召回依赖页级向量。导入早期数据或更换 embedding 模型后重建一次，命中率会明显回升。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => run(false)} disabled={pending !== null}>
            {pending === 'missing' ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-1.5 h-4 w-4" />
            )}
            补建缺失
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirmForce(true)} disabled={pending !== null}>
            {pending === 'force' && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            全量重建
          </Button>
        </div>
      </div>
      {summary && <p className="mt-2 text-xs font-medium text-[var(--muted-foreground)]">{summary}</p>}

      <AlertDialog open={confirmForce} onOpenChange={setConfirmForce}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>全量重建向量索引？</AlertDialogTitle>
            <AlertDialogDescription>
              会为所有页面重新调用一次 embedding 接口，耗时和费用随页数线性增长。换过模型时才有必要这么做。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirmForce(false);
                run(true);
              }}
            >
              开始重建
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
