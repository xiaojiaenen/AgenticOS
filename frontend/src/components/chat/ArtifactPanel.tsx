import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { CodeIcon, RefreshIcon, DownloadIcon, AlertCircleIcon } from '../ui/AnimatedIcons';
import { cn } from '../../lib/utils';
import { MotionValue } from 'motion/react';

interface ArtifactPanelProps {
  artifact: { code: string; language: string } | null;
  onClose: () => void;
  borderColor: MotionValue<string>;
}

export const ArtifactPanel: React.FC<ArtifactPanelProps> = ({ artifact, onClose, borderColor }) => {
  if (!artifact) return null;

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '60%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="h-full bg-white/40 backdrop-blur-3xl flex flex-col z-20 relative border-l ring-1 ring-white/70"
      style={{ borderColor }}
    >
      {/* Decorative background element */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(24,24,27,0.03),transparent)] pointer-events-none" />
      
      <div className="h-14 border-b border-slate-200/80 flex items-center justify-between px-6 bg-white/80 backdrop-blur-md flex-shrink-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-zinc-900 flex items-center justify-center text-white shadow-lg shadow-zinc-900/20 border border-white/20">
            <CodeIcon size={18} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-800 leading-none">预览画布</h2>
            <div className="flex items-center gap-1.5 mt-1">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">
                {artifact.language === 'html' ? 'Live Web Preview' : 'Vector Graphic'}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button 
            onClick={() => {
              const iframe = document.querySelector('iframe[title="Artifact Preview"]') as HTMLIFrameElement;
              if (iframe) iframe.srcdoc = artifact.code;
            }}
            className="p-2 text-slate-400 hover:text-zinc-600 hover:bg-slate-100 rounded-xl transition-all"
            title="刷新预览"
          >
            <RefreshIcon size={16} />
          </button>
          <button 
            onClick={() => {
              navigator.clipboard.writeText(artifact.code);
            }}
            className="p-2 text-slate-400 hover:text-zinc-600 hover:bg-slate-100 rounded-xl transition-all"
            title="复制代码"
          >
            <CodeIcon size={16} />
          </button>
          <button 
            onClick={() => {
              const blob = new Blob([artifact.code], { type: artifact.language === 'html' ? 'text/html' : 'image/svg+xml' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `artifact.${artifact.language === 'html' ? 'html' : 'svg'}`;
              a.click();
            }}
            className="p-2 text-slate-400 hover:text-zinc-600 hover:bg-slate-100 rounded-xl transition-all"
            title="下载文件"
          >
            <DownloadIcon size={16} />
          </button>
          <div className="w-px h-4 bg-slate-200 mx-2" />
          <button 
            onClick={onClose} 
            className="p-2 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-xl transition-all group"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:rotate-90 transition-transform duration-300"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
      </div>
      
      <div className="flex-1 p-4 md:p-6 overflow-hidden z-10">
        <motion.div 
          initial={{ opacity: 0, scale: 0.98, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="w-full h-full bg-white rounded-[32px] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.08)] border border-slate-200/60 overflow-hidden relative group"
        >
          {/* Browser-like top bar */}
          <div className="h-8 bg-slate-50/80 border-b border-slate-100 flex items-center px-4 gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-slate-200" />
            <div className="w-2.5 h-2.5 rounded-full bg-slate-200" />
            <div className="w-2.5 h-2.5 rounded-full bg-slate-200" />
            <div className="ml-2 h-4 w-32 bg-slate-200/50 rounded-full" />
          </div>

          {artifact.language === 'html' ? (
            <iframe 
              srcDoc={artifact.code} 
              className="w-full h-[calc(100%-2rem)] border-0" 
              sandbox="allow-scripts allow-same-origin" 
              title="Artifact Preview"
            />
          ) : artifact.language === 'svg' ? (
            <div className="w-full h-[calc(100%-2rem)] flex items-center justify-center p-12 bg-[url('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAMUlEQVQ4T2NkYGAQYcAP3MChWEHIIZJkOsBOfBDPIeZHmGZ4iP8hzCHmRzhmoPkRvqc9QDQTICD9LxVfAAAAAElFTkSuQmCC')] bg-center">
              <div className="max-w-full max-h-full drop-shadow-2xl" dangerouslySetInnerHTML={{ __html: artifact.code }} />
            </div>
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 gap-4">
              <div className="w-16 h-16 rounded-full bg-slate-50 flex items-center justify-center">
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
