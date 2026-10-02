/**
 * 知识库管理：搜索测试 Tab。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { Loader2, Search } from 'lucide-react';
import { RecallTestPanel } from './RecallTestPanel';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import type { SearchResult } from '@/services/knowledgeService';

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
        />
        <Button
          onClick={() => query.trim() && onSearch(query.trim())}
          disabled={!query.trim() || isPending}
        >
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </Button>
      </div>

      {results.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-[var(--muted-foreground)]">{results.length} 条结果</p>
          {results.map((r) => (
            <div key={r.page_id} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-[var(--foreground)]">{r.title}</span>
                <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs font-medium text-[var(--muted-foreground)]">
                  {r.page_type}
                </span>
                <span className="ml-auto text-xs font-medium text-[var(--muted-foreground)]">
                  得分: {r.score.toFixed(3)} · {r.authority_level}
                </span>
              </div>
              <p className="line-clamp-3 text-sm font-medium text-zinc-600">{r.content}</p>
            </div>
          ))}
        </div>
      )}

      {results.length === 0 && query && !isPending && (
        <p className="py-8 text-center text-sm font-medium text-[var(--muted-foreground)]">无匹配结果</p>
      )}
    
      <RecallTestPanel kbId={kbId} />
    </div>
  );
}
