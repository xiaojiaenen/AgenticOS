/**
 * 知识库管理：文档上传与管理 Tab。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { FileText, Trash2, Upload } from 'lucide-react';
import { StatusPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Skeleton } from '@/components/shadcn/skeleton';
import type { KBDocument } from '@/services/knowledgeService';
import { docStatusLabel, docStatusTone, formatSize } from './knowledgeHelpers';

export function KnowledgeDocumentsTab({
  documents,
  isLoading,
  onUpload,
  onDeleteDoc,
}: {
  documents: KBDocument[];
  isLoading: boolean;
  onUpload: (file: File) => void;
  onDeleteDoc: (doc: { docId: number; title: string }) => void;
}) {
  return (
    <div className="space-y-3">
      <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-300 bg-[var(--surface-1)] py-6 text-sm font-medium text-[var(--muted-foreground)] transition hover:border-indigo-300 hover:text-indigo-600">
        <Upload className="h-4 w-4" />
        点击上传文档（PDF / Word / Markdown）
        <input
          type="file"
          className="hidden"
          accept=".pdf,.docx,.md,.html,.txt"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(file);
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
            <div className="flex items-center gap-3">
              <FileText className="h-4 w-4 text-[var(--muted-foreground)]" />
              <div>
                <p className="text-sm font-medium text-[var(--foreground)]">{doc.title}</p>
                <p className="text-xs font-medium text-[var(--muted-foreground)]">
                  {doc.file_type.toUpperCase()} · {formatSize(doc.file_size)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <StatusPill tone={docStatusTone(doc.status)}>{docStatusLabel(doc.status)}</StatusPill>
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
    </div>
  );
}
