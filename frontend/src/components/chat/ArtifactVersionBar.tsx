/**
 * 产物版本切换条。
 *
 * 后端每轮产物生成都会留版本（PPT 走 ppt_artifacts 表，网站走每轮快照），
 * 这里把版本列表拉下来并支持回看。数据源：
 *   GET /agent/sessions/{id}/versions
 *   GET /agent/sessions/{id}/versions/{kind}/{reference}
 */
import React from 'react';
import { History, Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../shadcn/tooltip';
import {
  listSessionVersions,
  loadArtifactVersion,
  type ArtifactKind,
  type ArtifactVersion,
} from '../../services/agentService';

interface ArtifactVersionBarProps {
  sessionId?: string;
  /** 当前打开的产物引用：PPT 为 artifactId，网站为 v{n} */
  currentReference?: string;
  /** 当前产物类型；undefined 表示当前没有产物 */
  kind?: ArtifactKind;
  onSelect: (payload: { kind: ArtifactKind; artifact: Record<string, unknown> }) => void;
  className?: string;
}

function formatTime(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? `今天 ${date.toTimeString().slice(0, 5)}`
    : `${date.getMonth() + 1}/${date.getDate()} ${date.toTimeString().slice(0, 5)}`;
}

const KIND_BADGE: Record<
  ArtifactKind,
  { label: string; className: string }
> = {
  ppt: { label: 'PPT', className: 'bg-amber-500/15 text-amber-600 dark:text-amber-300' },
  website: { label: '网站', className: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' },
  sheet: { label: '表格', className: 'bg-sky-500/15 text-sky-600 dark:text-sky-300' },
};

export const ArtifactVersionBar: React.FC<ArtifactVersionBarProps> = ({
  sessionId,
  currentReference,
  kind,
  onSelect,
  className,
}) => {
  const [versions, setVersions] = React.useState<ArtifactVersion[]>([]);
  const [isOpen, setIsOpen] = React.useState(false);
  const [loadingRef, setLoadingRef] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    listSessionVersions(sessionId)
      .then((res) => {
        if (!cancelled) setVersions(res.versions ?? []);
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      });
    return () => {
      cancelled = true;
    };
    // currentReference 也要进依赖：同一会话里再生成一版时 sessionId 不变，
    // 但版本列表多了一项。只依赖 sessionId 会让版本条停留在首次挂载时的快照，
    // 新版本永远不出现（表格面板常驻不卸载，所以必然踩到）。
  }, [sessionId, currentReference]);

  // 切换会话时收起面板，避免显示上一个会话的版本
  React.useEffect(() => {
    setIsOpen(false);
  }, [sessionId]);

  if (!sessionId || versions.length === 0) return null;

  const sameKind = versions.filter((v) => v.kind === kind);
  // 该会话只有一种产物时，不必显示（没有对比价值）
  if (versions.length < 2 && sameKind.length < 2) return null;

  const handleSelect = async (version: ArtifactVersion) => {
    const ref = version.reference;
    if (!ref || ref === currentReference) {
      setIsOpen(false);
      return;
    }
    setLoadingRef(ref);
    setError(null);
    try {
      const payload = await loadArtifactVersion(sessionId, version.kind, ref);
      if (version.kind === 'ppt' && payload.ppt_artifact) {
        onSelect({ kind: 'ppt', artifact: payload.ppt_artifact as Record<string, unknown> });
      } else if (version.kind === 'website' && payload.website_artifact) {
        onSelect({ kind: 'website', artifact: payload.website_artifact as Record<string, unknown> });
      } else if (version.kind === 'sheet' && payload.sheet_artifact) {
        onSelect({ kind: 'sheet', artifact: payload.sheet_artifact as Record<string, unknown> });
      }
      setIsOpen(false);
    } catch {
      setError('该版本加载失败');
    } finally {
      setLoadingRef(null);
    }
  };

  return (
    <TooltipProvider delayDuration={250} skipDelayDuration={400}>
    <div className={cn('relative', className)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => setIsOpen((v) => !v)}
            className={cn(
              'flex h-8 items-center gap-1.5 rounded-lg px-2 text-[11px] font-semibold transition-all duration-200 active:scale-95',
              isOpen
                ? 'bg-[var(--surface-2)] text-[var(--foreground)]'
                : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
            )}
            aria-label="查看历史版本"
            aria-expanded={isOpen}
          >
            <History size={14} />
            版本
            {versions.length > 1 && (
              <span className="rounded-md bg-[var(--surface-2)] px-1.5 text-[10px] tabular-nums">
                {versions.length}
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          查看历史版本
        </TooltipContent>
      </Tooltip>

      {isOpen && (
        <>
          {/* 点击外部关闭 */}
          <button
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setIsOpen(false)}
            aria-hidden
            tabIndex={-1}
          />
          <div className="absolute right-0 top-10 z-50 w-72 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-xl">
            <div className="border-b border-[var(--border-subtle)] px-3 py-2 text-[11px] font-semibold text-[var(--muted-foreground)]">
              历史版本（{versions.length}）
            </div>
            <div className="max-h-72 overflow-y-auto py-1">
              {versions.map((version) => {
                const isCurrent = version.reference === currentReference;
                const isLoading = loadingRef === version.reference;
                return (
                  <button
                    key={`${version.kind}-${version.reference}`}
                    onClick={() => handleSelect(version)}
                    disabled={isLoading}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-[var(--surface-2)] disabled:opacity-60',
                      isCurrent && 'bg-[var(--surface-2)]',
                    )}
                  >
                    <span
                      className={cn(
                        'shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase',
                        KIND_BADGE[version.kind].className,
                      )}
                    >
                      {KIND_BADGE[version.kind].label}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-[var(--foreground)]">
                        {version.title || `v${version.version}`}
                        {isCurrent && <span className="ml-1.5 text-[10px] text-[var(--muted-foreground)]">（当前）</span>}
                      </span>
                      <span className="block text-[10px] text-[var(--muted-foreground)]">
                        v{version.version}
                        {version.kind === 'ppt' && version.slide_count ? ` · ${version.slide_count} 页` : ''}
                        {version.created_at ? ` · ${formatTime(version.created_at)}` : ''}
                      </span>
                    </span>
                    {isLoading && <Loader2 size={13} className="shrink-0 animate-spin" />}
                  </button>
                );
              })}
            </div>
            {error && (
              <div className="border-t border-[var(--border-subtle)] px-3 py-2 text-[11px] text-rose-600">
                {error}
              </div>
            )}
          </div>
        </>
      )}
    </div>
    </TooltipProvider>
  );;
};