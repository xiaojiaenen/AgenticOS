/**
 * 文件面板：浏览会话工作区的文件树。
 *
 * 为什么放在右侧栏：网站/办公场景里用户最常问「刚才那个文件在哪」，
 * 此前只能靠对话里的路径字符串去猜。文件树把工作区直接摊开。
 *
 * 安全：后端 `/files/workspace` 限定在 `data/workspaces/u<uid>/s<sid>/`
 * 之内，`..` 逃逸会被 400 拒绝 —— 前端不做也不应做自己的路径校验。
 */
import * as React from 'react';
import { ChevronLeft, File as FileIcon, Folder, Loader2, RefreshCw } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiFetch } from '../../services/apiClient';
import type { SessionPanelProps } from './types';

type Entry = { name: string; path: string; type: 'dir' | 'file'; size: number | null };

function formatSize(size: number | null): string {
  if (size == null) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export const FilesPanel: React.FC<SessionPanelProps> = ({ sessionId }) => {
  const [path, setPath] = React.useState('');
  const [entries, setEntries] = React.useState<Entry[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [rootExists, setRootExists] = React.useState(true);

  const load = React.useCallback(
    async (nextPath: string) => {
      if (!sessionId) {
        setError('缺少会话 ID');
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<{
          path: string;
          entries: Entry[];
          root_exists: boolean;
        }>(
          `/api/v1/files/workspace?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(nextPath)}`,
          {},
          '加载文件列表失败',
        );
        setEntries(data.entries ?? []);
        setRootExists(data.root_exists);
        setPath(data.path ?? '');
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        setLoading(false);
      }
    },
    [sessionId],
  );

  React.useEffect(() => {
    void load('');
  }, [load]);

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-[var(--muted-foreground)]">
        请先打开一个会话
      </div>
    );
  }

  if (!rootExists) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <Folder size={20} className="text-[var(--muted-foreground)]" />
        <p className="text-sm font-medium text-[var(--muted-foreground)]">工作区还是空的</p>
        <p className="text-xs text-[var(--muted-foreground)]">
          智能体生成文件或你上传附件后，这里会显示出来
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* 面包屑 / 返回 */}
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2">
        {path ? (
          <button
            type="button"
            onClick={() => {
              const parent = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
              void load(parent);
            }}
            className="rounded-md p-1 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)]"
            aria-label="返回上级"
          >
            <ChevronLeft size={14} />
          </button>
        ) : null}
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--muted-foreground)]">
          /{path}
        </span>
        <button
          type="button"
          onClick={() => void load(path)}
          disabled={loading}
          className="rounded-md p-1 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] disabled:opacity-50"
          aria-label="刷新"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : undefined} />
        </button>
      </div>

      {error ? (
        <p className="px-3 py-4 text-xs text-rose-600 dark:text-rose-400">{error}</p>
      ) : loading && entries.length === 0 ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 size={16} className="animate-spin text-[var(--muted-foreground)]" />
        </div>
      ) : entries.length === 0 ? (
        <p className="px-3 py-10 text-center text-xs text-[var(--muted-foreground)]">空目录</p>
      ) : (
        <ul className="flex flex-col py-1">
          {entries.map((entry) => (
            <li key={entry.path}>
              <button
                type="button"
                onClick={() => {
                  if (entry.type === 'dir') void load(entry.path);
                }}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors',
                  entry.type === 'dir'
                    ? 'hover:bg-[var(--surface-2)]'
                    : 'cursor-default',
                )}
              >
                {entry.type === 'dir' ? (
                  <Folder size={14} className="shrink-0 text-amber-500" />
                ) : (
                  <FileIcon size={14} className="shrink-0 text-[var(--muted-foreground)]" />
                )}
                <span className="min-w-0 flex-1 truncate text-xs text-[var(--foreground)]">
                  {entry.name}
                </span>
                {entry.size != null ? (
                  <span className="shrink-0 text-[10px] tabular-nums text-[var(--muted-foreground)]">
                    {formatSize(entry.size)}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
