import React from 'react';
import { motion } from 'motion/react';
import { Download, LayoutDashboard, RefreshCcw, X } from 'lucide-react';
import { MotionValue } from 'motion/react';
import { Artifact } from '../../types';
import { buildSandboxedHtmlDocument } from '../../lib/safePreview';

type PptArtifactPanelProps = {
  artifact: Extract<Artifact, { language: 'ppt' }>;
  onClose: () => void;
  borderColor: MotionValue<string>;
};

type ExportToPptxFn = (
  target: string | Element | Element[] | NodeList,
  options?: { fileName?: string; width?: number; height?: number; layout?: string; transition?: string },
) => Promise<void>;

let domToPptxReady: Promise<ExportToPptxFn> | null = null;

function loadDomToPptx(): Promise<ExportToPptxFn> {
  if (domToPptxReady) return domToPptxReady;
  domToPptxReady = new Promise((resolve, reject) => {
    const win = window as unknown as Record<string, unknown>;
    const domToPptx = win.domToPptx as Record<string, unknown> | undefined;
    if (typeof domToPptx?.exportToPptx === 'function') {
      resolve(domToPptx.exportToPptx as ExportToPptxFn);
      return;
    }
    // Remove any previously loaded script to force re-fetch
    const oldScript = document.querySelector('script[src="/vendor/dom-to-pptx.js"]');
    if (oldScript) oldScript.remove();
    const script = document.createElement('script');
    script.src = '/vendor/dom-to-pptx.js';
    script.onload = () => {
      const lib = (window as unknown as Record<string, unknown>).domToPptx as Record<string, unknown> | undefined;
      if (typeof lib?.exportToPptx === 'function') {
        resolve(lib.exportToPptx as ExportToPptxFn);
      } else {
        domToPptxReady = null;
        reject(new Error('exportToPptx not found after script load'));
      }
    };
    script.onerror = () => {
      domToPptxReady = null;
      reject(new Error('Failed to load dom-to-pptx bundle'));
    };
    document.head.appendChild(script);
  });
  return domToPptxReady;
}

export const PptArtifactPanel: React.FC<PptArtifactPanelProps> = ({ artifact, onClose, borderColor }) => {
  const [isExporting, setIsExporting] = React.useState(false);
  const iframeRef = React.useRef<HTMLIFrameElement | null>(null);
  const previewSrcDoc = React.useMemo(() => buildSandboxedHtmlDocument(artifact.html), [artifact.html]);

  const handleExport = async () => {
    setIsExporting(true);
    let tempContainer: HTMLDivElement | null = null;
    try {
      await document.fonts?.ready;
      const exportToPptx = await loadDomToPptx();

      // Load artifact.html in an invisible iframe (opacity:0, not off-screen)
      // so that innerText-based content detection in dom-to-pptx works.
      const exportFrame = document.createElement('iframe');
      exportFrame.style.position = 'fixed';
      exportFrame.style.top = '0';
      exportFrame.style.left = '0';
      exportFrame.style.width = '1280px';
      exportFrame.style.height = '720px';
      exportFrame.style.opacity = '0';
      exportFrame.style.pointerEvents = 'none';
      exportFrame.style.zIndex = '-1';
      exportFrame.srcdoc = artifact.html;
      document.body.appendChild(exportFrame);
      tempContainer = exportFrame;

      // Wait for the iframe to load
      await new Promise<void>((resolve, reject) => {
        exportFrame.onload = () => resolve();
        exportFrame.onerror = () => reject(new Error('Export iframe failed to load'));
        // Timeout fallback
        setTimeout(() => resolve(), 3000);
      });

      const iframeDoc = exportFrame.contentDocument;
      if (!iframeDoc) {
        console.warn('[PPTX Export] Cannot access iframe document');
        return;
      }

      const slides = iframeDoc.querySelectorAll('.deck .slide');
      console.log(`[PPTX Export] Found ${slides.length} slides in iframe`);

      // Force layout so innerText is available for dom-to-pptx content detection
      slides.forEach((s, i) => {
        const el = s as HTMLElement;
        const h = el.offsetHeight;
        const text = el.innerText?.trim().slice(0, 60);
        console.log(`[PPTX Export] slide ${i + 1}: offsetHeight=${h}, innerText="${text}"`);
      });

      if (slides.length > 0) {
        await exportToPptx(slides, {
          fileName: `${artifact.title || 'AgenticOS-PPT'}.pptx`,
          layout: 'LAYOUT_16x9',
        });
        console.log('[PPTX Export] Done');
      } else {
        console.warn('[PPTX Export] No .slide elements found');
      }
    } catch (err) {
      console.error('[PPTX Export] Error:', err);
    } finally {
      tempContainer?.remove();
      setIsExporting(false);
    }
  };

  return (
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
                {artifact.slideCount} slides · editable pptx
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
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
            sandbox="allow-same-origin allow-scripts"
            allow="fullscreen"
            referrerPolicy="no-referrer"
          />
        </motion.div>
      </div>
    </motion.aside>
  );
};
