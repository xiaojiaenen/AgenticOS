import React from 'react';
import { motion } from 'motion/react';
import { CheckCircle2, Globe, Loader2, RefreshCcw, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { apiFetch } from '../../services/apiClient';
import { toastError } from '../../lib/errors';

export type PublishedKind = 'ppt' | 'document' | 'sheet';

export type PublishedItemRecord = {
  id: number;
  kind: string;
  kind_label?: string;
  title: string;
  description?: string;
  status: string;
  source_ref?: string;
  short_code?: string | null;
  short_url?: string | null;
  reason?: string | null;
};

const STATUS_TEXT: Record<string, string> = {
  pending: '发布申请已提交，等待管理员审批',
  approved: '审批已通过，正在生成发布文件',
  deployed: '已发布到作品库',
  rejected: '发布申请已被拒绝',
  cancelled: '已取消发布',
  failed: '发布失败',
};

/**
 * 「公开到作品库」按钮 —— PPT / 文档 / 表格共用。
 *
 * 文件型作品只能公开（用户明确要求）：没有服务端运行时，泄露即等于公开。
 * 因此这里不提供可见性选择，只提供标题与说明。
 */
export const PublishToGalleryButton: React.FC<{
  kind: PublishedKind;
  sessionId: string;
  /** 产物标识：PPT 是 artifact_id；文档/表格是版本目录名 */
  sourceRef: string;
  title: string;
  onPublished?: (record: PublishedItemRecord) => void;
}> = ({ kind, sessionId, sourceRef, title, onPublished }) => {
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [status, setStatus] = React.useState<string | null>(null);
  const [itemTitle, setItemTitle] = React.useState(title);
  const [description, setDescription] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // 轮询审批状态：申请是异步的（管理员审批 → 后端导出文件）
    const timer = setInterval(async () => {
      try {
        const data = await apiFetch<{ items: PublishedItemRecord[] }>(
          '/api/v1/published-items',
          {},
          '查询发布状态失败',
        );
        if (cancelled) return;
        const mine = data.items.find(
          (i) => i.kind === kind && i.source_ref === sourceRef,
        );
        if (mine) {
          setStatus(mine.status);
          if (mine.status === 'deployed' || mine.status === 'rejected' || mine.status === 'failed') {
            clearInterval(timer);
            onPublished?.(mine);
          }
        }
      } catch {
        // 单次失败不打断
      }
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [open, kind, sourceRef, onPublished]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const record = await apiFetch<PublishedItemRecord>(
        '/api/v1/published-items',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            kind,
            session_id: sessionId,
            source_ref: sourceRef,
            title: itemTitle.trim(),
            description: description.trim(),
          }),
        },
        '提交发布申请失败',
      );
      setStatus(record.status);
      toast.success('发布申请已提交，等待管理员审批');
      onPublished?.(record);
    } catch (err) {
      const msg = toastError(err, '提交发布申请失败');
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const statusTone =
    status === 'deployed'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-400'
      : status === 'rejected' || status === 'failed'
        ? 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-400'
        : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-400';

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={busy}
        className="inline-flex items-center gap-2 rounded-xl bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 disabled:opacity-60"
        title="公开到作品库（需管理员审批）"
        aria-label="公开到作品库"
      >
        {busy ? (
          <RefreshCcw size={14} className="animate-spin" />
        ) : (
          <Globe size={14} />
        )}
        公开
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="w-[min(92%,420px)] rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-2xl"
          >
            <h3 className="mb-1 text-sm font-semibold text-[var(--foreground)]">公开到作品库</h3>
            <p className="mb-3 text-xs leading-relaxed text-[var(--muted-foreground)]">
              文件型作品只能公开：管理员审批通过后会生成可下载的文件并出现在作品库。
            </p>

            <label className="mb-3 block">
              <span className="mb-1.5 block text-[11px] font-semibold text-[var(--foreground)]">
                作品名
              </span>
              <input
                type="text"
                value={itemTitle}
                onChange={(e) => setItemTitle(e.target.value)}
                maxLength={200}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none transition-colors focus-visible:border-[var(--ring)]"
              />
            </label>

            <label className="mb-3 block">
              <span className="mb-1.5 block text-[11px] font-semibold text-[var(--foreground)]">
                作品说明
              </span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={500}
                rows={3}
                placeholder="一句话介绍这个作品。管理员审批时能看到，作品库卡片上也会展示。"
                className="w-full resize-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-sm leading-relaxed outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus-visible:border-[var(--ring)]"
              />
            </label>

            {status && (
              <div
                className={`mb-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-[11px] font-semibold ${statusTone}`}
              >
                {status === 'deployed' ? (
                  <CheckCircle2 size={13} />
                ) : status === 'rejected' || status === 'failed' ? (
                  <XCircle size={13} />
                ) : (
                  <Loader2 size={13} className="animate-spin" />
                )}
                <span className="min-w-0 flex-1 truncate">
                  {STATUS_TEXT[status] ?? status}
                </span>
              </div>
            )}

            {error && (
              <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-400">
                {error}
              </div>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                关闭
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={busy || !itemTitle.trim() || status === 'deployed'}
                className="rounded-lg bg-[var(--primary)] px-3.5 py-1.5 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 disabled:opacity-60"
              >
                {busy ? '提交中…' : status === 'deployed' ? '已发布' : '提交发布申请'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </>
  );
};

export default PublishToGalleryButton;
