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
import { ChevronLeft, Download, File as FileIcon, Folder, Loader2, RefreshCw } from 'lucide-react';
import { apiFetch } from '../../services/apiClient';
import { useChatStore } from '../../stores/chatStore';
import { collectOutputTabs } from './tabs';
import { isDisplayableOutput, type WorkspaceEntry } from '../../lib/workspaceArtifacts';
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
  const [downloading, setDownloading] = React.useState<string | null>(null);
  const openSidebarTab = useChatStore((s) => s.openSidebarTab);

  /** 通过带鉴权端点下载 outputs/ 下的产物文件（csv/xlsx/json/txt/md/图片）。 */
  const downloadFile = React.useCallback(
    async (entry: Entry) => {
      if (!sessionId) return;
      // /files/workspace 返回相对工作区的路径（如 outputs/data.csv）；
      // 下载端点只认 outputs/ 下的文件名，取最后一段即可。
      const filename = entry.path.split('/').pop() ?? entry.name;
      setDownloading(entry.path);
      try {
        const blob = await apiFetch<Blob>(
          `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/outputs/${encodeURIComponent(filename)}`,
          { responseType: 'blob' },
          '下载文件失败',
        );
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = entry.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // 给浏览器一点时间读取 blob 后再释放
        setTimeout(() => URL.revokeObjectURL(url), 0);
      } catch (err) {
        setError(err instanceof Error ? err.message : '下载失败');
      } finally {
        setDownloading(null);
      }
    },
    [sessionId],
  );

  /** 可展示文件（html/csv/图片等）：点击打开就地预览 tab；其余仍下载。 */
  const openOrDownload = React.useCallback(
    (entry: Entry) => {
      const asWorkspace: WorkspaceEntry = {
        name: entry.name, path: entry.path, type: entry.type, size: entry.size,
      };
      if (isDisplayableOutput(asWorkspace)) {
        const tab = collectOutputTabs([asWorkspace], sessionId)[0];
        if (tab) {
          openSidebarTab(tab);
          return;
        }
      }
      void downloadFile(entry);
    },
    [downloadFile, openSidebarTab, sessionId],
  );

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
              {entry.type === 'dir' ? (
                <button
                  type="button"
                  onClick={() => void load(entry.path)}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-[var(--surface-2)]"
                >
                  <Folder size={14} className="shrink-0 text-amber-500" />
                  <span className="min-w-0 flex-1 truncate text-xs text-[var(--foreground)]">
                    {entry.name}
                  </span>
                </button>
              ) : (
                <div className="group/file flex w-full items-center gap-2 px-3 py-1.5 transition-colors hover:bg-[var(--surface-2)]">
                  <button
                    type="button"
                    onClick={() => openOrDownload(entry)}
                    disabled={downloading === entry.path}
                    title={isDisplayableOutput({ name: entry.name, path: entry.path, type: entry.type, size: entry.size }) ? '点击预览' : '点击下载'}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:opacity-50"
                  >
                    {downloading === entry.path ? (
                      <Loader2 size={14} className="shrink-0 animate-spin text-[var(--muted-foreground)]" />
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
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); void downloadFile(entry); }}
                    disabled={downloading === entry.path}
                    title="下载"
                    aria-label={`下载 ${entry.name}`}
                    className="shrink-0 rounded p-1 text-[var(--muted-foreground)] opacity-60 transition-opacity hover:bg-[var(--surface-3)] hover:opacity-100 disabled:opacity-30"
                  >
                    <Download size={12} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
