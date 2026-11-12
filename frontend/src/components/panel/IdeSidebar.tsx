/**
 * IDE 式右侧栏：标签在顶，点会话里的产物/文件就开一个标签。
 *
 * 设计取舍（对齐用户要求）：
 * - **不做三层**（header + 标签条 + 内容）→ 只有一层标签栏 + 内容；
 * - **不做"会话产物"总览页**：产物与文件是同一类东西（会话里产出的东西），
 *   点一个就直接开标签；
 * - 网站类产物 **打开新浏览器页**（站内 iframe 预览受限，且用户要看真实站点）；
 * - 文档/表格/PPT 在标签里就地渲染。
 *
 * 标签状态在 store（sessionTabs），会话切换时按会话隔离。
 */
import * as React from 'react';
import { FileImage, FileSpreadsheet, FileText, Globe, Presentation, X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../stores/chatStore';
import type { Artifact, Message } from '../../types';

export type TabKind = 'ppt' | 'website' | 'document' | 'sheet' | 'image' | 'file' | 'log';

export interface SidebarTab {
  /** 稳定 id：kind + 业务 id */
  id: string;
  kind: TabKind;
  title: string;
  /** 直接可渲染的产物快照（website 不用，走新窗口） */
  artifact?: Artifact;
  /** 文件路径（file 标签） */
  path?: string;
}

const KIND_ICON: Record<TabKind, typeof Globe> = {
  ppt: Presentation,
  website: Globe,
  document: FileText,
  sheet: FileSpreadsheet,
  image: FileImage,
  file: FileText,
  log: FileText,
};

/** 从消息收集「可开标签」的条目（产物 + 图片附件） */
export function collectTabs(messages: Message[], sessionId: string): SidebarTab[] {
  const out: SidebarTab[] = [];
  const seen = new Set<string>();
  const push = (tab: SidebarTab) => {
    if (seen.has(tab.id)) return;
    seen.add(tab.id);
    out.push(tab);
  };
  messages.forEach((m, i) => {
    if (m.pptArtifact?.status === 'ready') {
      const id = m.pptArtifact.artifactId ?? `ppt-${i}`;
      push({
        id: `ppt:${id}`,
        kind: 'ppt',
        title: m.pptArtifact.title || '演示文稿',
        artifact: m.pptArtifact.html
          ? { language: 'ppt', artifactId: m.pptArtifact.artifactId, html: m.pptArtifact.html, title: m.pptArtifact.title ?? '', slideCount: m.pptArtifact.slideCount ?? 0, theme: m.pptArtifact.theme, sessionId }
          : undefined,
      });
    }
    if (m.websiteArtifact?.status === 'ready') {
      const id = m.websiteArtifact.artifactId ?? `web-${i}`;
      push({ id: `website:${id}`, kind: 'website', title: m.websiteArtifact.title || '网站' });
    }
    if (m.documentArtifact?.status === 'ready') {
      push({ id: `document:${m.documentArtifact.artifactId ?? i}`, kind: 'document', title: m.documentArtifact.title || '文档' });
    }
    if (m.sheetArtifact?.status === 'ready') {
      push({ id: `sheet:${m.sheetArtifact.artifactId ?? i}`, kind: 'sheet', title: m.sheetArtifact.title || '表格' });
    }
    m.attachments?.forEach((a, j) => {
      if (a.type?.startsWith('image/')) {
        push({ id: `image:${i}-${j}-${a.name}`, kind: 'image', title: a.name || '图片' });
      }
    });
  });
  return out;
}

export interface SidebarHostProps {
  sessionId: string | null;
  messages: Message[];
}

/**
 * 侧栏容器：标签栏 + 激活标签内容。
 * 标签数据由 ChatMainArea 的触发点写入 store；这里只负责渲染与关闭。
 */
export const IdeSidebar: React.FC<SidebarHostProps> = ({ sessionId, messages }) => {
  const tabs = useChatStore((s) => s.sidebarTabs);
  const activeTabId = useChatStore((s) => s.activeSidebarTabId);
  const setActiveTab = useChatStore((s) => s.setActiveSidebarTab);
  const closeTab = useChatStore((s) => s.closeSidebarTab);
  const closeAll = useChatStore((s) => s.closeSidebar);

  // 侧栏打开但没有任何标签时，给一个"可打开项"列表（等价于旧产物库，
  // 但从「浏览」降级为「空状态提示」，不占标签位）
  const available = React.useMemo(() => collectTabs(messages, sessionId ?? ''), [messages, sessionId]);
  const openTab = useChatStore((s) => s.openSidebarTab);
  const active = tabs.find((t) => t.id === activeTabId) ?? tabs[0] ?? null;

  if (tabs.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--border-subtle)] px-4 py-2.5">
          <span className="text-[11px] font-semibold text-[var(--muted-foreground)]">侧栏</span>
          <button type="button" onClick={closeAll} aria-label="关闭侧栏" className="rounded p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"><X size={14} /></button>
        </div>
        {available.length === 0 ? (
          <div className="flex flex-1 items-center justify-center px-6">
            <p className="text-center text-[11px] leading-relaxed text-[var(--muted-foreground)]">
              这个会话还没有产物。<br />生成 PPT、网站、文档或上传图片后，会出现在这里。
            </p>
          </div>
        ) : (
            <ul className="flex flex-col gap-1 p-3">
              {available.map((t) => {
                const Icon = KIND_ICON[t.kind];
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => openTab(t)}
                      className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                    >
                      <Icon size={13} className="shrink-0" />
                      <span className="truncate">{t.title}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col">
      {/* 单层标签栏：IDE 风格，横向滚动 */}
      <div className="flex shrink-0 items-stretch border-b border-[var(--border-subtle)]">
        <div role="tablist" aria-label="侧栏标签" className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
          {tabs.map((t) => {
            const Icon = KIND_ICON[t.kind];
            const isActive = t.id === (active?.id ?? '');
            return (
              <div
                key={t.id}
                className={cn(
                  'group flex max-w-[180px] shrink-0 items-center gap-1.5 border-r border-[var(--border-subtle)] px-2.5 py-2 text-[11px]',
                  isActive ? 'bg-[var(--surface-2)] text-[var(--foreground)]' : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]',
                )}
              >
                <button
                  role="tab"
                  aria-selected={isActive}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  title={t.title}
                >
                  <Icon size={12} className="shrink-0" />
                  <span className="truncate">{t.title}</span>
                </button>
                <button
                  type="button"
                  onClick={() => closeTab(t.id)}
                  aria-label={`关闭 ${t.title}`}
                  className="shrink-0 rounded p-0.5 opacity-0 transition-opacity hover:bg-[var(--surface-3)] group-hover:opacity-100"
                >
                  <X size={11} />
                </button>
              </div>
            );
          })}
        </div>
        <button
          type="button"
          onClick={closeAll}
          aria-label="关闭侧栏"
          className="shrink-0 px-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          <X size={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {active ? <TabBody tab={active} sessionId={sessionId} messages={messages} /> : null}
      </div>
    </div>
  );
};

/** 标签内容：按类型在侧栏内就地渲染 */
const TabBody: React.FC<{ tab: SidebarTab; sessionId: string | null; messages: Message[] }> = ({ tab, sessionId, messages }) => {
  const setArtifact = useChatStore((s) => s.setArtifact);

  // PPT：侧栏内 iframe 渲染（preview_html 自包含，无外部依赖）
  if (tab.kind === 'ppt' && tab.artifact?.language === 'ppt' && tab.artifact.html) {
    return (
      <iframe
        title={tab.title}
        srcDoc={tab.artifact.html}
        className="h-full w-full border-0 bg-white"
        sandbox="allow-scripts allow-same-origin allow-popups"
      />
    );
  }

  // 网站：产物自带预览 HTML 时内联渲染；否则提示在浏览器打开
  if (tab.kind === 'website') {
    const ws = messages.find((x) => `website:${x.websiteArtifact?.artifactId ?? ''}` === tab.id)?.websiteArtifact;
    if (ws?.html) {
      return (
        <iframe
          title={tab.title}
          srcDoc={ws.html}
          className="h-full w-full border-0 bg-white"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        />
      );
    }
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <Globe size={26} className="text-[var(--muted-foreground)]" />
        <p className="text-xs leading-relaxed text-[var(--muted-foreground)]">这个网站没有可内联的预览快照。</p>
        {ws?.previewUrl ? (
          <a href={ws.previewUrl} target="_blank" rel="noreferrer" className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)]">
            在浏览器打开
          </a>
        ) : null}
      </div>
    );
  }

  // 文档 / 表格：完整编辑器在主预览区（侧栏宽度放不下 Univer），给一键跳转
  if (tab.kind === 'document' || tab.kind === 'sheet') {
    const m = messages.find((x) =>
      tab.kind === 'document'
        ? `document:${x.documentArtifact?.artifactId ?? ''}` === tab.id
        : `sheet:${x.sheetArtifact?.artifactId ?? ''}` === tab.id,
    );
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <FileText size={26} className="text-[var(--muted-foreground)]" />
        <p className="text-xs leading-relaxed text-[var(--muted-foreground)]">
          {tab.kind === 'document' ? '文档' : '表格'}编辑器需要更大空间。
        </p>
        <button
          type="button"
          className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)]"
          onClick={() => {
            const d = m?.documentArtifact, s = m?.sheetArtifact;
            if (d?.artifactId) setArtifact({ language: 'document', artifactId: d.artifactId, title: d.title ?? '', snapshot: {} as Record<string, unknown>, charCount: d.charCount ?? 0, sessionId: sessionId ?? undefined });
            else if (s?.artifactId) setArtifact({ language: 'spreadsheet', artifactId: s.artifactId, title: s.title ?? '', snapshot: {} as Record<string, unknown>, sheetNames: s.sheetNames ?? [], sheetCount: s.sheetCount ?? 0, sessionId: sessionId ?? undefined });
          }}
        >
          在主区域打开
        </button>
      </div>
    );
  }

  if (tab.kind === 'image') {
    return <div className="p-4 text-[11px] leading-relaxed text-[var(--muted-foreground)]">图片附件请在对话中查看。</div>;
  }

  return <div className="p-4 text-[11px] text-[var(--muted-foreground)]">暂无可预览的内容。</div>;
};
