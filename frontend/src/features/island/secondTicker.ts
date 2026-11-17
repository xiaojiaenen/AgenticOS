/**
 * 全局秒级时钟：所有需要「每秒刷新」的岛共用一个 interval。
 *
 * 为什么需要这个：`IdleClockIsland` 和 `PptExportIsland` 各自 `setInterval(1000)`
 * 触发 setState。每个岛一秒钟重新渲染一次本身不贵，但**岛引擎的帧循环是按需
 * 静止的** —— `surface.tsx` 在所有弹簧静止时会 `unsubscribe()` 掉 rAF；而每秒
 * 一次的 update 把它一直叫醒，于是空闲页面上 60fps 的 rAF 永不停歇，纯 CPU 空转
 * （实测这块是岛接入后唯一常驻的动画开销）。
 *
 * 共用 ticker 不能消除 update 本身，但能做到两件事：
 * 1. 同一秒内的多个订阅者只产生一次 React 更新批次
 * 2. 页面隐藏时直接停表 —— 后台标签不该有任何定时器在跑
 *
 * 真正的省电靠调用方：只在**秒数真的变了**时才 setState（见 `useSecondTick`）。
 */
import * as React from 'react';

type Listener = (second: number) => void;

const listeners = new Set<Listener>();

let timer: number | null = null;
/** 上一次广播出去的整秒（Unix 秒），用于去重。 */
let lastSecond = -1;

const stopTimer = () => {
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
};

const tick = () => {
  const second = Math.floor(Date.now() / 1000);
  if (second === lastSecond) return;
  lastSecond = second;
  // 复制一份再遍历：订阅者可能在回调里退订
  for (const listener of [...listeners]) listener(second);
};

const startTimer = () => {
  if (timer !== null) return;
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
  lastSecond = -1; // 恢复时立刻补一次，让时间显示追上
  timer = window.setInterval(tick, 1000);
  tick();
};

// 切到后台就停表：后台标签里的秒级刷新没有任何意义。
const onVisibility = () => {
  if (document.visibilityState === 'hidden') {
    stopTimer();
  } else if (listeners.size > 0) {
    startTimer();
  }
};

let visibilityBound = false;

/** 订阅整秒变化，返回退订函数。 */
export function subscribeSecond(listener: Listener): () => void {
  listeners.add(listener);
  if (!visibilityBound && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility);
    visibilityBound = true;
  }
  if (listeners.size === 1) startTimer();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      stopTimer();
      if (visibilityBound) {
        document.removeEventListener('visibilitychange', onVisibility);
        visibilityBound = false;
      }
    }
  };
}

/**
 * 当前整秒（Unix 秒），每秒变化一次。
 *
 * 只在**秒数变化**时才 setState —— 这是本 hook 的全部价值：`setInterval` 计时器
 * 自己就会漂移（回调可能 998ms 或 1003ms 到），若每次都 setState 就会产生
 * 额外的渲染；按整秒去重后，一秒内最多一次更新。
 */
export function useSecondTick(enabled = true): number {
  const [second, setSecond] = React.useState(() => Math.floor(Date.now() / 1000));
  React.useEffect(() => {
    if (!enabled) return;
    return subscribeSecond(setSecond);
  }, [enabled]);
  return second;
}

/**
 * 按「整 N 秒」粒度返回时间戳，用于**不需要秒级精度**的地方。
 *
 * 为什么单独一个 hook：`useSecondTick` 每秒都会 setState，即使调用方只显示
 * 到分钟 —— 那仍然是每秒一次重渲染，会把岛引擎按需静止的帧循环反复叫醒。
 * 这里在订阅回调里先按粒度向下取整，值不变就直接忽略，所以 `granularity`
 * 为 60 时组件一分钟才渲染一次。
 */
export function useTieredTick(granularity: number): number {
  const safe = Math.max(1, Math.floor(granularity));
  // 初值也按粒度取整，避免首帧与后续值不落在同一格（否则首帧后立刻多渲染一次）
  const [tick, setTick] = React.useState(() => Math.floor(Math.floor(Date.now() / 1000) / safe) * safe);
  React.useEffect(
    () =>
      subscribeSecond((second) => {
        const tiered = Math.floor(second / safe) * safe;
        setTick((prev) => (prev === tiered ? prev : tiered));
      }),
    [safe],
  );
  return tick;
}
