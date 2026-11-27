/**
 * ForesightJS PoC：预测用户下一步点击，提前预取路由/后台 chunk。
 *
 * 只做「何时预取」，预取什么由这里的映射决定；回调严格幂等（只有 import()），
 * 无副作用、不预取任何带鉴权的用户数据。触屏设备收益低，默认交给库的
 * onTouchStart 策略（接近点击时才触发）。
 */
import { ForesightManager } from '@foresightjs/react';

let initialized = false;

/** 在应用入口调用一次。预测时间保守设 80ms，降低误触发。 */
export function initForesight(): void {
  if (initialized) return;
  initialized = true;
  try {
    ForesightManager.initialize({
      trajectoryPredictionTime: 80,
      // 仅指针设备受益；触屏保持 onTouchStart（库默认），不主动改
    });
  } catch {
    // 初始化失败不影响应用（预取是纯增强）
  }
}

/** 路由 path → 对应的动态 import（与 App.tsx 的 lazy loader 指向同一 chunk，幂等）。 */
export const ROUTE_PREFETCH: Record<string, () => Promise<unknown>> = {
  '/': () => import('../pages/Home'),
  '/chat': () => import('../pages/Chat'),
  '/agents': () => import('../pages/AgentStore'),
  '/agents/new': () => import('../pages/AgentEditor'),
  '/gallery': () => import('../pages/Gallery'),
  '/admin': () => import('../pages/AdminDashboard'),
  '/canvas': () => import('../pages/CreativeCanvas'),
  '/feedback': () => import('../pages/Feedback'),
};

/** 预取回调：只 import chunk，失败静默（不影响用户实际点击）。 */
export function prefetchRoute(path: string): void {
  const loader = ROUTE_PREFETCH[path];
  if (!loader) return;
  void loader().catch(() => undefined);
}
