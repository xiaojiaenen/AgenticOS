/**
 * 网站发布任务的状态容器。
 *
 * 与 exportStore 同构：发布发生在 WebsiteArtifactPanel，岛在 App 根，
 * 中间隔四层组件。这里只存「当前有没有发布在跑」这一个事实。
 */
import { create } from 'zustand';

import type { DeployStatus } from '@/services/websiteService';

export interface DeployJob {
  /** 站点标识（展开视图显示，也是 URL 的最后一段）。 */
  slug: string;
  status: DeployStatus;
}

interface SiteDeployState {
  job: DeployJob | null;
  begin: (slug: string, status: DeployStatus) => void;
  setStatus: (status: DeployStatus) => void;
  finish: () => void;
}

/** 终态：到了这些状态就不再占用岛（已上线/被拒/失败都该收掉）。 */
const TERMINAL: ReadonlySet<DeployStatus> = new Set<DeployStatus>([
  'deployed',
  'rejected',
  'cancelled',
]);

export const useSiteDeployStore = create<SiteDeployState>((set) => ({
  job: null,
  begin: (slug, status) => set({ job: { slug, status } }),
  setStatus: (status) =>
    set((s) => {
      if (!s.job) return s;
      // 上线成功 / 被拒 / 取消 → 让岛收起（成功会由 alert 提示一次）
      if (TERMINAL.has(status)) return { job: null };
      return { job: { ...s.job, status } };
    }),
  finish: () => set({ job: null }),
}));
