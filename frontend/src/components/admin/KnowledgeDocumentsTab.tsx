/**
 * 知识库管理：文档上传与管理 Tab。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { FileText, Loader2, RotateCw, Trash2, Upload } from 'lucide-react';
import { StatusPill } from './shared';
import { Pagination } from './Pagination';
import { Button } from '@/components/shadcn/button';
import { Skeleton } from '@/components/shadcn/skeleton';
import { cn } from '@/lib/utils';
import type { KBDocument } from '@/services/knowledgeService';
import { docStatusLabel, docStatusTone, formatSize } from './knowledgeHelpers';

export function KnowledgeDocumentsTab({
  documents,
  total,
  page,
  onPageChange,
  isLoading,
  isUploading = false,
  onUpload,
  onDeleteDoc,
  onRecompile,
  recompiling = false,
}: {
  documents: KBDocument[];
  total: number;
  page: number;
  onPageChange: (page: number) => void;
  isLoading: boolean;
  isUploading?: boolean;
  onUpload: (files: File[]) => void;
  onDeleteDoc: (doc: { docId: number; title: string }) => void;
  onRecompile?: (docId: number) => void;
  recompiling?: boolean;
}) {
  // 服务端分页：数据由父组件按 page 请求，这里只渲染 + 统一 Pagination
  const pageSize = 10;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-3">
      <label
        className={cn(
          'flex items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-300 bg-[var(--surface-1)] py-6 text-sm font-medium transition',
          isUploading
            ? 'cursor-not-allowed opacity-60'
            : 'cursor-pointer hover:border-zinc-900 hover:text-zinc-700',
        )}
      >
        {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {isUploading ? '上传中…' : '点击上传文档（可多选）'}
        <input
          type="file"
          className="hidden"
          accept=".pdf,.docx,.md,.markdown,.html,.htm,.txt"
          multiple
          disabled={isUploading}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) onUpload(files);
            e.target.value = '';
          }}
        />
      </label>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <p className="py-8 text-center text-sm font-medium text-[var(--muted-foreground)]">暂无文档</p>
      ) : (
        documents.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 shadow-sm"
          >
            <div className="flex min-w-0 items-center gap-3">
              <FileText className="h-4 w-4 shrink-0 text-[var(--muted-foreground)]" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-[var(--foreground)]">{doc.title}</p>
                <p className="text-xs font-medium text-[var(--muted-foreground)]">
                  {doc.file_type.toUpperCase()} · {formatSize(doc.file_size)}
                </p>
                {doc.status === 'failed' && (
                  <p className="mt-1 truncate text-[11px] text-rose-500" title={doc.error_message || ''}>
                    失败原因：{doc.error_message || '未知错误'}
                  </p>
                )}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <StatusPill tone={docStatusTone(doc.status)}>{docStatusLabel(doc.status)}</StatusPill>
              {doc.status === 'failed' && onRecompile && (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  disabled={recompiling}
                  onClick={() => onRecompile(doc.id)}
                  aria-label={`重新编译 ${doc.title}`}
                  title="重新编译"
                >
                  <RotateCw className={cn('h-3.5 w-3.5', recompiling && 'animate-spin')} />
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon-xs"
                className="text-rose-500 hover:bg-rose-50 hover:text-rose-600"
                onClick={() => onDeleteDoc({ docId: doc.id, title: doc.title })}
                aria-label={`删除文档 ${doc.title}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        ))
      )}
      {total > pageSize && (
        <Pagination
          currentPage={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
          totalLabel={`共 ${total} 条`}
        />
      )}
    </div>
  );
}
