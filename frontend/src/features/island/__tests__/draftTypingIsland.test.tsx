/**
 * 正在输入岛：草稿与运行态的优先级回归。
 *
 * 用户明确要求"输入框里正在写，岛上也要显示正在输入"。这条链路有三个
 * 容易回归的点：
 * 1. 草稿太短（1 个字）不该点亮 —— 否则一按键盘就闪
 * 2. AI 正在跑时必须让位给运行岛 —— 否则两个活动抢一个胶囊
 * 3. 剪贴板粘贴的空白不能算字数
 *
 * 用真实 store 驱动（zustand 的 getState/setState），不 mock 组件内部。
 */
import { describe, expect, it, beforeEach } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

import { Island, IslandProvider } from '@/lib/island';
import type { IslandClock } from '@/lib/island';
import { DraftTypingIsland } from '../DraftTypingIsland';
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
        <DraftTypingIsland />
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

/** 改草稿（走真实 store，模拟用户输入） */
const type = (text: string) => act(() => useChatStore.getState().setInputValue(text));

describe('正在输入岛', () => {
  beforeEach(() => {
    useChatStore.setState({
      inputValue: '',
      runStatus: { phase: 'idle', label: '已就绪' },
    });
  });

  it('草稿为空时岛保持 idle', () => {
    const env = mount(new ManualClock());
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('只打了 1 个字不点亮（避免一按键盘就闪）', () => {
    const env = mount(new ManualClock());
    type('测');
    act(() => env.clock.advance(200));
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('草稿 ≥2 字时显示「输入 N 字」', () => {
    const env = mount(new ManualClock());
    type('帮我写');
    act(() => env.clock.advance(200));
    expect(presentation(env.host)).toBe('compact');
    expect(compactText(env.host)).toBe('输入 3 字');
    env.unmount();
  });

  it('纯空白（粘贴的空格/换行）不算字数', () => {
    const env = mount(new ManualClock());
    type('   \n\t  ');
    act(() => env.clock.advance(200));
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('AI 运行中让位给运行岛（不显示输入态）', () => {
    const env = mount(new ManualClock());
    type('这是一段还没发出去的草稿');
    act(() => {
      useChatStore.setState({ runStatus: { phase: 'streaming', label: '生成回答中' } });
    });
    act(() => env.clock.advance(300));
    // 只有输入岛挂载，运行态时它自己 return null → 岛回到 idle
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });

  it('运行中用户继续打字也不抢胶囊（草稿保留但不点亮）', () => {
    const env = mount(new ManualClock());
    act(() => {
      useChatStore.setState({ runStatus: { phase: 'streaming', label: '生成回答中' } });
    });
    type('AI 在跑的时候我又打了一段');
    act(() => env.clock.advance(400));
    expect(presentation(env.host)).toBe('idle');
    // 草稿本身不能被清掉（这是用户的字）
    expect(useChatStore.getState().inputValue).toBe('AI 在跑的时候我又打了一段');
    env.unmount();
  });

  it('运行结束后草稿还在 → 输入态重新点亮', () => {
    const env = mount(new ManualClock());
    act(() => {
      useChatStore.setState({ runStatus: { phase: 'streaming', label: '生成回答中' } });
    });
    type('等它跑完');
    act(() => env.clock.advance(300));
    expect(presentation(env.host)).toBe('idle');
    act(() => {
      useChatStore.setState({ runStatus: { phase: 'idle', label: '已就绪' } });
    });
    act(() => env.clock.advance(400));
    expect(presentation(env.host)).toBe('compact');
    expect(compactText(env.host)).toBe('输入 4 字');
    env.unmount();
  });

  it('字数封顶 99（三位数会撑破 72px 槽位）', () => {
    const env = mount(new ManualClock());
    type('字'.repeat(120));
    act(() => env.clock.advance(200));
    expect(compactText(env.host)).toBe('输入 99 字');
    env.unmount();
  });
});
