import React from 'react';
import { motion, MotionValue } from 'motion/react';
import { Save, X } from 'lucide-react';
import { toast } from 'sonner';
import type { Artifact } from '../../types';
import { saveDocumentSnapshot } from '../../services/agentService';
import { ArtifactVersionBar } from '../chat/ArtifactVersionBar';
import { getUnsupportedReason, MIN_BROWSER_HINT } from '../../lib/univerSupport';
import { useIsDark } from '../../hooks/useIsDark';
import { DocEditor, type DocEditorHandle } from './DocEditor';
import { DocSnapshotView } from './DocSnapshotView';

type DocumentArtifact = Extract<Artifact, { language: 'document' }>;

type DocumentArtifactPanelProps = {
  artifact: DocumentArtifact;
  onClose: () => void;
  borderColor: MotionValue<string>;
  sessionId?: string;
  /** 切换到历史版本（由版本条调用） */
  onSwitchVersion?: (artifact: DocumentArtifact) => void;
};

/**
 * 文档产物面板。
 *
 * 与表格面板同构：面板 React.lazy + SDK 挂载时动态 import，浏览器不达标时
 * 连 SDK 都不会下载。
 */
export const DocumentArtifactPanel: React.FC<DocumentArtifactPanelProps> = ({
  artifact,
  onClose,
  borderColor,
  sessionId,
  onSwitchVersion,
}) => {
  const [saving, setSaving] = React.useState(false);
  const editorRef = React.useRef<DocEditorHandle>(null);
  const capabilityIssue = React.useMemo(() => getUnsupportedReason(), []);
  const isDark = useIsDark();

  /** 文档编辑器可编辑画布暂不可用（Univer 1.0.3 的 Docs preset 在我们的挂载
   *  方式下只渲染工具栏与状态栏，正文页面画不出来；同一套挂载逻辑下表格是
   *  正常的）。在修好之前走只读渲染 —— 它能正确呈现标题层级与正文，比给用户
   *  一个空白编辑器诚实。见 docs/调研-Univer办公能力接入.md 的「已知问题」。 */
  const DOC_EDITOR_READY = true;
  const unsupported = capabilityIssue ?? (DOC_EDITOR_READY ? null : '文档暂不支持在线编辑');

  const handleSave = async () => {
    if (!sessionId) {
      toast.error('缺少会话 ID，无法保存');
      return;
    }
    const next = editorRef.current?.getSnapshot();
    if (!next) {
      toast.error('文档编辑器尚未就绪');
      return;
    }
    setSaving(true);
    try {
      await saveDocumentSnapshot(sessionId, artifact.artifactId, next);
      toast.success('文档已保存');
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
            {artifact.charCount} 字
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
          aria-label="关闭文档"
          className="shrink-0 rounded-md p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)]"
        >
          <X size={16} />
        </button>
      </header>

      {sessionId && !unsupported && (
        <ArtifactVersionBar
          sessionId={sessionId}
          currentReference={artifact.version ? `v${artifact.version}` : undefined}
          kind="document"
          onSelect={({ artifact: loaded }: { artifact: Record<string, unknown> }) => {
            const next = loaded as unknown as {
              artifact_id: string;
              title: string;
              snapshot: Record<string, unknown>;
            };
            const body = (next.snapshot?.body ?? {}) as { dataStream?: string };
            onSwitchVersion?.({
              language: 'document',
              artifactId: next.artifact_id,
              title: next.title,
              snapshot: next.snapshot,
              // 段落符 \r 与收尾的 \n 都不是正文字数
              charCount: (body.dataStream ?? '').replace(/[\r\n]/g, '').length,
              sessionId,
            });
          }}
        />
      )}

      <div className="min-h-0 flex-1">
        {unsupported ? (
          <DocSnapshotView
            snapshot={artifact.snapshot}
            reason={capabilityIssue ?? '文档编辑器尚未就绪'}
            browserHint={MIN_BROWSER_HINT}
          />
        ) : (
          /* key 绑产物 id：切历史版本 / 生成新文档时必须重建编辑器。
             DocEditor 只在挂载时读一次快照（它刻意不做重建，以免抹掉用户
             正在改的内容），不换 key 的话标题和字数会更新、画布却还停在
             上一版内容，看起来像「生成了但没生效」。 */
          <DocEditor
            key={artifact.artifactId}
            ref={editorRef}
            snapshot={artifact.snapshot}
            dark={isDark}
          />
        )}
      </div>
    </motion.aside>
  );
};
