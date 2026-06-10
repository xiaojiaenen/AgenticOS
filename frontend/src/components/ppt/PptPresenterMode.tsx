import React, { useCallback, useEffect, useRef, useState } from 'react';
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
 * Presenter Mode — fullscreen slide-by-slide presentation.
 *
 * 使用完整的 PPT HTML（包含 CSS 自定义属性），通过 postMessage
 * 与 iframe 通信实现翻页，确保样式正确渲染。
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
  const [totalSlides, setTotalSlides] = useState(slideCount);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  // 构建演示模式 HTML：注入翻页控制脚本
  const presenterHtml = React.useMemo(() => {
    // 在原始 HTML 基础上注入翻页脚本
    const navScript = `
<script>
(function() {
  // 获取所有 slide 元素（svg 或 .slide 容器）
  function getSlides() {
    var svgs = document.querySelectorAll('svg');
    if (svgs.length > 0) return Array.from(svgs);
    var slides = document.querySelectorAll('.slide');
    if (slides.length > 0) return Array.from(slides);
    return [];
  }

  var slides = getSlides();
  var current = 0;

  // 通知父窗口总页数
  window.parent.postMessage({ type: 'ppt-total', total: slides.length }, '*');

  function scrollToSlide(i) {
    current = Math.max(0, Math.min(i, slides.length - 1));
    slides[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.parent.postMessage({ type: 'ppt-slide', index: current }, '*');
  }

  // 监听父窗口的翻页消息
  window.addEventListener('message', function(e) {
    if (!e.data || typeof e.data.type !== 'string') return;
    if (e.data.type === 'ppt-goto') {
      scrollToSlide(e.data.index);
    } else if (e.data.type === 'ppt-next') {
      scrollToSlide(current + 1);
    } else if (e.data.type === 'ppt-prev') {
      scrollToSlide(current - 1);
    }
  });

  // 监听滚动事件同步当前页码
  var scrollTimer = null;
  window.addEventListener('scroll', function() {
    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(function() {
      var viewCenter = window.innerHeight / 2;
      for (var i = 0; i < slides.length; i++) {
        var rect = slides[i].getBoundingClientRect();
        if (rect.top <= viewCenter && rect.bottom >= viewCenter) {
          if (current !== i) {
            current = i;
            window.parent.postMessage({ type: 'ppt-slide', index: current }, '*');
          }
          break;
        }
      }
    }, 100);
  });
})();
</script>`;
    // 注入到 </body> 前
    if (html.includes('</body>')) {
      return html.replace('</body>', navScript + '</body>');
    }
    return html + navScript;
  }, [html]);

  const slideHtml = React.useMemo(
    () => buildSandboxedHtmlDocument(presenterHtml),
    [presenterHtml],
  );

  // 监听 iframe 消息
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (!e.data || typeof e.data.type !== 'string') return;
      if (e.data.type === 'ppt-total') {
        setTotalSlides(e.data.total || slideCount);
      } else if (e.data.type === 'ppt-slide') {
        setCurrentSlide(e.data.index || 0);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [slideCount]);

  // 发送翻页命令到 iframe
  const sendCommand = useCallback((type: string, index?: number) => {
    iframeRef.current?.contentWindow?.postMessage(
      index !== undefined ? { type, index } : { type },
      '*',
    );
  }, []);

  const goNext = useCallback(() => sendCommand('ppt-next'), [sendCommand]);
  const goPrev = useCallback(() => sendCommand('ppt-prev'), [sendCommand]);

  // 键盘导航
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

  // 计时器
  useEffect(() => {
    const interval = setInterval(() => setElapsed((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex bg-black"
      >
        {/* 主幻灯片区域 */}
        <div className="relative flex-1 flex items-center justify-center bg-[#111]">
          <iframe
            ref={iframeRef}
            srcDoc={slideHtml}
            title={title}
            className="h-full w-full border-0"
            sandbox="allow-scripts allow-same-origin"
            allow="fullscreen"
          />

          {/* 导航箭头 */}
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
            disabled={currentSlide >= totalSlides - 1}
            className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white backdrop-blur-sm transition hover:bg-white/20 disabled:opacity-20"
            aria-label="下一页"
          >
            <ChevronRight size={24} />
          </button>

          {/* 底部计数器 */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-white/10 px-4 py-2 text-sm font-medium text-white/80 backdrop-blur-sm">
            {String(currentSlide + 1).padStart(2, '0')} / {String(totalSlides).padStart(2, '0')}
          </div>

          {/* 顶部控制栏 */}
          <div className="absolute top-4 right-4 flex items-center gap-2">
            <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-mono text-white/60 backdrop-blur-sm">
              {formatTime(elapsed)}
            </span>
            <button
              onClick={() => setShowNotes((s) => !s)}
              className="rounded-full bg-white/10 px-3 py-1.5 text-xs text-white/60 backdrop-blur-sm transition hover:bg-white/20 hover:text-white"
              aria-label="切换备注"
            >
              <Play size={14} />
            </button>
            <button
              onClick={onClose}
              className="rounded-full bg-white/10 p-2 text-white/60 backdrop-blur-sm transition hover:bg-white/20 hover:text-white"
              aria-label="退出演示"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* 演讲者备注面板 */}
        <AnimatePresence>
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
                <p className="text-sm text-white/30 italic">
                  使用键盘 ← → 或点击箭头翻页，按 N 切换备注面板
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 隐藏备注时的显示按钮 */}
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
