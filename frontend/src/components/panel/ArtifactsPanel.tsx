/**
 * 产物库面板：把整个会话产生的产物按类型摊开，点一条即可在预览区打开。
 *
 * 与单条消息上的产物卡不同 —— 这里回答「这一共做了哪些东西」，
 * 支持 PPT / 网站 / 文档 / 表格 / 图片几类，并可按标签筛选。
 * 数据全部来自消息快照（离线缓存也有），不额外请求后端。
 */
import * as React from 'react';
import { FileImage, FileSpreadsheet, FileText, Globe, Presentation } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../stores/chatStore';
import type { Artifact, Message } from '../../types';
import type { SessionPanelProps } from './types';

type Kind = 'all' | 'ppt' | 'website' | 'document' | 'sheet' | 'image';

const FILTERS: Array<{ id: Kind; label: string; Icon: typeof Globe }> = [
  { id: 'all', label: '全部', Icon: Globe },
  { id: 'ppt', label: 'PPT', Icon: Presentation },
  { id: 'website', label: '网站', Icon: Globe },
  { id: 'document', label: '文档', Icon: FileText },
  { id: 'sheet', label: '表格', Icon: FileSpreadsheet },
  { id: 'image', label: '图片', Icon: FileImage },
];

type Entry = {
  key: string;
  kind: Exclude<Kind, 'all'>;
  title: string;
  meta: string;
  /** 能直接从消息快照恢复的产物；文档/表格快照不进缓存，交给现签/回源 */
  artifact?: Artifact;
};

function collect(messages: Message[], sessionId: string): Entry[] {
  const out: Entry[] = [];
  const seen = new Set<string>();
  const push = (kind: Entry['kind'], id: string, title: string, meta: string, artifact?: Artifact) => {
    const key = `${kind}:${id}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ key, kind, title: title || '未命名产物', meta, artifact });
  };

  messages.forEach((m, i) => {
    if (m.pptArtifact?.status === 'ready') {
      push('ppt', m.pptArtifact.artifactId ?? `ppt-${i}`, m.pptArtifact.title ?? '演示文稿',
        `${m.pptArtifact.slideCount ?? 0} 页`, m.pptArtifact.html
          ? { language: 'ppt', artifactId: m.pptArtifact.artifactId, html: m.pptArtifact.html, title: m.pptArtifact.title ?? '', slideCount: m.pptArtifact.slideCount ?? 0, theme: m.pptArtifact.theme, sessionId }
          : undefined);
    }
    if (m.websiteArtifact?.status === 'ready') {
      push('website', m.websiteArtifact.artifactId ?? `web-${i}`, m.websiteArtifact.title ?? '网站',
        m.websiteArtifact.stack || '网站预览', m.websiteArtifact.html
          ? { language: 'website', artifactId: m.websiteArtifact.artifactId ?? '', html: m.websiteArtifact.html, title: m.websiteArtifact.title ?? '', projectSlug: m.websiteArtifact.projectSlug ?? '', stack: m.websiteArtifact.stack, sessionId }
          : undefined);
    }
    if (m.documentArtifact?.status === 'ready') {
      push('document', m.documentArtifact.artifactId ?? `doc-${i}`, m.documentArtifact.title ?? '文档',
        `${m.documentArtifact.charCount ?? 0} 字`);
    }
    if (m.sheetArtifact?.status === 'ready') {
      push('sheet', m.sheetArtifact.artifactId ?? `sheet-${i}`, m.sheetArtifact.title ?? '表格',
        `${m.sheetArtifact.sheetCount ?? 0} 个工作表`);
    }
    // 图片附件也算产物（用户上传或模型生成的图）
    m.attachments?.forEach((a, j) => {
      if (a.type?.startsWith('image/')) {
        push('image', `${i}-${j}-${a.name}`, a.name || '图片', a.type);
      }
    });
  });
  return out;
}

const KIND_ICON: Record<Entry['kind'], typeof Globe> = {
  ppt: Presentation,
  website: Globe,
  document: FileText,
  sheet: FileSpreadsheet,
  image: FileImage,
};

export const ArtifactsPanel: React.FC<SessionPanelProps> = ({ messages, sessionId }) => {
  const [filter, setFilter] = React.useState<Kind>('all');
  const setArtifact = useChatStore((s) => s.setArtifact);
  const entries = React.useMemo(() => collect(messages, sessionId), [messages, sessionId]);
  const shown = filter === 'all' ? entries : entries.filter((e) => e.kind === filter);

  return (
    <div className="p-4">
      <div className="mb-4 flex flex-wrap gap-1.5">
        {FILTERS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
              filter === id
                ? 'border-[var(--ring)] bg-[var(--surface-2)] text-[var(--foreground)]'
                : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
            )}
          >
            <Icon size={11} /> {label}
          </button>
        ))}
      </div>

      {entries.length === 0 ? (
        <p className="py-10 text-center text-xs text-[var(--muted-foreground)]">
          这个会话还没有产物。生成 PPT、网站或文档后，会集中出现在这里。
        </p>
      ) : shown.length === 0 ? (
        <p className="py-10 text-center text-xs text-[var(--muted-foreground)]">该分类下暂无产物</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {shown.map((e) => {
            const Icon = KIND_ICON[e.kind];
            return (
              <li key={e.key}>
                <button
                  type="button"
                  disabled={!e.artifact}
                  title={e.artifact ? '打开预览' : '快照需回源，暂不可直接打开'}
                  onClick={() => e.artifact && setArtifact(e.artifact)}
                  className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2.5 text-left transition-colors enabled:hover:border-[var(--ring)] enabled:hover:bg-[var(--surface-3)] disabled:opacity-55"
                >
                  <Icon size={16} className="shrink-0 text-[var(--muted-foreground)]" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold text-[var(--foreground)]">{e.title}</span>
                    <span className="block truncate text-[10px] text-[var(--muted-foreground)]">{e.meta}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
