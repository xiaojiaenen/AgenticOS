/**
 * PPT 生成中的实时预览（轮询 save_slide 产出的 SVG 片段）。
 *
 * **设计取舍（用户反馈后重做）**：
 *
 * 1. **不再自建 35% 右栏抢宽度**。原来它是独立 <aside>，与 ChatArtifactArea
 *    的 60% 产物面板并存 —— 生成一开始 artifact 就被置上，两个面板同时挤占
 *    宽度，聊天区被压到 40%（截图里"界面样式变了 + 右侧一片黑"）。
 *    现在它只在**没有成品产物**时出现，且由调用方决定容器。
 *
 * 2. **不再写死 THEME_VARS**。原来内置一套蓝白变量覆盖 SVG 的
 *    `var(--token)`，导致「不管选了什么主题预览都是蓝白」—— 用户报的
 *    "主题显示不对"就是它。后端 `resolve_token_values` 已把主题变量解析成
 *    具体色值，直接渲染即可。
 *
 * 3. **不再硬编码 bg-white / slate-\***。深色模式下原来是一块亮白底。
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion } from 'motion/react';
import { Presentation, RefreshCcw } from 'lucide-react';
import { authHeaders } from '../../services/authService';
import { cn } from '../../lib/utils';

export interface SlideData {
  num: number;
  svg: string;
  updated_at: number;
}

interface SlideLivePreviewProps {
  sessionId: string | null;
  isStreaming: boolean;
  hasArtifact: boolean;
  /** 内嵌模式：铺满容器、去外层边框与宽度动画（侧栏标签用） */
  compact?: boolean;
}

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

/** 轮询生成中的幻灯片（save_slide 落盘后 2s 内可见）。供侧栏复用。 */
export function useSlideLiveData(
  sessionId: string | null,
  isStreaming: boolean,
  hasArtifact: boolean,
) {
  const [slides, setSlides] = useState<SlideData[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchSlides(sessionId);
    if (data.length > 0) setSlides(data);
  }, [sessionId]);

  useEffect(() => {
    setSlides([]);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || !isStreaming || hasArtifact) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (hasArtifact) setSlides([]);
      return;
    }
    void poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [sessionId, isStreaming, hasArtifact, poll]);

  return { slides, refresh: poll };
}

/**
 * 幻灯片列表（纯内容，无外层容器）。
 *
 * 每页 SVG 直接渲染 —— 后端已把 `var(--token)` 解析成具体色值，
 * 这里再套一层自定义变量只会覆盖主题（"主题显示不对"的根因）。
 */
export const SlideLiveList: React.FC<{ slides: SlideData[]; className?: string }> = ({
  slides,
  className,
}) => (
  <div className={cn('space-y-3', className)}>
    {slides.map(({ num, svg }) => (
      <motion.div
        key={num}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] shadow-sm"
      >
        <div
          className="aspect-[16/9] overflow-hidden [&>svg]:h-full [&>svg]:w-full"
          dangerouslySetInnerHTML={{
            __html: svg.replace(/<svg/, '<svg style="width:100%;height:100%"'),
          }}
        />
        <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-3 py-2">
          <span className="text-[11px] font-semibold text-[var(--foreground)]">第 {num} 页</span>
          <span className="text-[10px] font-medium text-[var(--success)]">已保存</span>
        </div>
      </motion.div>
    ))}
  </div>
);

/**
 * 生成中的实时预览面板。
 *
 * 与 ChatArtifactArea 的 PptArtifactPanel **互斥**（按 hasArtifact）：
 * 生成中看这里（轮询增量 SVG），产物就绪后由成品面板接管（主题/导出/编辑）。
 */
export const SlideLivePreview: React.FC<SlideLivePreviewProps> = ({
  sessionId,
  isStreaming,
  hasArtifact,
  compact = false,
}) => {
  const { slides, refresh } = useSlideLiveData(sessionId, isStreaming, hasArtifact);

  if (!isStreaming || slides.length === 0 || hasArtifact) return null;

  const body = (
    <>
      <div
        className={cn(
          'flex flex-shrink-0 items-center gap-3 border-b border-[var(--border-subtle)]',
          compact ? 'h-10 px-2.5' : 'h-14 px-6',
        )}
      >
        <div
          className={cn(
            'flex flex-shrink-0 items-center justify-center rounded-lg bg-[var(--surface-3)] text-[var(--foreground)]',
            compact ? 'h-6 w-6' : 'h-9 w-9',
          )}
        >
          <Presentation size={compact ? 12 : 16} />
        </div>
        <div className="min-w-0">
          <h2
            className={cn(
              'font-semibold leading-none text-[var(--foreground)]',
              compact ? 'text-[11px]' : 'text-sm',
            )}
          >
            实时预览
          </h2>
          <p className="mt-1 text-[10px] font-medium tracking-wider text-[var(--muted-foreground)]">
            {slides.length} 页 · 生成中
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="ml-auto rounded-md p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          title="刷新"
        >
          <RefreshCcw size={13} />
        </button>
      </div>
      <div className={cn('min-h-0 flex-1 overflow-y-auto', compact ? 'p-2.5' : 'p-4')}>
        <SlideLiveList slides={slides} />
      </div>
    </>
  );

  if (compact) {
    return <div className="flex h-full flex-col">{body}</div>;
  }

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '32%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--surface-1)]"
    >
      {body}
    </motion.aside>
  );
};
