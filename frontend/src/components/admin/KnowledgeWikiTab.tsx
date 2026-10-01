/**
 * 知识库管理：Wiki 页面浏览 Tab。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { BookOpen, ChevronRight, Eye, Loader2 } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import type { WikiPage } from '@/services/knowledgeService';

export function KnowledgeWikiTab({
  pages,
  isLoading,
  selectedPage,
  onSelectPage,
}: {
  pages: WikiPage[];
  isLoading: boolean;
  selectedPage: WikiPage | null;
  onSelectPage: (page: WikiPage | null) => void;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-[var(--muted-foreground)]">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (selectedPage) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" className="gap-1" onClick={() => onSelectPage(null)}>
          <ChevronRight className="h-4 w-4 rotate-180" />
          返回列表
        </Button>
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-6 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <h3 className="text-lg font-semibold text-[var(--foreground)]">{selectedPage.title}</h3>
            <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs font-medium text-[var(--muted-foreground)]">
              {selectedPage.page_type}
            </span>
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
              {selectedPage.authority_level}
            </span>
          </div>
          <pre className="whitespace-pre-wrap rounded-lg border border-zinc-100 bg-[var(--surface-2)] p-4 font-mono text-sm leading-relaxed text-zinc-700">
            {selectedPage.content}
          </pre>
          {selectedPage.sources.length > 0 && (
            <div className="mt-4 text-xs font-medium text-[var(--muted-foreground)]">
              来源: {selectedPage.sources.join(', ')}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (pages.length === 0) {
    return (
      <p className="py-8 text-center text-sm font-medium text-[var(--muted-foreground)]">
        暂无 Wiki 页面。上传文档后系统将自动编译生成。
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {pages.map((page) => (
        <button
          key={page.id}
          onClick={() => onSelectPage(page)}
          className="flex w-full items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 text-left shadow-sm transition hover:border-zinc-300 hover:bg-[var(--surface-2)]"
        >
          <div className="flex items-center gap-3">
            <BookOpen className="h-4 w-4 text-[var(--muted-foreground)]" />
            <div>
              <p className="text-sm font-medium text-[var(--foreground)]">{page.title}</p>
              <p className="text-xs font-medium text-[var(--muted-foreground)]">{page.page_type}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
              {page.authority_level}
            </span>
            <Eye className="h-4 w-4 text-[var(--muted-foreground)]" />
          </div>
        </button>
      ))}
    </div>
  );
}
