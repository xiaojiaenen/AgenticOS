import React from 'react';
import { motion } from 'motion/react';
import { MotionValue } from 'motion/react';
import { Artifact } from '../../types';
import { buildSandboxedHtmlDocument, createObjectUrl } from '../../lib/safePreview';
import { AlertCircleIcon, CodeIcon, DownloadIcon, RefreshIcon } from '../ui/AnimatedIcons';

interface ArtifactPanelProps {
  artifact: Extract<Artifact, { language: 'html' | 'svg' }> | null;
  onClose: () => void;
  borderColor: MotionValue<string>;
}

export const ArtifactPanel: React.FC<ArtifactPanelProps> = ({ artifact, onClose, borderColor }) => {
  const iframeRef = React.useRef<HTMLIFrameElement | null>(null);
  const [svgUrl, setSvgUrl] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!artifact || artifact.language !== 'svg') {
      setSvgUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
      return;
    }

    const nextUrl = createObjectUrl(artifact.code, 'image/svg+xml');
    setSvgUrl((current) => {
      if (current) {
        URL.revokeObjectURL(current);
      }
      return nextUrl;
    });

    return () => {
      URL.revokeObjectURL(nextUrl);
    };
  }, [artifact]);

  if (!artifact) return null;

  const previewSrcDoc = artifact.language === 'html' ? buildSandboxedHtmlDocument(artifact.code) : '';

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '60%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col border-l bg-white/40 ring-1 ring-white/70 backdrop-blur-3xl"
      style={{ borderColor }}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(24,24,27,0.03),transparent)]" />

      <div className="z-10 flex h-14 flex-shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/80 px-6 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/20 bg-zinc-900 text-white shadow-lg shadow-zinc-900/20">
            <CodeIcon size={18} />
          </div>
          <div>
            <h2 className="text-sm font-bold leading-none text-slate-800">预览画布</h2>
            <div className="mt-1 flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                {artifact.language === 'html' ? 'Live Web Preview' : 'Vector Graphic'}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              if (iframeRef.current && artifact.language === 'html') {
                iframeRef.current.srcdoc = previewSrcDoc;
              }
            }}
            className="rounded-xl p-2 text-slate-400 transition-all hover:bg-slate-100 hover:text-zinc-600"
            title="刷新预览"
          >
            <RefreshIcon size={16} />
          </button>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(artifact.code);
            }}
            className="rounded-xl p-2 text-slate-400 transition-all hover:bg-slate-100 hover:text-zinc-600"
            title="复制代码"
          >
            <CodeIcon size={16} />
          </button>
          <button
            type="button"
            onClick={() => {
              const blob = new Blob([artifact.code], {
                type: artifact.language === 'html' ? 'text/html' : 'image/svg+xml',
              });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement('a');
              anchor.href = url;
              anchor.download = `artifact.${artifact.language === 'html' ? 'html' : 'svg'}`;
              anchor.click();
              URL.revokeObjectURL(url);
            }}
            className="rounded-xl p-2 text-slate-400 transition-all hover:bg-slate-100 hover:text-zinc-600"
            title="下载文件"
          >
            <DownloadIcon size={16} />
          </button>
          <div className="mx-2 h-4 w-px bg-slate-200" />
          <button
            type="button"
            onClick={onClose}
            className="group rounded-xl p-2 text-slate-400 transition-all hover:bg-rose-50 hover:text-rose-500"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="transition-transform duration-300 group-hover:rotate-90"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div className="z-10 flex-1 overflow-hidden p-4 md:p-6">
        <motion.div
          initial={{ opacity: 0, scale: 0.98, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="relative h-full w-full overflow-hidden rounded-[32px] border border-slate-200/60 bg-white shadow-[0_32px_64px_-16px_rgba(0,0,0,0.08)]"
        >
          <div className="flex h-8 items-center gap-1.5 border-b border-slate-100 bg-slate-50/80 px-4">
            <div className="h-2.5 w-2.5 rounded-full bg-slate-200" />
            <div className="h-2.5 w-2.5 rounded-full bg-slate-200" />
            <div className="h-2.5 w-2.5 rounded-full bg-slate-200" />
            <div className="ml-2 h-4 w-32 rounded-full bg-slate-200/50" />
          </div>

          {artifact.language === 'html' ? (
            <iframe
              ref={iframeRef}
              srcDoc={previewSrcDoc}
              className="h-[calc(100%-2rem)] w-full border-0"
              sandbox="allow-scripts"
              referrerPolicy="no-referrer"
              title="Artifact Preview"
            />
          ) : artifact.language === 'svg' ? (
            <div className="flex h-[calc(100%-2rem)] w-full items-center justify-center bg-[url('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAMUlEQVQ4T2NkYGAQYcAP3MChWEHIIZJkOsBOfBDPIeZHmGZ4iP8hzCHmRzhmoPkRvqc9QDQTICD9LxVfAAAAAElFTkSuQmCC')] bg-center p-12">
              {svgUrl ? <img src={svgUrl} alt="SVG Preview" className="max-h-full max-w-full drop-shadow-2xl" /> : null}
            </div>
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-4 text-slate-400">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-50">
                <AlertCircleIcon size={32} />
              </div>
              <p className="text-sm font-medium">暂不支持预览 {artifact.language} 格式</p>
            </div>
          )}
        </motion.div>
      </div>
    </motion.aside>
  );
};
