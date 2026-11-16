import React from 'react';
import { motion, AnimatePresence, MotionValue } from 'motion/react';
import { Download, LayoutDashboard, Palette, Play, RefreshCcw, Sparkles, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Artifact } from '../../types';
import { cn } from '../../lib/utils';
import { buildSandboxedHtmlDocument } from '../../lib/safePreview';
import { toastError } from '../../lib/errors';
import { exportPptx, listPptThemes, rethemePpt, getPptPreviewHtml, listPptVisualStyles, PPT_TRANSITIONS, VISUAL_STYLE_CATEGORY_LABELS, type PptTheme, type PptVisualStyle } from '../../services/agentService';
import { PptPresenterMode } from './PptPresenterMode';
import { ArtifactVersionBar } from '../chat/ArtifactVersionBar';
import { PublishToGalleryButton } from '../gallery/PublishToGalleryButton';

type PptArtifactPanelProps = {
  artifact: Extract<Artifact, { language: 'ppt' }>;
  onClose: () => void;
  /** 外框颜色动画值（主区域抽屉用）；侧栏 compact 模式不需要 */
  borderColor?: MotionValue<string>;
  onThemeChange?: (newHtml: string, theme: string) => void;
  /** 切换到历史版本（由版本条调用） */
  onSwitchVersion?: (artifact: Extract<Artifact, { language: 'ppt' }>) => void;
  /**
   * 侧栏内嵌模式：铺满容器、去掉 60% 宽度动画与左侧边框。
   *
   * 面板本身是给主区域右侧抽屉用的（`width: 60%` + 入场动画 + 关闭按钮）。
   * 在 IDE 侧栏里这些都不合适 —— 容器已经是窄栏，60% 会把它挤成一条缝，
   * 而关闭按钮与外层标签栏的关闭重复。工具按钮（主题/导出/编辑）保持不变，
   * 那正是「侧栏点开没有这些按钮」要修的。
   */
  compact?: boolean;
};

export const PptArtifactPanel: React.FC<PptArtifactPanelProps> = ({ artifact, onClose, borderColor, onThemeChange, onSwitchVersion, compact = false }) => {
  const [isExporting, setIsExporting] = React.useState(false);
  const [isPresenting, setIsPresenting] = React.useState(false);
  const [showThemePanel, setShowThemePanel] = React.useState(false);
  // 视觉风格面板（与主题面板并列，两者正交）
  const [showStylePanel, setShowStylePanel] = React.useState(false);
  const [visualStyles, setVisualStyles] = React.useState<PptVisualStyle[]>([]);
  // 导出选项（转场 / 动画 / 备注）—— 演示增强，默认走后端缺省
  const [showExportOptions, setShowExportOptions] = React.useState(false);
  const [exportTransition, setExportTransition] = React.useState('');
  const [exportAnimation, setExportAnimation] = React.useState('');
  const [exportNotes, setExportNotes] = React.useState(true);
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

  // 父级换掉了预览 HTML（切换主题 / 切历史版本 / 侧栏重开）时必须同步到本地
  // state，否则预览永远停在首次挂载那份 —— 用户点主题「没反应」。
  //
  // 为什么需要这个 effect：`html` 是本地 state（为了让懒加载回源能写入），
  // `useState(artifact.html)` 只在挂载时求值一次，之后父传的 artifact.html
  // 变了不会自动跟着变。之前只有 `handleThemeChange` 调 onThemeChange 更新
  // 父级，本地这份没人管 —— 切主题后后端返回了新 HTML、父级也存了，
  // 但预览 iframe 用的还是旧的那份。
  React.useEffect(() => {
    if (artifact.html && artifact.html !== html) {
      setHtml(artifact.html);
    }
    // 刻意不依赖 html：本地写入（懒加载/切换主题）不该反过来触发这个 effect，
    // 只关心「父级给了一份新的」。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifact.html]);

  const previewSrcDoc = React.useMemo(() => buildSandboxedHtmlDocument(html), [html]);

  // 「打开 SVG 编辑器」的入口已按用户要求从面板移除（侧栏是查看/发布场景，
  // 跳独立编辑器页面与侧栏形态冲突）。后端 `/ppt/editor/{id}` 端点保留，
  // 需要时仍可直接访问。

  // 加载主题列表
  React.useEffect(() => {
    if (showThemePanel && themes.length === 0) {
      listPptThemes().then(setThemes).catch(console.error);
    }
  }, [showThemePanel, themes.length]);

  // 加载视觉风格目录（首次打开风格面板时）
  React.useEffect(() => {
    if (showStylePanel && visualStyles.length === 0) {
      listPptVisualStyles().then(setVisualStyles).catch(console.error);
    }
  }, [showStylePanel, visualStyles.length]);

  const handleExport = async () => {
    setIsExporting(true);

    if (artifact.artifactId) {
      try {
        const blob = await exportPptx(artifact.artifactId, {
          transition: exportTransition || undefined,
          animation: exportAnimation || undefined,
          enableNotes: exportNotes,
        });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${artifact.title || 'AgenticOS-PPT'}.pptx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        toast.success('已导出 PPTX');
      } catch (err) {
        console.error('[PPTX Export] Backend export error:', err);
        toast.error(toastError(err, '导出失败'));
      } finally {
        setIsExporting(false);
        setShowExportOptions(false);
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
      // **必须直接更新本地 html**：预览 iframe 读的是这个 state。
      //
      // 之前只调 onThemeChange 往上抛，靠父级回传新 artifact.html —— 但
      //   1) 侧栏（IdeSidebar）压根没传 onThemeChange，回调为空；
      //   2) 即使传了，父级 setArtifact 也只是让 artifact.html 变化，
      //      本组件的 html 是 useState 初始化的本地副本，不会自动同步。
      // 两条叠加 → 后端主题真的换了（metadata 也更新），但预览纹丝不动，
      // 用户看到的就是「切换主题不生效」。
      if (result.html) setHtml(result.html);
      onThemeChange?.(result.html, themeName);
    } catch (err) {
      console.error('[Theme Change] Error:', err);
      toast.error(toastError(err, '主题切换失败'));
    } finally {
      setIsChangingTheme(false);
    }
  };

  return (
    <>
      <motion.aside
        initial={compact ? false : { width: 0, opacity: 0 }}
        animate={compact ? undefined : { width: '60%', opacity: 1 }}
        exit={compact ? undefined : { width: 0, opacity: 0 }}
        transition={compact ? undefined : { duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className={cn(
          'relative z-20 flex h-full flex-col overflow-hidden bg-[var(--surface-1)]/70 backdrop-blur-3xl',
          compact
            ? 'w-full'
            : 'border-l ring-1 ring-[var(--border-subtle)]',
        )}
        style={compact ? undefined : { borderColor }}
      >
        <div className={cn(
          'z-10 flex flex-shrink-0 items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/90 backdrop-blur-md',
          compact ? 'h-11 px-2.5' : 'h-14 px-6',
        )}>
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
          <div
            className={cn(
              'flex items-center gap-1',
              // 侧栏（compact）只有 420px 宽，5 个按钮横排会被挤到变形
              // （文字竖排、图标溢出）。允许换行 + 收紧内边距，按钮保持完整。
              compact ? 'flex-wrap justify-end gap-1' : '',
            )}
          >
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
              className={`inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
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
              onClick={() => setShowStylePanel(!showStylePanel)}
              className={`inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
                showStylePanel
                  ? 'bg-sky-100 text-sky-700 border border-sky-200 dark:bg-sky-500/20 dark:text-sky-300 dark:border-sky-500/40'
                  : 'border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] hover:bg-[var(--surface-2)]'
              }`}
              title="查看视觉风格（与主题正交：风格管形状/留白，主题管配色）"
              aria-label="视觉风格"
            >
              <Sparkles size={14} />
              风格
            </button>
            <button
              type="button"
              onClick={() => setShowExportOptions((v) => !v)}
              disabled={isExporting}
              className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 disabled:opacity-60"
              title="导出 PPTX（可选转场 / 动画）"
              aria-label="导出 PPTX"
            >
              {isExporting ? <RefreshCcw size={14} className="animate-spin" /> : <Download size={14} />}
              导出
            </button>
            {artifact.artifactId && artifact.sessionId && (
              <PublishToGalleryButton
                kind="ppt"
                sessionId={artifact.sessionId}
                sourceRef={artifact.artifactId}
                title={artifact.title}
              />
            )}
            <button
              type="button"
              onClick={() => setIsPresenting(true)}
              className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
              title="演示模式"
              aria-label="演示模式"
            >
              <Play size={14} />
              演示
            </button>
            {/* 「编辑幻灯片」按钮已按用户要求移除：侧栏是查看/发布的场景，
                进编辑器要跳转到独立的 svg_editor 页面，和侧栏形态冲突。
                主区域的产物面板同样不再提供该入口。 */}
            {/* 侧栏内嵌时关闭交给外层标签栏，不重复放一个 X */}
            {!compact && (
              <>
                <div className="mx-2 h-4 w-px bg-[var(--border-medium)]" />
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-xl p-2 text-[var(--muted-foreground)] transition-all hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-500/15"
                  aria-label="关闭演示文稿预览"
                >
                  <X size={18} />
                </button>
              </>
            )}
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
                      {/* WCAG 对比度徽章：AAA/AA 绿、AA-Large 黄、FAIL 红点警示 */}
                      {theme.contrast_grade && (
                        <span
                          title={`WCAG 对比度：${theme.contrast_grade}`}
                          className={`absolute top-0.5 left-0.5 rounded px-0.5 text-[7px] font-bold leading-3 ${
                            theme.contrast_grade === 'AAA' || theme.contrast_grade === 'AA'
                              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
                              : theme.contrast_grade === 'AA-Large'
                                ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300'
                                : 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300'
                          }`}
                        >
                          {theme.contrast_grade === 'AA-Large' ? 'AA-L' : theme.contrast_grade === 'FAIL' ? '!' : theme.contrast_grade}
                        </span>
                      )}
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

        {/* 视觉风格面板：只读展示 —— 风格是**生成时**决定的，已生成的
            SVG 无法事后改风格（形状/留白/纹理都写进 SVG 了），所以这里
            不提供切换，只说明当前缺省并提供「重新生成时选它」的指引。 */}
        <AnimatePresence>
          {showStylePanel && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="z-10 overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/90 backdrop-blur-md"
              style={{ maxHeight: '260px' }}
            >
              <div className="overflow-y-auto p-4" style={{ maxHeight: '260px' }}>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">
                    视觉风格（18 种）
                  </h3>
                  <span className="text-[10px] text-[var(--muted-foreground)]">
                    与配色正交 · 选择在下次生成时生效
                  </span>
                </div>
                <p className="mb-3 text-[10px] leading-relaxed text-[var(--muted-foreground)]">
                  风格管形状语言、装饰密度、留白节奏、纹理层次；配色由上方「主题」决定。
                  两种组合使用，例如 <code className="rounded bg-[var(--surface-2)] px-1">github</code> 主题 ×{' '}
                  <code className="rounded bg-[var(--surface-2)] px-1">swiss-minimal</code> 风格。
                </p>
                {(['corporate', 'editorial', 'expressive', 'hand_drawn', 'specialty'] as const).map((cat) => {
                  const items = visualStyles.filter((s) => s.category === cat);
                  if (items.length === 0) return null;
                  return (
                    <div key={cat} className="mb-3">
                      <div className="mb-1.5 text-[10px] font-semibold text-[var(--foreground)]">
                        {VISUAL_STYLE_CATEGORY_LABELS[cat] ?? cat}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((s) => (
                          <span
                            key={s.id}
                            title={`${s.label_en ?? ''}\n${s.summary}`}
                            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1 text-[10px] text-[var(--foreground)]"
                          >
                            {s.label}
                            <span className="ml-1 text-[9px] text-[var(--muted-foreground)]">({s.id})</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 导出选项：转场 / 元素动画 / 演讲者备注。
            演示增强 —— 此前导出固定走后端默认（fade + mixed），用户无从
            选择；后端 /ppt/export 其实一直支持 transition / animation。 */}
        <AnimatePresence>
          {showExportOptions && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="z-10 overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/90 backdrop-blur-md"
            >
              <div className="flex flex-wrap items-end gap-3 p-4">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-semibold text-[var(--muted-foreground)]">页面转场</span>
                  <select
                    value={exportTransition}
                    onChange={(e) => setExportTransition(e.target.value)}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1.5 text-[11px] text-[var(--foreground)]"
                  >
                    <option value="">默认（淡入淡出）</option>
                    {PPT_TRANSITIONS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-semibold text-[var(--muted-foreground)]">元素动画</span>
                  <select
                    value={exportAnimation}
                    onChange={(e) => setExportAnimation(e.target.value)}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1.5 text-[11px] text-[var(--foreground)]"
                  >
                    <option value="">默认（混合）</option>
                    <option value="none">无动画</option>
                    <option value="mixed">混合</option>
                    <option value="random">随机</option>
                  </select>
                </label>
                <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[var(--foreground)]">
                  <input
                    type="checkbox"
                    checked={exportNotes}
                    onChange={(e) => setExportNotes(e.target.checked)}
                    className="h-3.5 w-3.5"
                  />
                  写入演讲者备注
                </label>
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={isExporting}
                  className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-[11px] font-semibold text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-60"
                >
                  {isExporting ? <RefreshCcw size={12} className="animate-spin" /> : <Download size={12} />}
                  开始导出
                </button>
                <button
                  type="button"
                  onClick={() => setShowExportOptions(false)}
                  className="rounded-lg px-2 py-1.5 text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                >
                  取消
                </button>
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
