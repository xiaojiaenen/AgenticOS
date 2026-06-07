/**
 * ChatMessage sub-components extracted for performance and maintainability.
 * These were previously defined inside the ChatMessage render function,
 * causing them to be recreated on every render.
 */
import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import mermaid from 'mermaid';
import { BrainCircuit, Globe, Presentation, Sparkles } from 'lucide-react';
import { Artifact, Message, ToolCall } from '../../types';
import { cn, copyToClipboard } from '../../lib/utils';
import { getAppConfig } from '../../services/configService';
import { CopyIcon, CheckIcon, WrenchIcon, ChevronDownIcon } from '../ui/AnimatedIcons';

// ── Constants ──────────────────────────────────────────────────────────────

const TOOL_RESULT_PREVIEW_CHAR_LIMIT = 520;
const TOOL_RESULT_PREVIEW_LINE_LIMIT = 10;

// ── Utility functions ──────────────────────────────────────────────────────

export function normalizeToolResult(result: string): string {
  if (!result) return '';
  return result
    .replace(/(data:image\/[a-zA-Z0-9.+-]+;base64,)[A-Za-z0-9+/=\n\r]{40,}/g, '$1...')
    .replace(/(data:application\/[a-zA-Z0-9.+-]+;base64,)[A-Za-z0-9+/=\n\r]{40,}/g, '$1...');
}

export function buildToolResultPreview(result: string): { text: string; truncated: boolean } {
  if (!result) return { text: '', truncated: false };
  if (result.length <= TOOL_RESULT_PREVIEW_CHAR_LIMIT) {
    if (result.split('\n').length <= TOOL_RESULT_PREVIEW_LINE_LIMIT) return { text: result, truncated: false };
  }
  const lines = result.split('\n');
  const previewLines = lines.slice(0, TOOL_RESULT_PREVIEW_LINE_LIMIT);
  let preview = previewLines.join('\n');
  if (preview.length > TOOL_RESULT_PREVIEW_CHAR_LIMIT) {
    preview = `${preview.slice(0, TOOL_RESULT_PREVIEW_CHAR_LIMIT).trimEnd()}...`;
  } else if (lines.length > TOOL_RESULT_PREVIEW_LINE_LIMIT || result.length > preview.length) {
    preview = `${preview.trimEnd()}\n...`;
  }
  return { text: preview, truncated: true };
}

export function buildToolMetaItems(tool: ToolCall): string[] {
  const items: string[] = [];
  if (tool.sideEffect) items.push('有副作用');
  if (tool.requiresApproval) items.push('需要审批');
  if (tool.toolExecuted === false) items.push('未执行');
  if (tool.retryable) items.push('可重试');
  if (typeof tool.attempts === 'number') items.push(`尝试 ${tool.attempts} 次`);
  if (tool.errorType) items.push(`错误类型 ${tool.errorType}`);
  return items;
}

export function getActiveToolLabel(tool: ToolCall): string {
  const { status, name } = tool;
  if (status === 'approval_required') return `等待审批: ${name}`;
  if (status === 'approved') return `正在执行: ${name}`;
  if (status === 'pending') return `正在调用: ${name}`;
  if (status === 'success') return `已完成: ${name}`;
  if (status === 'error') return `执行失败: ${name}`;
  if (status === 'rejected') return `已拒绝: ${name}`;
  return name;
}

export function isToolActive(tool: ToolCall): boolean {
  return tool.status === 'pending' || tool.status === 'approved' || tool.status === 'approval_required';
}

// ── Sub-components ──────────────────────────────────────────────────────────

export const AnimatedDots = () => (
  <span className="flex items-center gap-1" aria-hidden="true">
    {[0, 1, 2].map((dot) => (
      <motion.span
        key={dot}
        className="h-1.5 w-1.5 rounded-full bg-slate-300"
        animate={{ y: [0, -3, 0], opacity: [0.35, 1, 0.35] }}
        transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut", delay: dot * 0.16 }}
      />
    ))}
  </span>
);

export const AssistantWaitingIndicator = ({ statusText = '正在思考' }: { statusText?: string }) => (
  <div className="flex min-w-[12rem] items-center gap-3 py-1 text-sm font-semibold text-slate-500">
    <span className="relative flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-2xl border border-slate-200/80 bg-slate-50/90 text-slate-400 shadow-inner">
      <BrainCircuit size={15} />
      <motion.span
        className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-sky-400 shadow-[0_0_0_4px_rgba(56,189,248,0.16)]"
        animate={{ scale: [0.85, 1.18, 0.85], opacity: [0.55, 1, 0.55] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
      />
    </span>
    <span className="whitespace-nowrap">{statusText}</span>
    <AnimatedDots />
  </div>
);

export const LiveToolCall = ({ tool }: { tool: ToolCall }) => {
  const active = isToolActive(tool);
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium border",
        active ? "border-sky-200 bg-sky-50/80 text-sky-700"
          : tool.status === 'error' ? "border-rose-200 bg-rose-50/80 text-rose-600"
            : "border-emerald-200 bg-emerald-50/80 text-emerald-600",
      )}
    >
      {active ? (
        <motion.span className="h-3.5 w-3.5 rounded-full border-2 border-sky-400 border-t-transparent" animate={{ rotate: 360 }} transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }} />
      ) : (
        <WrenchIcon size={13} />
      )}
      <span className="font-mono font-bold uppercase tracking-[0.12em] text-[10px]">{getActiveToolLabel(tool)}</span>
    </motion.div>
  );
};

export const ToolResultPreview = ({ result, isError = false }: { result: string; isError?: boolean }) => {
  const [expanded, setExpanded] = useState(false);
  const normalizedResult = normalizeToolResult(result);
  const { text: previewText, truncated } = buildToolResultPreview(normalizedResult);
  const displayedText = expanded || !truncated ? normalizedResult : previewText;

  return (
    <div className="space-y-2">
      <div className="relative">
        <div className={cn(
          "rounded-xl px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all max-w-full overflow-hidden",
          expanded && "max-h-[32rem] overflow-y-auto",
          isError ? "border border-rose-200/90 bg-rose-50/90 text-rose-700" : "border border-slate-200/80 bg-slate-50/90 text-slate-500",
        )}>
          {displayedText}
        </div>
        {!expanded && truncated && (
          <div className={cn(
            "pointer-events-none absolute inset-x-0 bottom-0 h-16 rounded-b-xl",
            isError ? "bg-gradient-to-t from-rose-50/95 via-rose-50/70 to-transparent" : "bg-gradient-to-t from-slate-50/95 via-slate-50/70 to-transparent",
          )} />
        )}
      </div>
      {truncated && (
        <button type="button" onClick={() => setExpanded(v => !v)} className={cn(
          "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] transition-colors",
          isError ? "border-rose-200 bg-white text-rose-600 hover:bg-rose-50" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
        )}>
          <span>{expanded ? '收起结果' : '展开结果'}</span>
          <ChevronDownIcon size={12} className={cn("transition-transform duration-300", expanded && "rotate-180")} />
        </button>
      )}
    </div>
  );
};

export const MermaidChart = React.memo(({ chart }: { chart: string }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgUrl, setSvgUrl] = useState<string>('');
  const [isRendering, setIsRendering] = useState(false);
  const [height, setHeight] = useState<number | 'auto'>('auto');

  useEffect(() => {
    mermaid.initialize({ startOnLoad: true, theme: 'neutral', fontFamily: 'Plus Jakarta Sans', securityLevel: 'strict' });
    let cancelled = false;
    const renderChart = async () => {
      if (!containerRef.current) return;
      setIsRendering(true);
      try {
        if (containerRef.current.offsetHeight > 50) setHeight(containerRef.current.offsetHeight);
        const { svg } = await mermaid.render(`mermaid-${Math.random().toString(36).slice(2, 11)}`, chart);
        if (cancelled) return;
        const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
        setSvgUrl(current => { if (current) URL.revokeObjectURL(current); return url; });
      } catch (e) { console.error('Mermaid render error:', e); }
      finally { if (!cancelled) { setIsRendering(false); setTimeout(() => setHeight('auto'), 100); } }
    };
    renderChart();
    return () => { cancelled = true; setSvgUrl(current => { if (current) URL.revokeObjectURL(current); return ''; }); };
  }, [chart]);

  return (
    <div ref={containerRef} style={{ minHeight: height !== 'auto' ? `${height}px` : undefined }}
      className={cn("bg-slate-50/30 p-6 rounded-2xl border border-slate-200/50 my-2 flex justify-center overflow-x-auto transition-opacity duration-300", isRendering ? "opacity-50" : "opacity-100")}>
      {svgUrl ? <img src={svgUrl} alt="Mermaid chart" className="max-w-full" /> : null}
    </div>
  );
});

export const PptArtifactCard = ({ message, onOpenArtifact }: { message: Message; onOpenArtifact?: (artifact: Artifact) => void }) => {
  const html = message.pptArtifact?.html;
  const status = html ? 'ready' : message.pptArtifact?.status;
  if (!status) return null;
  const isReady = status === 'ready' && Boolean(html);
  const title = message.pptArtifact?.title || 'PPT 演示文稿';
  const slideCount = message.pptArtifact?.slideCount || 0;
  const handleOpen = () => { if (html) onOpenArtifact?.({ language: 'ppt', artifactId: message.pptArtifact?.artifactId, html, title, slideCount }); };

  return (
    <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      className={cn("mb-3 flex w-fit max-w-[34rem] items-center gap-3 rounded-3xl border px-4 py-3 shadow-lg backdrop-blur-xl", isReady ? "border-white/70 bg-white/84" : "border-sky-200/70 bg-sky-50/80")}>
      <div className={cn("flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl text-white", isReady ? "bg-zinc-900" : "bg-sky-500")}>
        {isReady ? <Presentation size={19} /> : <Sparkles size={18} className="animate-pulse" />}
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-black text-slate-900">{isReady ? title : '正在生成 PPT'}</div>
        <div className="mt-0.5 text-[11px] font-medium text-slate-500">{isReady ? `${slideCount} 页 · 可预览和导出 PPTX` : '正在规划内容、图表和版式，请稍候'}</div>
      </div>
      {isReady && <button type="button" onClick={handleOpen} className="ml-2 flex-shrink-0 rounded-full bg-zinc-900 px-3 py-1.5 text-[11px] font-bold text-white transition-colors hover:bg-zinc-800 active:scale-95">打开 PPT</button>}
    </motion.div>
  );
};

export const WebsiteArtifactCard = ({ message, onOpenArtifact }: { message: Message; onOpenArtifact?: (artifact: Artifact) => void }) => {
  const html = message.websiteArtifact?.html;
  const status = html ? 'ready' : message.websiteArtifact?.status;
  if (!status) return null;
  const isReady = status === 'ready' && Boolean(html);
  const title = message.websiteArtifact?.title || 'Website';
  const slug = message.websiteArtifact?.projectSlug || '';
  const stack = message.websiteArtifact?.stack || '';
  const handleOpen = () => { if (html) onOpenArtifact?.({ language: 'website', artifactId: message.websiteArtifact?.artifactId || '', html, title, projectSlug: slug, stack, fileCount: 0 }); };

  return (
    <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      className={cn("mb-3 flex w-fit max-w-[34rem] items-center gap-3 rounded-3xl border px-4 py-3 shadow-lg backdrop-blur-xl", isReady ? "border-white/70 bg-white/84" : "border-emerald-200/70 bg-emerald-50/80")}>
      <div className={cn("flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl text-white", isReady ? "bg-zinc-900" : "bg-emerald-500")}>
        {isReady ? <Globe size={19} /> : <Sparkles size={18} className="animate-pulse" />}
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-black text-slate-900">{isReady ? title : '正在生成网站'}</div>
        <div className="mt-0.5 text-[11px] font-medium text-slate-500">{isReady ? `${stack} · ${slug}` : '正在规划页面结构和内容，请稍候'}</div>
      </div>
      {isReady && <button type="button" onClick={handleOpen} className="ml-2 flex-shrink-0 rounded-full bg-zinc-900 px-3 py-1.5 text-[11px] font-bold text-white transition-colors hover:bg-zinc-800 active:scale-95">预览</button>}
    </motion.div>
  );
};

export const ToolTimelineStep = ({ title, state, body }: { title: string; state: 'done' | 'active' | 'idle'; body: React.ReactNode }) => (
  <div className="grid grid-cols-[1rem_1fr] gap-3">
    <div className="flex flex-col items-center">
      <div className={cn("mt-1 h-3 w-3 rounded-full border-2 transition-colors",
        state === 'done' && "border-emerald-500 bg-emerald-500",
        state === 'active' && "border-sky-500 bg-white shadow-[0_0_0_4px_rgba(56,189,248,0.15)]",
        state === 'idle' && "border-slate-300 bg-white")} />
      <div className={cn("mt-2 h-full min-h-5 w-px", state === 'done' ? "bg-emerald-300/80" : "bg-slate-200")} />
    </div>
    <div className="pb-3">
      <div className={cn("text-[11px] font-bold uppercase tracking-[0.14em]",
        state === 'done' && "text-emerald-600", state === 'active' && "text-sky-600", state === 'idle' && "text-slate-400")}>{title}</div>
      <div className="mt-1 text-xs leading-relaxed text-slate-600">{body}</div>
    </div>
  </div>
);

export const CodeBlock = ({ inline, className, children, onOpenArtifact, ...props }: any) => {
  const [isBlockCopied, setIsBlockCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const codeString = String(children).replace(/\n$/, '');
  const config = getAppConfig();

  if (!inline && match && match[1] === 'mermaid' && config.enableMermaid) return <MermaidChart chart={codeString} />;

  const handleBlockCopy = async () => { await copyToClipboard(codeString); setIsBlockCopied(true); setTimeout(() => setIsBlockCopied(false), 2000); };

  if (!inline && match) {
    if (match[1] === 'widget') {
      try {
        const widgetData = JSON.parse(codeString);
        if (widgetData.type === 'weather') {
          return (
            <div className="bg-gradient-to-br from-blue-400 to-cyan-300 rounded-3xl p-6 text-white my-4 w-72 transform hover:scale-[1.02] transition-transform">
              <div className="flex justify-between items-start mb-4">
                <div><div className="text-sm font-bold opacity-80 uppercase tracking-widest">{widgetData.data.city}</div><div className="text-5xl font-display font-bold mt-1 tracking-tighter">{widgetData.data.temp}</div></div>
                <div className="text-5xl drop-shadow-lg">{widgetData.data.icon}</div>
              </div>
              <div className="mt-2 text-base font-bold bg-white/20 backdrop-blur-md px-3 py-1 rounded-full w-fit">{widgetData.data.condition}</div>
            </div>
          );
        }
      } catch (e) { /* fallback to code block */ }
    }

    const isArtifactable = ['html', 'svg'].includes(match[1]) && config.enableArtifacts;

    return (
      <div className="relative group my-5 overflow-hidden rounded-3xl border border-slate-800/80 bg-zinc-950 shadow-xl ring-1 ring-white/5">
        <div className="flex items-center border-b border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(30,41,59,0.88))] px-4 py-3 backdrop-blur-sm">
          <div className="flex gap-1.5"><div className="w-3 h-3 rounded-full bg-[#ff5f56]" /><div className="w-3 h-3 rounded-full bg-[#ffbd2e]" /><div className="w-3 h-3 rounded-full bg-[#27c93f]" /></div>
          <div className="ml-4 text-[10px] font-bold uppercase tracking-[0.24em] text-slate-400/90 select-none">{match[1]}</div>
          <div className="ml-auto flex items-center gap-4">
            {isArtifactable && onOpenArtifact && (
              <button onClick={() => onOpenArtifact({ code: codeString, language: match[1] as 'html' | 'svg' })} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300 transition-colors hover:text-cyan-200">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg><span>可视化预览</span>
              </button>
            )}
            <button onClick={handleBlockCopy} className="flex items-center justify-center rounded-lg p-1.5 text-slate-400 transition-all hover:bg-white/10 hover:text-white active:scale-90" title={isBlockCopied ? '已复制' : '复制代码'}>
              <AnimatePresence mode="wait" initial={false}>
                {isBlockCopied ? <motion.div key="ok" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}><CheckIcon size={14} className="text-green-400" /></motion.div>
                  : <motion.div key="copy" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}><CopyIcon size={14} /></motion.div>}
              </AnimatePresence>
            </button>
          </div>
        </div>
        <div className="text-sm">
          <SyntaxHighlighter style={vscDarkPlus} language={match[1]} PreTag="div" customStyle={{ margin: 0, padding: '1.35rem 1.4rem', background: 'transparent', fontSize: '0.85rem', lineHeight: '1.7' }} {...props}>
            {codeString}
          </SyntaxHighlighter>
        </div>
      </div>
    );
  }
  return <code className={cn("bg-slate-100 text-teal-800 px-1.5 py-0.5 rounded-md text-sm font-mono font-medium", className)} {...props}>{children}</code>;
};

// ── Table components (extracted from render) ──────────────────────────────

export const MarkdownTable = ({ children }: { children: React.ReactNode }) => (
  <div className="my-5 overflow-hidden rounded-3xl border border-slate-200/90 bg-white/88 shadow-lg ring-1 ring-white/65">
    <div className="h-2 bg-[linear-gradient(90deg,rgba(15,23,42,0.9),rgba(30,41,59,0.85),rgba(34,211,238,0.75))]" />
    <div className="visible-scrollbar overflow-x-auto px-1 pb-2">
      <table className="w-max min-w-full border-collapse text-left text-sm text-slate-700">{children}</table>
    </div>
  </div>
);

export const MarkdownTableHead = ({ children }: { children: React.ReactNode }) => (
  <thead className="bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(30,41,59,0.92))] text-slate-100">{children}</thead>
);

export const MarkdownTableRow = ({ children }: { children: React.ReactNode }) => (
  <tr className="border-b border-slate-200/80 transition-colors even:bg-slate-50/70 hover:bg-sky-50/50 last:border-b-0">{children}</tr>
);
