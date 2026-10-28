import React from 'react';
import { motion, AnimatePresence, MotionValue } from 'motion/react';
import { Download, LayoutDashboard, Palette, Pencil, Play, RefreshCcw, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Artifact } from '../../types';
import { buildSandboxedHtmlDocument } from '../../lib/safePreview';
import { API_BASE_URL, apiFetch } from '../../services/apiClient';
import { exportPptx, listPptThemes, rethemePpt, getPptPreviewHtml, type PptTheme } from '../../services/agentService';
import { PptPresenterMode } from './PptPresenterMode';
import { ArtifactVersionBar } from '../chat/ArtifactVersionBar';
import { toastError } from '../../lib/errors';

type PptArtifactPanelProps = {
  artifact: Extract<Artifact, { language: 'ppt' }>;
  onClose: () => void;
  borderColor: MotionValue<string>;
  onThemeChange?: (newHtml: string, theme: string) => void;
  /** 切换到历史版本（由版本条调用） */
  onSwitchVersion?: (artifact: Extract<Artifact, { language: 'ppt' }>) => void;
};

export const PptArtifactPanel: React.FC<PptArtifactPanelProps> = ({ artifact, onClose, borderColor, onThemeChange, onSwitchVersion }) => {
  const [isExporting, setIsExporting] = React.useState(false);
  const [isPresenting, setIsPresenting] = React.useState(false);
  const [isOpeningEditor, setIsOpeningEditor] = React.useState(false);
  const [showThemePanel, setShowThemePanel] = React.useState(false);
  const [themes, setThemes] = React.useState<PptTheme[]>([]);
  const [currentTheme, setCurrentTheme] = React.useState(artifact.theme || 'apple');
  const [isChangingTheme, setIsChangingTheme] = React.useState(false);
  const iframeRef = React.useRef<HTMLIFrameElement | null>(null);
  
  // 懒加载：当 html 缺失时按 artifactId 从后端加载
  const [html, setHtml] = React.useState(artifact.html || '');
  const [isLoading, setIsLoading] = React.useState(!artifact.html && !!artifact.artifactId);
  
  React.useEffect(() => {
    if (!html && artifact.artifactId) {
      setIsLoading(true);
      getPptPreviewHtml(artifact.artifactId)
        .then(setHtml)
        .catch(err => {
          console.error('[PPT Preview] Failed to load:', err);
          setHtml('<div style="padding:40px;text-align:center;color:#888;">加载预览失败</div>');
        })
        .finally(() => setIsLoading(false));
    }
  }, [html, artifact.artifactId]);
  
  const previewSrcDoc = React.useMemo(() => buildSandboxedHtmlDocument(html), [html]);

  /**
   * 打开 SVG 编辑器。
   * 后端该端点是 bearer 鉴权的自包含 HTML，直接 window.open 不会带 Authorization
   * 头（必然 401），所以先带鉴权取回内容，再用 blob URL 交给新窗口。
   */
  const openEditor = async () => {
    if (!artifact.artifactId || isOpeningEditor) return;
    setIsOpeningEditor(true);
    try {
      const editorHtml = await apiFetch<string>(
        `${API_BASE_URL}/api/v1/agent/ppt/editor/${artifact.artifactId}`,
        { responseType: 'text' },
        '打开编辑器失败',
      );
      const url = URL.createObjectURL(new Blob([editorHtml], { type: 'text/html;charset=utf-8' }));
      const win = window.open(url, '_blank');
      if (!win) {
        URL.revokeObjectURL(url);
        toast.error('浏览器拦截了新窗口，请允许弹窗后重试');
        return;
      }
      // 等新窗口加载完再回收，过早 revoke 会导致白屏
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      toast.error(toastError(err, '打开编辑器失败'));
    } finally {
      setIsOpeningEditor(false);
    }
  };

  // 加载主题列表
  React.useEffect(() => {
    if (showThemePanel && themes.length === 0) {
      listPptThemes().then(setThemes).catch(console.error);
    }
  }, [showThemePanel, themes.length]);

  const handleExport = async () => {
    setIsExporting(true);

    if (artifact.artifactId) {
      try {
        const blob = await exportPptx(artifact.artifactId);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${artifact.title || 'AgenticOS-PPT'}.pptx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch (err) {
        console.error('[PPTX Export] Backend export error:', err);
      } finally {
        setIsExporting(false);
      }
      return;
    }

    setIsExporting(false);
  };

  const handleThemeChange = async (themeName: string) => {
    if (themeName === currentTheme || isChangingTheme || !artifact.artifactId) return;

    setIsChangingTheme(true);
    try {
      const result = await rethemePpt(artifact.artifactId, themeName);
      setCurrentTheme(themeName);
      onThemeChange?.(result.html, themeName);
    } catch (err) {
      console.error('[Theme Change] Error:', err);
    } finally {
      setIsChangingTheme(false);
    }
  };

  return (
    <>
      <motion.aside
        initial={{ width: 0, opacity: 0 }}
        animate={{ width: '60%', opacity: 1 }}
        exit={{ width: 0, opacity: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-20 flex h-full flex-col overflow-hidden border-l bg-[var(--surface-1)]/70 ring-1 ring-[var(--border-subtle)] backdrop-blur-3xl"
        style={{ borderColor }}
      >
        <div className="z-10 flex h-14 flex-shrink-0 items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-6 backdrop-blur-md">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm">
              <LayoutDashboard size={18} />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold leading-none text-[var(--foreground)]">{artifact.title}</h2>
              <div className="mt-1 flex items-center gap-1.5">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">
                  {artifact.slideCount} slides · native pptx
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <ArtifactVersionBar
              sessionId={artifact.sessionId}
              currentReference={artifact.artifactId}
              kind="ppt"
              onSelect={({ artifact: loaded }) => {
                onSwitchVersion?.({
                  language: 'ppt',
                  artifactId: String(loaded.artifact_id ?? ''),
                  html: String(loaded.html ?? ''),
                  title: String(loaded.title ?? ''),
                  slideCount: Number(loaded.slide_count ?? 0),
                  theme: loaded.theme as string | undefined,
                });
              }}
            />
            <button
              type="button"
              onClick={() => setShowThemePanel(!showThemePanel)}
              className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
                showThemePanel
                  ? 'bg-sky-100 text-sky-700 border border-sky-200'
                  : 'border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] hover:bg-[var(--surface-2)]'
              }`}
              title="切换主题"
              aria-label="切换主题"
            >
              <Palette size={14} />
              主题
            </button>
            <button
              type="button"
              onClick={handleExport}
              disabled={isExporting}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 disabled:opacity-60"
              title="导出 PPTX"
              aria-label="导出 PPTX"
            >
              {isExporting ? <RefreshCcw size={14} className="animate-spin" /> : <Download size={14} />}
              导出
            </button>
            <button
              type="button"
              onClick={() => setIsPresenting(true)}
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
              title="演示模式"
              aria-label="演示模式"
            >
              <Play size={14} />
              演示
            </button>
            {artifact.artifactId && (
              <button
                type="button"
                onClick={() => void openEditor()}
                disabled={isOpeningEditor}
                className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)] disabled:cursor-not-allowed disabled:opacity-60"
                title="编辑幻灯片"
                aria-label="编辑幻灯片"
              >
                {isOpeningEditor ? <Loader2 size={14} className="animate-spin" /> : <Pencil size={14} />}
                编辑
              </button>
            )}
            <div className="mx-2 h-4 w-px bg-[var(--border-medium)]" />
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl p-2 text-[var(--muted-foreground)] transition-all hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-500/15"
              aria-label="关闭演示文稿预览"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        {/* 主题选择面板 - 固定最大高度，可滚动 */}
        <AnimatePresence>
          {showThemePanel && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="z-10 overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/90 backdrop-blur-md"
              style={{ maxHeight: '200px' }}
            >
              <div className="overflow-y-auto p-4" style={{ maxHeight: '200px' }}>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">选择主题</h3>
                  {isChangingTheme && (
                    <div className="flex items-center gap-2 text-xs text-sky-600">
                      <RefreshCcw size={12} className="animate-spin" />
                      切换中...
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-6 gap-2 sm:grid-cols-8 md:grid-cols-10">
                  {themes.map((theme) => (
                    <button
                      key={theme.name}
                      type="button"
                      onClick={() => handleThemeChange(theme.name)}
                      disabled={isChangingTheme}
                      className={`group relative flex flex-col items-center gap-1.5 rounded-lg border-2 p-2 transition-all ${
                        currentTheme === theme.name
                          ? 'border-sky-500 bg-sky-50 shadow-md'
                          : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-[var(--border-strong)] hover:shadow-sm'
                      } ${isChangingTheme ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                    >
                      {/* 主题颜色预览 */}
                      <div className="flex gap-0.5">
                        <div
                          className="h-3 w-3 rounded-full border border-white shadow-sm"
                          style={{ backgroundColor: theme.primary_color }}
                        />
                        <div
                          className="h-3 w-3 rounded-full border border-white shadow-sm"
                          style={{ backgroundColor: theme.bg_color }}
                        />
                        <div
                          className="h-3 w-3 rounded-full border border-white shadow-sm"
                          style={{ backgroundColor: theme.text_color }}
                        />
                      </div>
                      <span className="text-[9px] font-medium text-[var(--muted-foreground)] truncate w-full text-center">{theme.name}</span>
                      {currentTheme === theme.name && (
                        <div className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-sky-500 text-white flex items-center justify-center">
                          <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="z-10 flex-1 overflow-auto p-6">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="min-h-full overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-xl"
          >
            {isLoading ? (
              <div className="flex min-h-[calc(100vh-10rem)] items-center justify-center">
                <div className="flex flex-col items-center gap-3 text-[var(--muted-foreground)]">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="text-sm">加载预览中…</span>
                </div>
              </div>
            ) : (
              <iframe
                ref={iframeRef}
                srcDoc={previewSrcDoc}
                title={artifact.title}
                className="min-h-[calc(100vh-10rem)] w-full border-0"
                sandbox="allow-scripts allow-same-origin"
                allow="fullscreen"
                referrerPolicy="no-referrer"
                style={{ backgroundColor: '#fff' }}
              />
            )}
          </motion.div>
        </div>
      </motion.aside>

      <AnimatePresence>
        {isPresenting && (
          <PptPresenterMode
            html={html}
            slideCount={artifact.slideCount}
            title={artifact.title}
            onClose={() => setIsPresenting(false)}
          />
        )}
      </AnimatePresence>
    </>
  );
};
