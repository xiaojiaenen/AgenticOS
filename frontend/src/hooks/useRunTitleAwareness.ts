/**
 * 浏览器标签页的运行状态感知。
 *
 * 为什么：agent 一轮可能跑几分钟（网站生成、多步工具链）。用户切到别的
 * 标签页干活时，唯一的「还在跑 / 跑完了」线索就是标签页标题 —— 没有它，
 * 要么反复切回来盯，要么跑完了很久都不知道。
 *
 * 行为：
 * - 运行中：`● 生成中 — AgenticOS`（● 让标签在窄宽度下也可辨认）
 * - 结束恢复标题；若页面处于后台（document.hidden），短暂闪一下
 *   「✓ 已完成」再恢复 —— 用户不在这个页也能注意到完成事件
 * - 卸载时无条件恢复原标题，避免 SPA 路由切换后标题残留
 */
import { useEffect, useRef } from 'react';

const BASE_TITLE = document.title || 'AgenticOS';

export type RunPhase =
  | 'idle' | 'thinking' | 'streaming'
  | 'generating_ppt' | 'rendering_ppt' | 'rendering_website'
  | 'done' | 'error';

const RUNNING_PHASES: Set<RunPhase> = new Set([
  'thinking', 'streaming', 'generating_ppt', 'rendering_ppt', 'rendering_website',
]);

export function useRunTitleAwareness(phase: RunPhase, label?: string): void {
  // 记住运行前的标题：恢复时用「进入运行态那一刻」的标题，而不是模块常量
  // （别的代码也可能改标题）。
  const titleBeforeRun = useRef<string | null>(null);
  const wasRunning = useRef(false);

  useEffect(() => {
    const running = RUNNING_PHASES.has(phase);

    if (running) {
      if (!wasRunning.current) titleBeforeRun.current = document.title;
      wasRunning.current = true;
      document.title = `● ${label || '运行中'} — ${BASE_TITLE}`;
      return;
    }

    if (wasRunning.current) {
      wasRunning.current = false;
      const finishedOk = phase === 'done';
      const restore = () => {
        document.title = titleBeforeRun.current ?? BASE_TITLE;
        titleBeforeRun.current = null;
      };
      if (finishedOk && document.hidden) {
        // 后台完成：给一个 2.5s 的可注意信号，然后恢复
        document.title = `✓ 已完成 — ${BASE_TITLE}`;
        const timer = window.setTimeout(restore, 2500);
        return () => window.clearTimeout(timer);
      }
      restore();
    }
  }, [phase, label]);

  // 卸载兜底：组件树卸载（路由切换）时标题必须回到原样
  useEffect(() => {
    return () => {
      if (titleBeforeRun.current !== null) {
        document.title = titleBeforeRun.current;
        titleBeforeRun.current = null;
      }
    };
  }, []);
}
