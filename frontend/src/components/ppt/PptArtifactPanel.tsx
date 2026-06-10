import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Download, LayoutDashboard, Palette, Pencil, Play, RefreshCcw, X } from 'lucide-react';
import { MotionValue } from 'motion/react';
import { Artifact } from '../../types';
import { buildSandboxedHtmlDocument } from '../../lib/safePreview';
import { exportPptx, listPptThemes, rethemePpt, type PptTheme } from '../../services/agentService';
import { PptPresenterMode } from './PptPresenterMode';

type PptArtifactPanelProps = {
  artifact: Extract<Artifact, { language: 'ppt' }>;
  onClose: () => void;
  borderColor: MotionValue<string>;
  onThemeChange?: (newHtml: string, theme: string) => void;
};

export const PptArtifactPanel: React.FC<PptArtifactPanelProps> = ({ artifact, onClose, borderColor, onThemeChange }) => {
  const [isExporting, setIsExporting] = React.useState(false);
  const [isPresenting, setIsPresenting] = React.useState(false);
  const [showThemePanel, setShowThemePanel] = React.useState(false);
  const [themes, setThemes] = React.useState<PptTheme[]>([]);
  const [currentTheme, setCurrentTheme] = React.useState(artifact.theme || 'apple');
  const [isChangingTheme, setIsChangingTheme] = React.useState(false);
  const iframeRef = React.useRef<HTMLIFrameElement | null>(null);
  const previewSrcDoc = React.useMemo(() => buildSandboxedHtmlDocument(artifact.html), [artifact.html]);

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
        className="relative z-20 flex h-full flex-col overflow-hidden border-l bg-white/42 ring-1 ring-white/70 backdrop-blur-3xl"
        style={{ borderColor }}
      >
        <div className="z-10 flex h-14 flex-shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/82 px-6 backdrop-blur-md">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border border-white/20 bg-zinc-900 text-white shadow-lg shadow-zinc-900/20">
              <LayoutDashboard size={18} />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-bold leading-none text-slate-800">{artifact.title}</h2>
              <div className="mt-1 flex items-center gap-1.5">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                  {artifact.slideCount} slides · native pptx
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setShowThemePanel(!showThemePanel)}
              className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-colors ${
                showThemePanel
                  ? 'bg-sky-100 text-sky-700 border border-sky-200'
                  : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
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
              className="inline-flex items-center gap-2 rounded-xl bg-zinc-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-zinc-800 disabled:opacity-60"
              title="导出 PPTX"
              aria-label="导出 PPTX"
            >
              {isExporting ? <RefreshCcw size={14} className="animate-spin" /> : <Download size={14} />}
              导出
            </button>
            <button
              type="button"
              onClick={() => setIsPresenting(true)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-50"
              title="演示模式"
              aria-label="演示模式"
            >
              <Play size={14} />
              演示
            </button>
            {artifact.artifactId && (
              <button
                type="button"
                onClick={() => window.open(`/api/v1/agent/ppt/editor/${artifact.artifactId}`, '_blank')}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 transition-colors hover:bg-slate-50"
                title="编辑幻灯片"
                aria-label="编辑幻灯片"
              >
                <Pencil size={14} />
                编辑
              </button>
            )}
            <div className="mx-2 h-4 w-px bg-slate-200" />
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl p-2 text-slate-400 transition-all hover:bg-rose-50 hover:text-rose-500"
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
              className="z-10 overflow-hidden border-b border-slate-200/80 bg-white/90 backdrop-blur-md"
              style={{ maxHeight: '200px' }}
            >
              <div className="overflow-y-auto p-4" style={{ maxHeight: '200px' }}>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">选择主题</h3>
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
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
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
                      <span className="text-[9px] font-medium text-slate-600 truncate w-full text-center">{theme.name}</span>
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
          </motion.div>
        </div>
      </motion.aside>

      <AnimatePresence>
        {isPresenting && (
          <PptPresenterMode
            html={artifact.html}
            slideCount={artifact.slideCount}
            title={artifact.title}
            onClose={() => setIsPresenting(false)}
          />
        )}
      </AnimatePresence>
    </>
  );
};
