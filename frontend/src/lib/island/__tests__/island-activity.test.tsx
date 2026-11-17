/**
 * 岛引擎集成回归：活动从注册到展开再到收场的完整链路。
 *
 * 为什么不用浏览器 e2e：引擎时钟是纯 rAF 驱动（clock.ts createFrameClock），
 * 而自动化浏览器面板里的标签页 rAF 会被冻结（窗口被遮挡时 0 帧），长按计时器
 * 永远不触发，动画链路推不动。这里注入手动时钟逐帧推进，把交互时序变成确定性
 * 的：idle → compact（活动注册）→ 长按展开 → 点外部收起 → 卸载回 idle。
 *
 * 渲染方式跟随本仓库既有约定（`react-dom/client` + `act`），不引入
 * @testing-library —— 项目里没有这个依赖。
 */
import { describe, expect, it } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

import { Island, IslandProvider } from '../index';
import type { IslandClock } from '../clock';
import { useActivity } from '@/components/islandcn/use-activity';

// act() 需要显式声明测试环境（仓库其他组件测试同款写法）
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/**
 * 手动时钟：测试里显式推进时间并派发帧。与 createFrameClock 的接口一致，
 * 但 advance() 会先触发到期计时器再广播一帧 —— 与真实 rAF 循环的顺序相同
 * （clock.ts loop(): runTimersUntil → emitFrame）。
 */
class ManualClock implements IslandClock {
  time = 0;
  private frameListeners = new Set<(now: number) => void>();
  private timers: { at: number; run: (due: number) => void }[] = [];

  now = () => this.time;

  onFrame = (fn: (now: number) => void) => {
    this.frameListeners.add(fn);
    return () => {
      this.frameListeners.delete(fn);
    };
  };

  at = (at: number, run: (due: number) => void) => {
    this.timers.push({ at, run });
    return () => {
      this.timers = this.timers.filter((t) => t.run !== run);
    };
  };

  /** 推进时间：先触发到期计时器，再广播一帧（顺序同真实帧循环）。 */
  advance(ms: number) {
    this.time += ms;
    const due = this.timers.filter((t) => t.at <= this.time).sort((a, b) => a.at - b.at);
    this.timers = this.timers.filter((t) => t.at > this.time);
    for (const timer of due) timer.run(timer.at);
    for (const listener of [...this.frameListeners]) listener(this.time);
  }
}

/** 探针活动：用 useActivity 注册一个带 compact/expanded 内容的活动。 */
const ProbeActivity: React.FC<{ stepText: string }> = ({ stepText }) => {
  useActivity(
    () => ({
      id: 'probe-run',
      label: '探针活动',
      compact: {
        leading: <span data-testid="probe-glyph">✎</span>,
        trailing: stepText ? <span data-testid="probe-step">{stepText}</span> : undefined,
      },
      expanded: {
        leading: <span data-testid="probe-verb">思考中</span>,
        bottom: <span data-testid="probe-progress">6/10</span>,
      },
    }),
    [stepText],
  );
  return null;
};

function mount(clock: ManualClock) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  act(() => {
    root.render(
      <IslandProvider clock={clock}>
        <ProbeActivity stepText="3/10" />
        <Island placement="viewport" />
      </IslandProvider>,
    );
  });
  return {
    host,
    clock,
    root,
    unmount: () => {
      act(() => root.unmount());
      host.remove();
    },
  };
}

const presentation = (host: HTMLElement) =>
  host.querySelector('[data-islandcn]')?.getAttribute('data-presentation');

/** 在胶囊命中区上按下（React 按 pointerdown/pointerup 事件名监听，jsdom 没有 PointerEvent 构造器，用 MouseEvent 代替 —— 事件类型名一致即可进入 React 委托）。 */
const pressPill = (host: HTMLElement, type: 'pointerdown' | 'pointerup') =>
  act(() => {
    const hit = host.querySelector('[data-islandcn-hit="pill"]') as HTMLElement;
    hit.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 0 }));
  });

describe('岛引擎活动链路', () => {
  it('活动注册后从 idle 进入 compact，内容可见', () => {
    const env = mount(new ManualClock());
    expect(presentation(env.host)).toBe('compact');
    expect(env.host.querySelector('[data-testid="probe-glyph"]')?.textContent).toBe('✎');
    expect(env.host.querySelector('[data-testid="probe-step"]')?.textContent).toBe('3/10');
    env.unmount();
  });

  it('长按展开：decide(0.1s) 之后、longPress(0.216s) 之后出现 expanded 层', () => {
    const clock = new ManualClock();
    const env = mount(clock);
    pressPill(env.host, 'pointerdown');
    // decide 之前松手是轻点，不该展开
    act(() => clock.advance(80));
    pressPill(env.host, 'pointerup');
    expect(presentation(env.host)).toBe('compact');
    // 重新按住超过 longPress
    pressPill(env.host, 'pointerdown');
    act(() => clock.advance(300));
    expect(presentation(env.host)).toBe('expanded');
    expect(env.host.querySelector('[data-testid="probe-verb"]')?.textContent).toBe('思考中');
    expect(env.host.querySelector('[data-testid="probe-progress"]')?.textContent).toBe('6/10');
    env.unmount();
  });

  it('展开态点外部（或 Escape）收起回 compact，活动仍在', () => {
    const clock = new ManualClock();
    const env = mount(clock);
    pressPill(env.host, 'pointerdown');
    act(() => clock.advance(300));
    expect(presentation(env.host)).toBe('expanded');
    // 点岛外
    act(() => {
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
    });
    act(() => clock.advance(100));
    expect(presentation(env.host)).toBe('compact');
    env.unmount();
  });

  it('活动卸载即结束：回到 idle 胶囊', () => {
    const clock = new ManualClock();
    const env = mount(clock);
    expect(presentation(env.host)).toBe('compact');
    act(() => {
      env.root.render(
        <IslandProvider clock={clock}>
          <Island placement="viewport" />
        </IslandProvider>,
      );
    });
    clock.advance(400);
    expect(presentation(env.host)).toBe('idle');
    env.unmount();
  });
});
