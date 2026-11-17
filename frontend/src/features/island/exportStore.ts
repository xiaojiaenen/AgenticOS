/**
 * 导出任务的小型状态容器（zustand）。
 *
 * 为什么需要一个 store 而不是 prop 传递：导出发生在 `PptArtifactPanel`
 * 深处，而岛挂在 `App` 根。中间隔着 Chat → ChatArtifactArea →
 * PptArtifactPanel 四层，为此改四个组件的 props 链不值得。
 *
 * 这个 store 只放「当前有没有导出在跑」这一个事实，不掺任何 UI 状态。
 */
import { create } from 'zustand';

export interface ExportJob {
  /** 正在导出的演示文稿标题（展开视图显示）。 */
  title: string;
  /** 开始时间戳（毫秒），岛据此自己算已用秒数。 */
  startedAt: number;
}

interface PptExportState {
  job: ExportJob | null;
  begin: (title: string) => void;
  finish: () => void;
}

export const usePptExportStore = create<PptExportState>((set) => ({
  job: null,
  begin: (title) => set({ job: { title, startedAt: Date.now() } }),
  finish: () => set({ job: null }),
}));
