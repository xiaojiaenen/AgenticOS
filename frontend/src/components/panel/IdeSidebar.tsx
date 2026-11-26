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
import {
  Activity, FileImage, FileSpreadsheet, FileText, FolderTree, Globe,
  Layers, LayoutGrid, Presentation, X,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useChatStore } from '../../stores/chatStore';
import { issueWebsitePreviewUrl } from '../../services/websiteService';
import { apiFetch } from '../../services/apiClient';
import { Download } from 'lucide-react';
import { PptArtifactPanel } from '../ppt/PptArtifactPanel';
import { SlideLivePreview } from '../ppt/SlideLivePreview';
import { FilesPanel } from './FilesPanel';
import { RunLogPanel } from './RunLogPanel';
import { ArtifactsPanel } from './ArtifactsPanel';
import { collectTabs, panelTab } from './tabs';
import { inlineHtmlResources, hasRelativeResourceRefs } from '../../lib/inlineHtmlResources';
import type { SidebarTab, TabKind } from './tabs';
import type { Message } from '../../types';

// 兼容旧 import 路径：类型与收集函数的唯一事实来源在 ./tabs。
export { collectTabs, panelTab, PANEL_TAB_IDS } from './tabs';
export type { SidebarTab, TabKind } from './tabs';

const KIND_ICON: Record<TabKind, typeof Globe> = {
  ppt: Presentation,
  website: Globe,
  document: FileText,
  sheet: FileSpreadsheet,
  image: FileImage,
  file: FileText,
  log: FileText,
  output: FileText,
  files: FolderTree,
  'run-log': Activity,
  artifacts: Layers,
};

/** 启动器条目：空状态时展示的「打开面板」卡片（IDE 工作台风格） */
const LAUNCHERS: Array<{
  kind: 'files' | 'run-log' | 'artifacts';
  label: string;
  desc: string;
  icon: typeof Globe;
}> = [
  { kind: 'files', label: '文件', desc: '浏览会话工作区的文件与产物', icon: FolderTree },
  { kind: 'artifacts', label: '产物库', desc: '查看本次会话生成的全部交付物', icon: Layers },
  { kind: 'run-log', label: '运行日志', desc: '复盘本轮工具调用与执行状态', icon: Activity },
];

export interface SidebarHostProps {
  sessionId: string | null;
  messages: Message[];
  /** PPT 生成中：侧栏在没有产物标签时展示实时预览（轮询增量 SVG） */
  isPptStreaming?: boolean;
  /** 会话工作区产物（html/csv/xlsx/图片…），用于「本次会话产物」列表 */
  workspaceOutputs?: import('../../lib/workspaceArtifacts').WorkspaceEntry[];
}

/**
 * 侧栏容器：标签栏 + 激活标签内容。
 * 标签数据由 ChatMainArea 的触发点写入 store；这里只负责渲染与关闭。
 */
export const IdeSidebar: React.FC<SidebarHostProps> = ({ sessionId, messages, isPptStreaming = false, workspaceOutputs = [] }) => {
  const tabs = useChatStore((s) => s.sidebarTabs);
  const activeTabId = useChatStore((s) => s.activeSidebarTabId);
  const setActiveTab = useChatStore((s) => s.setActiveSidebarTab);
  const closeTab = useChatStore((s) => s.closeSidebarTab);
  const closeAll = useChatStore((s) => s.closeSidebar);

  // 侧栏打开但没有任何标签时，给一个"可打开项"列表（等价于旧产物库，
  // 但从「浏览」降级为「空状态提示」，不占标签位）
  const available = React.useMemo(
    () => collectTabs(messages, sessionId ?? '', workspaceOutputs),
    [messages, sessionId, workspaceOutputs],
  );
  const openTab = useChatStore((s) => s.openSidebarTab);
  const active = tabs.find((t) => t.id === activeTabId) ?? tabs[0] ?? null;
  const [showLauncher, setShowLauncher] = React.useState(false);

  // 启动器菜单：展示可打开的功能面板
  const launcher = (
    <div className="relative">
      <button
        type="button"
        onClick={() => setShowLauncher((v) => !v)}
        aria-label="打开工作区面板"
        title="打开工作区面板"
        className="rounded-md p-1 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
      >
        <LayoutGrid size={14} />
      </button>
      {showLauncher && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setShowLauncher(false)} />
          <div className="absolute right-0 top-7 z-40 w-56 rounded-xl border border-[var(--border-medium)] bg-[var(--surface-1)] p-1.5 shadow-xl">
            <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">工作区面板</p>
            {LAUNCHERS.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.kind}
                  type="button"
                  onClick={() => { openTab(panelTab(item.kind)); setShowLauncher(false); }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-[11px] text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                >
                  <Icon size={14} className="shrink-0 text-[var(--muted-foreground)]" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{item.label}</span>
                    <span className="block truncate text-[10px] text-[var(--muted-foreground)]">{item.desc}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );

  if (tabs.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--border-subtle)] px-4 py-2.5">
          <span className="text-[11px] font-semibold text-[var(--muted-foreground)]">侧栏</span>
          <div className="flex items-center gap-1">
            {launcher}
            <button type="button" onClick={closeAll} aria-label="关闭侧栏" className="rounded p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"><X size={14} /></button>
          </div>
        </div>
        {/* 生成中没有产物标签：直接展示实时预览（用户要求"用侧栏那套展示"）。
            原来实时预览是主区域独立的 35% 右栏，与产物面板抢宽度。 */}
        {isPptStreaming ? (
          <SlideLivePreview
            sessionId={sessionId}
            isStreaming={isPptStreaming}
            hasArtifact={false}
            compact
          />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            {/* 工作台启动器：文件 / 产物库 / 运行日志 */}
            <div className="px-3 pb-2 pt-3">
              <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                工作区
              </p>
              <div className="grid grid-cols-1 gap-2">
                {LAUNCHERS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.kind}
                      type="button"
                      onClick={() => openTab(panelTab(item.kind))}
                      className="group flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-2.5 text-left transition-all hover:border-[var(--ring)] hover:bg-[var(--surface-2)] active:scale-[0.98]"
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-2)] text-[var(--muted-foreground)] transition-colors group-hover:text-[var(--ring)]">
                        <Icon size={17} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-semibold text-[var(--foreground)]">{item.label}</span>
                        <span className="block truncate text-[10px] text-[var(--muted-foreground)]">{item.desc}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 本次会话的产物（可打开项） */}
            {available.length > 0 && (
              <div className="border-t border-[var(--border-subtle)] px-3 py-3">
                <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                  本次会话 · {available.length} 项产物
                </p>
                <ul className="flex flex-col gap-1">
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
              </div>
            )}
          </div>
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
        <div className="flex shrink-0 items-center">
          {launcher}
          <button
            type="button"
            onClick={closeAll}
            aria-label="关闭侧栏"
            className="shrink-0 px-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {active ? <TabBody tab={active} sessionId={sessionId} messages={messages} workspaceOutputs={workspaceOutputs} /> : null}
      </div>
    </div>
  );
};

/**
 * 网站标签体：与 WebsiteArtifactPanel 相同的劫持防护。
 *
 * vue/react（带路由的 SPA）在 srcDoc 里启动时，hash router 的
 * replaceState 以**父文档**为基准 —— iframe 会导航到 AgenticOS 自己
 * （实测 /chat#/）。这类栈必须用子路径托管的 preview_url；
 * vanilla（无路由脚本）srcDoc 安全，作为兜底。
 */
const WebsiteTabBody: React.FC<{ tab: SidebarTab; sessionId: string | null }> = ({ tab, sessionId }) => {
  const slug = tab.projectSlug;
  const stack = tab.stack;
  const isRouterStack = stack === 'vue' || stack === 'react';
  const [signedUrl, setSignedUrl] = React.useState<string | null>(null);
  const [signFailed, setSignFailed] = React.useState(false);

  React.useEffect(() => {
    if (!sessionId || !slug || signedUrl || signFailed) return;
    let cancelled = false;
    issueWebsitePreviewUrl(sessionId, slug)
      .then((r) => {
        if (!cancelled && r?.url) setSignedUrl(r.url);
        else if (!cancelled) setSignFailed(true);
      })
      .catch(() => {
        if (!cancelled) setSignFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, slug, signedUrl, signFailed]);

  const art = tab.artifact;
  const canInline = !isRouterStack && !!art && art.language === 'website' && !!art.html;

  if (signedUrl) {
    return (
      <iframe
        title={tab.title}
        src={signedUrl}
        className="h-full w-full border-0 bg-white"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        allow="fullscreen"
      />
    );
  }

  if (isRouterStack || (!canInline && signFailed)) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <Globe size={26} className="text-[var(--muted-foreground)]" />
        <p className="text-xs leading-relaxed text-[var(--muted-foreground)]">
          {signFailed
            ? '预览链接签发失败，请稍后重试或在会话里重新打开产物。'
            : '正在签发预览链接…'}
        </p>
        {!signFailed && slug && sessionId && (
          <button
            type="button"
            onClick={() => setSignFailed(false)}
            className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)]"
          >
            重试
          </button>
        )}
      </div>
    );
  }

  // vanilla：内联快照安全
  if (canInline && art.language === 'website') {
    return (
      <iframe
        title={tab.title}
        srcDoc={art.html}
        className="h-full w-full border-0 bg-white"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      />
    );
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <Globe size={26} className="text-[var(--muted-foreground)]" />
      <p className="text-xs leading-relaxed text-[var(--muted-foreground)]">这个网站没有可内联的预览快照。</p>
    </div>
  );
};

/**
 * 工作区产物标签（html / 图片 / 数据文件）。
 *
 * 读取端点带鉴权，iframe / `<img src>` 不会自动带 Authorization header，
 * 所以统一走 apiFetch 取回内容再内联渲染：html → srcDoc（sandbox 不给
 * allow-same-origin，模型生成的脚本拿不到父页面），图片 → objectURL，
 * 其余数据类型 → 文本预览 + 下载按钮。
 */
const OutputTabBody: React.FC<{ tab: SidebarTab; sessionId: string | null }> = ({ tab, sessionId }) => {
  const url = tab.url ?? '';
  const kind = tab.outputKind;
  const [text, setText] = React.useState<string | null>(null);
  const [blobUrl, setBlobUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!url) return;
    let cancelled = false;
    let created: string | null = null;
    setError(null);
    setText(null);
    setBlobUrl(null);
    apiFetch<string | Blob>(url, { responseType: kind === 'image' ? 'blob' : 'text' }, '加载产物失败')
      .then(async (data) => {
        if (cancelled) return;
        if (kind === 'image') {
          created = URL.createObjectURL(data as Blob);
          setBlobUrl(created);
          return;
        }
        let html = data as string;
        // html 相对路径资源（<link href="style.css">/<img src="x.png">）在
        // srcDoc iframe 里解析不到，且 sandbox 无 same-origin 带不了鉴权 header。
        // 在父页面用带鉴权端点抓回并内联，预览才能完整呈现。
        if (kind === 'html' && sessionId && hasRelativeResourceRefs(html)) {
          html = await inlineHtmlResources(html, async (filename) => {
            const resourceUrl = `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/outputs/${encodeURIComponent(filename)}`;
            const isImage = /\.(png|jpe?g|gif|webp|svg)$/i.test(filename);
            if (isImage) {
              return { blob: await apiFetch<Blob>(resourceUrl, { responseType: 'blob' }, '加载资源失败') };
            }
            return { text: await apiFetch<string>(resourceUrl, { responseType: 'text' }, '加载资源失败') };
          });
        }
        if (!cancelled) setText(html);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载产物失败');
      });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [url, kind, sessionId]);

  // 带鉴权端点用 blob 下载：直接 a.href=url 不会带 header，会 401。
  const downloadWithAuth = async () => {
    try {
      const blob = await apiFetch<Blob>(url, { responseType: 'blob' }, '下载产物失败');
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = tab.title;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载产物失败');
    }
  };

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <FileText size={26} className="text-[var(--muted-foreground)]" />
        <p className="text-xs text-[var(--muted-foreground)]">{error}</p>
        <button type="button" onClick={downloadWithAuth} className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)]">重试下载</button>
      </div>
    );
  }

  if (kind === 'html') {
    if (text == null) return <div className="flex h-full items-center justify-center text-xs text-[var(--muted-foreground)]">正在加载预览…</div>;
    return (
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--border-subtle)] px-3 py-2">
          <span className="truncate text-[11px] text-[var(--muted-foreground)]">{tab.title}</span>
          <button type="button" onClick={downloadWithAuth} className="inline-flex items-center gap-1 text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"><Download size={12} />下载</button>
        </div>
        <iframe
          title={tab.title}
          srcDoc={text}
          sandbox="allow-scripts allow-forms allow-popups"
          className="min-h-0 w-full flex-1 border-0 bg-white"
        />
      </div>
    );
  }

  if (kind === 'image') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-4">
        {blobUrl ? (
          <img src={blobUrl} alt={tab.title} className="max-h-full max-w-full rounded-lg border border-[var(--border-subtle)] object-contain" />
        ) : (
          <p className="text-xs text-[var(--muted-foreground)]">正在加载图片…</p>
        )}
        <button type="button" onClick={downloadWithAuth} className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)]"><Download size={12} />下载图片</button>
      </div>
    );
  }

  // csv / json / txt / md / css / js：文本预览；xlsx 只提供下载。
  const ext = (tab.title.split('.').pop() ?? '').toLowerCase();
  const canPreview = ['csv', 'json', 'txt', 'md', 'css', 'js'].includes(ext);
  // 代码类文件用语法高亮（与聊天代码块同一套 Prism + vscDarkPlus）；
  // txt/csv 走纯文本，避免误高亮 + 保留换行可读性。
  const highlightLanguage: Record<string, string> = {
    css: 'css', js: 'javascript', json: 'json', md: 'markdown', html: 'html', htm: 'html', svg: 'xml',
  };
  const language = highlightLanguage[ext];
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--border-subtle)] px-3 py-2">
        <span className="truncate text-[11px] text-[var(--muted-foreground)]">{tab.title}</span>
        <button type="button" onClick={downloadWithAuth} className="inline-flex items-center gap-1 text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"><Download size={12} />下载</button>
      </div>
      {canPreview ? (
        text == null ? (
          <p className="p-4 text-xs text-[var(--muted-foreground)]">正在加载…</p>
        ) : language ? (
          <div className="min-h-0 flex-1 overflow-auto bg-[#0d0d0c]">
            <SyntaxHighlighter
              language={language}
              style={vscDarkPlus}
              PreTag="div"
              showLineNumbers
              customStyle={{ margin: 0, padding: '0.85rem 1rem', background: 'transparent', fontSize: '11px', lineHeight: '1.7' }}
              codeTagProps={{ style: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' } }}
            >
              {text}
            </SyntaxHighlighter>
          </div>
        ) : (
          <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-[11px] leading-relaxed text-[var(--foreground)]">{text}</pre>
        )
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <FileText size={26} className="text-[var(--muted-foreground)]" />
          <p className="text-xs text-[var(--muted-foreground)]">该格式请在下载后用本地软件打开。</p>
        </div>
      )}
    </div>
  );
};

/** 标签内容：按类型在侧栏内就地渲染 */
const TabBody: React.FC<{ tab: SidebarTab; sessionId: string | null; messages: Message[]; workspaceOutputs?: import('../../lib/workspaceArtifacts').WorkspaceEntry[] }> = ({ tab, sessionId, messages, workspaceOutputs = [] }) => {
  const setArtifact = useChatStore((s) => s.setArtifact);
  const closeSidebarTab = useChatStore((s) => s.closeSidebarTab);

  // 功能面板：复用已有的会话级面板组件（产物库 / 文件树 / 运行日志）
  if (tab.kind === 'files' || tab.kind === 'run-log' || tab.kind === 'artifacts') {
    const props = { sessionId: sessionId ?? '', messages, onClose: () => closeSidebarTab(tab.id), workspaceOutputs };
    if (tab.kind === 'files') return <FilesPanel {...props} />;
    if (tab.kind === 'run-log') return <RunLogPanel {...props} />;
    return <ArtifactsPanel {...props} />;
  }

  // 工作区文件产物（html / csv / xlsx / json / txt / md / 图片）：就地预览 + 下载
  if (tab.kind === 'output') {
    return <OutputTabBody tab={tab} sessionId={sessionId} />;
  }

  // PPT：**必须复用 PptArtifactPanel**，不能只渲染裸 iframe。
  // 主题切换 / 导出 PPTX / 发布到作品库这些按钮长在该面板上，
  // 之前侧栏直接 srcDoc 预览 HTML，用户看到的是"没有工具栏的空壳"。
  if (tab.kind === 'ppt' && tab.artifact?.language === 'ppt') {
    const pptArtifact = tab.artifact;
    return (
      <PptArtifactPanel
        // sessionId 必须兜底成侧栏当前的会话：PublishToGalleryButton 的
        // 渲染条件是 artifactId && sessionId，而从历史消息还原的 artifact
        // 可能没带 sessionId（collectTabs 的入参为空时）—— 那会让"发布到
        // 作品库"按钮凭空消失。
        artifact={{ ...pptArtifact, sessionId: pptArtifact.sessionId || sessionId || undefined }}
        onClose={() => {}}
        // 主题切换后要把新 HTML 回写到全局 artifact：
        // 面板内部已 setHtml 保证预览立即刷新，这里再同步一份给「重开产物」
        // 与主区域面板 —— 否则侧栏切完主题、关掉再重开，又回到旧主题。
        onThemeChange={(newHtml, theme) => {
          setArtifact({
            ...pptArtifact,
            html: newHtml,
            theme,
            sessionId: pptArtifact.sessionId || sessionId || undefined,
          });
        }}
        // 侧栏宽度有限，面板自身的 60% 宽度动画在侧栏里会挤成 0，
        // 用 compact 让它铺满容器、去掉侧边栏专属的内边距。
        compact
      />
    );
  }

  // 网站：vue/react 是带路由的 SPA，srcDoc 内联会**劫持父文档路由**
  //（hash router 启动时 replaceState 以父文档为 base → iframe 导航到
  // AgenticOS 自己）。这类栈一律现签 preview_url 用子路径托管；
  // vanilla（无路由脚本）srcDoc 安全，保留内联兜底。
  if (tab.kind === 'website') {
    return <WebsiteTabBody key={tab.id} tab={tab} sessionId={sessionId} />;
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
