import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion } from 'motion/react';
import { Presentation, RefreshCcw } from 'lucide-react';
import { authHeaders } from '../../services/authService';

interface SlideData {
  num: number;
  svg: string;
  updated_at: number;
}

interface SlideLivePreviewProps {
  sessionId: string | null;
  isStreaming: boolean;
  hasArtifact: boolean;
}

const THEME_VARS: React.CSSProperties = {
  '--bg': '#ffffff', '--bg-soft': '#f8fafc', '--surface': '#f1f5f9',
  '--surface-2': '#e2e8f0', '--border': '#e2e8f0', '--border-strong': '#cbd5e1',
  '--text-1': '#0f172a', '--text-2': '#475569', '--text-3': '#94a3b8',
  '--accent': '#2563eb', '--accent-2': '#7c3aed', '--accent-3': '#0891b2',
  '--good': '#16a34a', '--warn': '#d97706', '--bad': '#dc2626',
} as React.CSSProperties;

async function fetchSlides(sessionId: string): Promise<SlideData[]> {
  try {
    const res = await fetch(`/api/v1/agent/ppt/slides/${sessionId}`, {
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.slides || [];
  } catch {
    return [];
  }
}

export const SlideLivePreview: React.FC<SlideLivePreviewProps> = ({ sessionId, isStreaming, hasArtifact }) => {
  const [slides, setSlides] = useState<SlideData[]>([]);
  const [lastUpdate, setLastUpdate] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchSlides(sessionId);
    if (data.length > 0) {
      setSlides(data);
      setLastUpdate(Date.now());
    }
  }, [sessionId]);

  // sessionId 变化时立即清空旧预览
  useEffect(() => {
    setSlides([]);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || !isStreaming || hasArtifact) {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      if (hasArtifact) setSlides([]);
      return;
    }
    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => { if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; } };
  }, [sessionId, isStreaming, hasArtifact, poll]);

  if (!isStreaming || slides.length === 0 || hasArtifact) return null;

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '35%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col overflow-hidden border-l border-slate-200/60 bg-white/60 backdrop-blur-xl"
    >
      <div className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-slate-200/80 bg-white/80 px-6 backdrop-blur-md">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-sky-500 text-white shadow-lg shadow-sky-500/20">
          <Presentation size={18} />
        </div>
        <div>
          <h2 className="text-sm font-bold leading-none text-slate-800">实时预览</h2>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">{slides.length} slides</p>
        </div>
        <button type="button" onClick={poll} className="ml-auto rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600" title="刷新">
          <RefreshCcw size={14} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {slides.map(({ num, svg }) => (
          <motion.div key={num} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-md" style={THEME_VARS}>
            <div className="aspect-[16/9] overflow-hidden" dangerouslySetInnerHTML={{ __html: svg.replace(/<svg/, '<svg style="width:100%;height:100%"') }} />
            <div className="border-t border-slate-100 px-3 py-2 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-700">第 {num} 页</span>
              <span className="text-[10px] font-medium text-emerald-600">✓ 已保存</span>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.aside>
  );
};
