/**
 * 走时刷新粒度回归 —— 岛的性能底线。
 *
 * 背景：岛引擎的帧循环是**按需静止**的（`surface.tsx` 在所有弹簧静止后
 * `unsubscribe()` 掉 rAF）。每次 activity update 都会把它重新叫醒跑
 * 300–500ms。所以「空胶囊上要不要每秒刷新」不是观感问题，而是 CPU 问题：
 * 每秒一次 update ≈ 让静止页面持续以 60fps 跑近一半时间。
 *
 * 因此约定：
 * - 紧凑胶囊只显示 HH:MM，**一分钟**才更新一次
 * - 秒级跳动只在展开视图里（用户正盯着看）
 * - 页面切到后台时停表（后台标签不该有任何定时器在跑）
 *
 * 这几条都在这里钉死，任何人把「秒」加回紧凑态都会撞红。
 */
import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

import { useSecondTick, useTieredTick, subscribeSecond } from '../secondTicker';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function mountHook<T>(useHook: () => T): { read: () => T; unmount: () => void; renders: () => number } {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  let renders = 0;
  let value: T;
  const Probe: React.FC = () => {
    renders += 1;
    value = useHook();
    return null;
  };
  act(() => {
    root.render(<Probe />);
  });
  return {
    read: () => value,
    renders: () => renders,
    unmount: () => {
      act(() => root.unmount());
      host.remove();
    },
  };
}

describe('走时刷新粒度', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-17T14:30:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('useTieredTick(60) 一分钟只更新一次，秒级变化不打扰', () => {
    const h = mountHook(() => useTieredTick(60));
    const before = h.read();
    const rendersBefore = h.renders();

    // 走 59 秒：值不变，也不该多渲染
    act(() => {
      for (let i = 0; i < 59; i++) {
        vi.advanceTimersByTime(1000);
      }
    });
    expect(h.read()).toBe(before);
    expect(h.renders()).toBe(rendersBefore);

    // 跨过整分钟：更新一次
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(h.read()).toBe(before + 60);
    h.unmount();
  });

  it('useSecondTick 每秒更新（展开态才用）', () => {
    const h = mountHook(() => useSecondTick(true));
    const before = h.read();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(h.read()).toBe(before + 3);
    h.unmount();
  });

  it('useSecondTick(false) 不订阅：传 enabled=false 时连定时器都不该有', () => {
    const h = mountHook(() => useSecondTick(false));
    const before = h.read();
    const rendersBefore = h.renders();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    // 值不变、渲染次数不变
    expect(h.read()).toBe(before);
    expect(h.renders()).toBe(rendersBefore);
    h.unmount();
  });

  it('没有订阅者时不挂定时器（空转检查）', () => {
    // 直接订阅再立刻退订，期间不应堆积监听
    const calls: number[] = [];
    const off = subscribeSecond((s) => calls.push(s));
    off();
    const count = calls.length;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    // 退订后不再收到回调
    expect(calls.length).toBe(count);
  });

  it('页面切到后台时停表，回到前台补一次', () => {
    const h = mountHook(() => useSecondTick(true));
    const before = h.read();

    // 切后台
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    // 后台不推进（计时器已停 —— 即便系统时间往前走，也不该有回调驱动的更新）
    expect(h.read()).toBe(before);

    // 回前台：立刻补一次，时间追上
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(h.read()).toBeGreaterThan(before);
    h.unmount();
  });
});
