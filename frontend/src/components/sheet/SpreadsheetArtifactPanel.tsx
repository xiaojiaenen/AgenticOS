import React from 'react';
import { motion, MotionValue } from 'motion/react';
import { Save, X } from 'lucide-react';
import { toast } from 'sonner';
import type { Artifact } from '../../types';
import { saveSheetSnapshot } from '../../services/agentService';
import { getUnsupportedReason, MIN_BROWSER_HINT } from '../../lib/univerSupport';
import { useTheme } from '../../hooks/useTheme';
import { SheetEditor, type SheetEditorHandle } from './SheetEditor';
import { SheetSnapshotTable } from './SheetSnapshotTable';

type SpreadsheetArtifact = Extract<Artifact, { language: 'spreadsheet' }>;

type SpreadsheetArtifactPanelProps = {
  artifact: SpreadsheetArtifact;
  onClose: () => void;
  borderColor: MotionValue<string>;
  sessionId?: string;
};

/**
 * 表格产物面板。
 *
 * Univer 的 SDK 体积很大（gzip 后约 1.7MB），所以这里做两层懒加载：
 * 面板本身由 ChatArtifactArea 用 React.lazy 加载，SDK 再在 SheetEditor
 * 挂载时动态 import。浏览器不达标时连 SDK 都不会下载。
 */
export const SpreadsheetArtifactPanel: React.FC<SpreadsheetArtifactPanelProps> = ({
  artifact,
  onClose,
  borderColor,
  sessionId,
}) => {
  const [saving, setSaving] = React.useState(false);
  const editorRef = React.useRef<SheetEditorHandle>(null);
  const unsupported = React.useMemo(() => getUnsupportedReason(), []);
  const { theme } = useTheme();
  // Univer 自成一套 UI 命名空间，必须显式告知明暗；system 模式下以 html.dark 为准
  const isDark =
    theme === 'system'
      ? document.documentElement.classList.contains('dark')
      : theme === 'dark';

  const handleSave = async () => {
    if (!sessionId) {
      toast.error('缺少会话 ID，无法保存');
      return;
    }
    const next = editorRef.current?.getSnapshot();
    if (!next) {
      toast.error('表格编辑器尚未就绪');
      return;
    }
    setSaving(true);
    try {
      await saveSheetSnapshot(sessionId, artifact.artifactId, next);
      toast.success('表格已保存');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '100%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      style={{ borderColor }}
      className="relative flex h-full min-w-0 flex-col overflow-hidden border-l bg-[var(--surface-1)]"
    >
      <header className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-[var(--foreground)]">
            {artifact.title}
          </h2>
          <p className="mt-0.5 truncate text-xs text-[var(--muted-foreground)]">
            {artifact.sheetCount} 个工作表
            {artifact.sheetNames.length > 0 && ` · ${artifact.sheetNames.join('、')}`}
          </p>
        </div>
        {!unsupported && (
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-[var(--border)] px-3 text-sm font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save size={14} />
            {saving ? '保存中…' : '保存'}
          </button>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭表格"
          className="shrink-0 rounded-md p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)]"
        >
          <X size={16} />
        </button>
      </header>

      <div className="min-h-0 flex-1">
        {unsupported ? (
          <SheetSnapshotTable
            snapshot={artifact.snapshot}
            reason={unsupported}
            browserHint={MIN_BROWSER_HINT}
          />
        ) : (
          <SheetEditor ref={editorRef} snapshot={artifact.snapshot} dark={isDark} />
        )}
      </div>
    </motion.aside>
  );
};
