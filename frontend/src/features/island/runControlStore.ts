/**
 * 运行控制桥：让岛上的按钮能触发聊天页里的动作。
 *
 * 为什么需要它：岛挂在 `App` 根，而「停止生成」的实现在 `useChatStream`（Chat
 * 页面深处的 hook 里，持有 AbortController）。中间隔着 Router + 页面 + 若干层
 * 组件，为这一个按钮把回调一路 props 传下去不值得。
 *
 * 约定：这一层只存「怎么停止」，不存任何 UI 状态。Chat 页在挂载时注册实现、
 * 卸载时清空；岛只在实现非空时才渲染按钮（README 侧栏、登录页等没有聊天
 * 上下文的页面自然不显示）。
 */
import { create } from 'zustand';

interface RunControlState {
  /** 停止当前会话的生成；null 表示当前页面没有注册（不在聊天页）。 */
  stop: (() => void) | null;
  register: (stop: () => void) => void;
  clear: () => void;
}

export const useRunControlStore = create<RunControlState>((set) => ({
  stop: null,
  register: (stop) => set({ stop }),
  clear: () => set({ stop: null }),
}));
