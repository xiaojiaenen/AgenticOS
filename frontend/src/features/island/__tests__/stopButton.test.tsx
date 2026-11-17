/**
 * 运行岛「停止」按钮回归。
 *
 * 展开岛通常意味着用户正在盯着它看 —— 这时最想做的是停掉。但岛挂在 App 根，
 * 拿不到 `useChatStream` 里的 AbortController，所以通过 `runControlStore` 交接。
 *
 * 这里锁住两个语义：
 * 1. Chat 页没注册停止实现时，展开视图里**不能**有按钮（登录页/侧栏等场景）
 * 2. 注册之后按钮出现，点它能调到实现 —— 而且不会顺带触发岛的展开/收起
 *    （CaptionButton 内部 stopPropagation）
 */
import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

import { Island, IslandProvider } from '@/lib/island';
import type { IslandClock } from '@/lib/island';
import { useRunControlStore } from '../runControlStore';
import { useChatStore } from '@/stores/chatStore';
import { AgentRunIsland } from '../AgentRunIsland';

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
        <AgentRunIsland />
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

/** 长按展开（指针事件，jsdom 没有 PointerEvent 构造器，用 MouseEvent 带 pointerType）。 */
function longPress(host: HTMLElement) {
  const hit = host.querySelector('[data-islandcn-hit="pill"]') as HTMLElement;
  const ev = () => {
    const e = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0 });
    Object.defineProperty(e, 'pointerType', { value: 'mouse' });
    return e;
  };
  act(() => {
    hit.dispatchEvent(ev());
  });
}

const stopButton = (host: HTMLElement) =>
  host.querySelector('button[aria-label="停止本轮生成"]') as HTMLButtonElement | null;

describe('运行岛停止按钮', () => {
  beforeEach(() => {
    useRunControlStore.setState({ stop: null });
    useChatStore.setState({
      inputValue: '',
      currentSessionId: 's1',
      sessions: [
        { id: 's1', title: 't', messages: [], updatedAt: Date.now(), agentName: '通用助手' },
      ],
      runStatus: { phase: 'streaming', label: '生成回答中', step: 3, maxSteps: 10 },
    });
  });

  afterEach(() => {
    useRunControlStore.setState({ stop: null });
  });

  it('没注册停止实现时，展开视图里没有停止按钮', () => {
    const clock = new ManualClock();
    const env = mount(clock);
    expect(presentation(env.host)).toBe('compact');
    longPress(env.host);
    act(() => clock.advance(400));
    expect(presentation(env.host)).toBe('expanded');
    expect(stopButton(env.host)).toBeNull();
    env.unmount();
  });

  it('注册之后按钮出现，点击调到实现', () => {
    const stop = vi.fn();
    useRunControlStore.getState().register(stop);
    const clock = new ManualClock();
    const env = mount(clock);
    longPress(env.host);
    act(() => clock.advance(400));
    expect(presentation(env.host)).toBe('expanded');

    const btn = stopButton(env.host);
    expect(btn).not.toBeNull();
    expect(btn!.textContent).toBe('停止');

    act(() => {
      btn!.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    });
    expect(stop).toHaveBeenCalledTimes(1);
    env.unmount();
  });

  it('点停止不会把岛收起（CaptionButton 阻止冒泡）', () => {
    useRunControlStore.getState().register(vi.fn());
    const clock = new ManualClock();
    const env = mount(clock);
    longPress(env.host);
    act(() => clock.advance(400));
    expect(presentation(env.host)).toBe('expanded');

    act(() => {
      stopButton(env.host)!.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    });
    act(() => clock.advance(200));
    // 仍在展开 —— 停止是动作，不是收起手势
    expect(presentation(env.host)).toBe('expanded');
    env.unmount();
  });

  it('跑完（phase=done）时运行岛整体卸载，按钮随之消失', () => {
    useRunControlStore.getState().register(vi.fn());
    const clock = new ManualClock();
    const env = mount(clock);
    expect(presentation(env.host)).toBe('compact');

    act(() => {
      useChatStore.setState({ runStatus: { phase: 'done', label: '已完成' } });
    });
    act(() => clock.advance(500));
    // 运行岛不渲染 → 岛回到 idle（完成提示由 AgentRunDoneIsland 单独负责）
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });
});
