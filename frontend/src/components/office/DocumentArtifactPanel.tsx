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
import { toastError } from '../../lib/errors';

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

  /**
   * 文档编辑器可用性开关。
   *
   * 曾经是 false：Univer 1.0.3 的 Docs preset 在旧的挂载方式下只渲染工具栏与
   * 状态栏、正文画布一片空白，那时走 DocSnapshotView 只读降级（能正确呈现标题
   * 层级与正文，比给用户一个空白编辑器诚实）。
   *
   * 现已为 true，可编辑画布、段落级样式渲染与持久化链路均已实测通过
   * （浏览器点击「居中对齐」→ 画布该行右移 → 段落 horizontalAlign 置 2 →
   * 保存 → 重开/读磁盘快照均保留；段落 startIndex 的规范约定见
   * DocEditor.tsx 的 conformParagraphStartIndexes）。保留这个开关
   * 是为了万一 Docs preset 再出回归时能一键切回只读，不必删代码。
   */
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
      toast.error(toastError(err, '保存失败'));
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
