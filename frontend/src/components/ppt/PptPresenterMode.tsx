import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronLeft, ChevronRight, Play, X } from 'lucide-react';
import { buildSandboxedHtmlDocument } from '../../lib/safePreview';

type PptPresenterModeProps = {
  html: string;
  slideCount: number;
  title: string;
  onClose: () => void;
};

/**
 * Presenter Mode — fullscreen slide-by-slide presentation with speaker notes.
 *
 * Inspired by open-design's html-ppt Presenter Mode (S key).
 *
 * Features:
 * - Fullscreen SVG slide display
 * - Keyboard navigation (← → arrows, Space, Escape)
 * - Bottom floating counter (01 / 08)
 * - Side panel: speaker notes + timer
 * - Auto-detects <!-- notes: ... --> from SVG
 */
export const PptPresenterMode: React.FC<PptPresenterModeProps> = ({
  html,
  slideCount,
  title,
  onClose,
}) => {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [showNotes, setShowNotes] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  // Parse slides from the HTML document
  const slides = useMemo(() => {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const svgs = doc.querySelectorAll('svg');
      return Array.from(svgs).map((svg, i) => {
        const svgStr = new XMLSerializer().serializeToString(svg);
        // Extract notes from <!-- notes: ... --> comment
        const notesMatch = svgStr.match(/<!--\s*notes?:\s*(.*?)-->/s);
        return {
          index: i,
          svg: svgStr,
          notes: notesMatch ? notesMatch[1].trim() : '',
        };
      });
    } catch {
      return [];
    }
  }, [html]);

  const current = slides[currentSlide];
  const total = slides.length || slideCount;

  // Build single-slide HTML for iframe
  const slideHtml = useMemo(() => {
    if (!current) return '';
    return buildSandboxedHtmlDocument(
      `<div style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:#111;">${current.svg}</div>`
    );
  }, [current]);

  // Keyboard navigation
  const goNext = useCallback(() => {
    setCurrentSlide((p) => Math.min(p + 1, total - 1));
  }, [total]);

  const goPrev = useCallback(() => {
    setCurrentSlide((p) => Math.max(p - 1, 0));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault();
        goNext();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goPrev();
      } else if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'n' || e.key === 'N') {
        setShowNotes((s) => !s);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goNext, goPrev, onClose]);

  // Timer
  useEffect(() => {
    const interval = setInterval(() => setElapsed((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  if (!current) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex bg-black"
      >
        {/* Main slide area */}
        <div className="relative flex-1 flex items-center justify-center bg-[#111]">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentSlide}
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -40 }}
              transition={{ duration: 0.25 }}
              className="h-full w-full"
            >
              <iframe
                srcDoc={slideHtml}
                title={`Slide ${currentSlide + 1}`}
                className="h-full w-full border-0"
                sandbox="allow-scripts"
              />
            </motion.div>
          </AnimatePresence>

          {/* Navigation arrows */}
          <button
            onClick={goPrev}
            disabled={currentSlide === 0}
            className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white backdrop-blur-sm transition hover:bg-white/20 disabled:opacity-20"
            aria-label="上一页"
          >
            <ChevronLeft size={24} />
          </button>
          <button
            onClick={goNext}
            disabled={currentSlide === total - 1}
            className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white backdrop-blur-sm transition hover:bg-white/20 disabled:opacity-20"
            aria-label="下一页"
          >
            <ChevronRight size={24} />
          </button>

          {/* Bottom counter */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-white/10 px-4 py-2 text-sm font-medium text-white/80 backdrop-blur-sm">
            {String(currentSlide + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
          </div>

          {/* Top controls */}
          <div className="absolute top-4 right-4 flex items-center gap-2">
            <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-mono text-white/60 backdrop-blur-sm">
              {formatTime(elapsed)}
            </span>
            <button
              onClick={onClose}
              className="rounded-full bg-white/10 p-2 text-white/60 backdrop-blur-sm transition hover:bg-white/20 hover:text-white"
              aria-label="退出演示"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Speaker notes panel */}
        {showNotes && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 360, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="flex flex-col border-l border-white/10 bg-[#1a1a1a]"
          >
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-medium text-white/80">
                <Play size={14} />
                演讲者备注
              </div>
              <button
                onClick={() => setShowNotes(false)}
                className="text-xs text-white/40 hover:text-white/60"
              >
                隐藏 (N)
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {current.notes ? (
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/70">
                  {current.notes}
                </p>
              ) : (
                <p className="text-sm text-white/30 italic">本页无备注</p>
              )}
            </div>
            {/* Mini preview of next slide */}
            {currentSlide < total - 1 && (
              <div className="border-t border-white/10 p-4">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-white/30">
                  下一页预览
                </p>
                <div className="overflow-hidden rounded-lg border border-white/10 bg-white/5">
                  <iframe
                    srcDoc={buildSandboxedHtmlDocument(
                      slides[currentSlide + 1]
                        ? `<div style="display:flex;align-items:center;justify-content:center;min-height:200px;background:#111;">${slides[currentSlide + 1].svg}</div>`
                        : ''
                    )}
                    title="Next slide preview"
                    className="h-32 w-full border-0"
                    sandbox="allow-scripts"
                  />
                </div>
              </div>
            )}
          </motion.div>
        )}

        {/* Toggle notes button when hidden */}
        {!showNotes && (
          <button
            onClick={() => setShowNotes(true)}
            className="fixed bottom-6 right-6 z-50 rounded-full bg-white/10 px-4 py-2 text-xs text-white/60 backdrop-blur-sm transition hover:bg-white/20 hover:text-white"
          >
            显示备注 (N)
          </button>
        )}
      </motion.div>
    </AnimatePresence>
  );
};
