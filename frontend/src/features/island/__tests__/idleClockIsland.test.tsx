/**
 * 常驻时钟岛：格式、时段问候、让位逻辑。
 *
 * 用户要求"静止状态也加点东西，比如时间常驻，或者一些可爱的对话"。
 * 这里锁住三件最容易出错的事：
 * 1. 时间格式必须是 HH:MM:SS 且补零（"9:5:3" 读起来就不像时钟）
 * 2. 问候语按时段切换（跨零点、跨晌午都要对）
 * 3. 任何真实任务在跑时必须让位 —— 否则会和运行岛并排成 minimal 分裂态，
 *    那是岛上最难看的状态
 *
 * 用真实 store + 手动时钟驱动，不 mock 组件内部。
 */
import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

import { Island, IslandProvider } from '@/lib/island';
import type { IslandClock } from '@/lib/island';
import { IdleClockIsland } from '../IdleClockIsland';
import { useChatStore } from '@/stores/chatStore';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

class ManualClock implements IslandClock {
  time = 0;
  private frames = new Set<(now: number) => void>();
  private timers: { at: number; run: (due: number) => void }[] = [];
  now = () => this.time;
  onFrame = (fn: (now: number) => void) => {
    this.frames.add(fn);
    return () => {
      this.frames.delete(fn);
    };
  };
  at = (at: number, run: (due: number) => void) => {
    this.timers.push({ at, run });
    return () => {
      this.timers = this.timers.filter((t) => t.run !== run);
    };
  };
  advance(ms: number) {
    this.time += ms;
    const due = this.timers.filter((t) => t.at <= this.time).sort((a, b) => a.at - b.at);
    this.timers = this.timers.filter((t) => t.at > this.time);
    for (const t of due) t.run(t.at);
    for (const fn of [...this.frames]) fn(this.time);
  }
}

function mount(clock: ManualClock) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  act(() => {
    root.render(
      <IslandProvider clock={clock}>
        <IdleClockIsland />
        <Island placement="viewport" />
      </IslandProvider>,
    );
  });
  return {
    host,
    clock,
    unmount: () => {
      act(() => root.unmount());
      host.remove();
    },
  };
}

const presentation = (host: HTMLElement) =>
  host.querySelector('[data-islandcn]')?.getAttribute('data-presentation');

const compactText = (host: HTMLElement) =>
  host.querySelector('[data-layer="compact"] [data-slot="trailing"]')?.textContent ?? null;

const label = (host: HTMLElement) =>
  host.querySelector('[data-islandcn-hit="pill"]')?.getAttribute('aria-label') ?? null;

/** 把系统时间固定到某个时刻（组件用 new Date()，只能改系统时钟） */
function freezeAt(iso: string) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(iso));
}

/**
 * 模拟标签页切换。
 * jsdom 的 document.visibilityState 是只读的 getter，必须重定义才能改。
 * 事件类型用普通 Event（组件只读 visibilityState，不读事件 detail）。
 */
function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  });
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

describe('常驻时钟岛', () => {
  beforeEach(() => {
    useChatStore.setState({
      inputValue: '',
      runStatus: { phase: 'idle', label: '已就绪' },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('空闲时显示 HH:MM:SS，且零位补全', () => {
    freezeAt('2026-11-17T09:05:03');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));
    // 09:05:03 —— 关键在补零
    expect(compactText(env.host)).toBe('09:05:03');
    env.unmount();
  });

  it('深夜时段问候是「夜深了」，早晨是「早上好」', () => {
    freezeAt('2026-11-17T03:20:00');
    const env1 = mount(new ManualClock());
    act(() => env1.clock.advance(200));
    expect(label(env1.host)).toContain('夜深了');
    env1.unmount();

    freezeAt('2026-11-17T07:30:00');
    const env2 = mount(new ManualClock());
    act(() => env2.clock.advance(200));
    expect(label(env2.host)).toContain('早上好');
    env2.unmount();
  });

  it('AI 运行中让位（不显示时钟）', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));
    expect(presentation(env.host)).toBe('compact');

    act(() => {
      useChatStore.setState({ runStatus: { phase: 'thinking', label: '思考中' } });
    });
    act(() => env.clock.advance(300));
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('输入中让位（草稿 ≥2 字时不显示时钟）', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));
    expect(presentation(env.host)).toBe('compact');

    act(() => useChatStore.getState().setInputValue('我在打字'));
    act(() => env.clock.advance(300));
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('任务结束后时钟回来', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => {
      useChatStore.setState({ runStatus: { phase: 'streaming', label: '生成回答' } });
    });
    act(() => env.clock.advance(300));
    expect(presentation(env.host)).toBe('idle');

    act(() => {
      useChatStore.setState({ runStatus: { phase: 'idle', label: '已就绪' } });
    });
    act(() => env.clock.advance(400));
    expect(presentation(env.host)).toBe('compact');
    expect(compactText(env.host)).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    env.unmount();
  });

  it('标签页隐藏时岛清空（什么都不显示）', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));
    expect(presentation(env.host)).toBe('compact');

    setVisibility('hidden');
    act(() => env.clock.advance(300));
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('离开够久再回来 → 先显示「你回来啦」，几秒后回到时钟', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));

    setVisibility('hidden');
    act(() => env.clock.advance(100));
    // 离开 10 秒
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    setVisibility('visible');
    act(() => env.clock.advance(300));

    expect(presentation(env.host)).toBe('compact');
    expect(compactText(env.host)).toBe('你回来啦');
    expect(label(env.host)).toContain('欢迎回来');

    // 问候 4 秒后自动回到时钟
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    act(() => env.clock.advance(400));
    expect(compactText(env.host)).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    env.unmount();
  });

  it('只切走一瞬（<1.5s）回来不打招呼，避免误触闪烁', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));

    setVisibility('hidden');
    act(() => {
      vi.advanceTimersByTime(400);
    });
    setVisibility('visible');
    act(() => env.clock.advance(300));

    // 直接是时钟，不是「你回来啦」
    expect(compactText(env.host)).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    env.unmount();
  });

  it('AI 运行中切走再回来，不抢运行岛（招呼让位）', () => {
    freezeAt('2026-11-17T14:00:00');
    const env = mount(new ManualClock());
    act(() => env.clock.advance(200));

    setVisibility('hidden');
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    act(() => {
      useChatStore.setState({ runStatus: { phase: 'streaming', label: '生成回答' } });
    });
    setVisibility('visible');
    act(() => env.clock.advance(300));

    // 有运行任务时，常驻岛整体不挂载
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });
});
