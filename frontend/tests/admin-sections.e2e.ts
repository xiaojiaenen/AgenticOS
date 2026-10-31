import { test, expect } from 'e2e';

/**
 * 管理后台全部分区的冒烟巡检。
 *
 * 整组不需要模型：每个分区点开一次，断言主区域确实渲染了该分区的标题，
 * 并且没有掉进错误兜底。全部通过 = 没有白屏、没有组件崩溃。
 *
 * 维护约定（2026-10-30 对齐当前 UI，此前两个用例失败就是断言过期）：
 *  1. `nav` 用以分区名开头的正则匹配侧栏按钮的无障碍名（= 分区名 + 描述）。
 *  2. `heading` 必须与各面板 AdminPageHeader 的 title 严格一致 ——
 *     改版侧栏分区或面板标题时，必须同步更新这份清单。
 *  3. 侧栏分组默认折叠，点子项前要先展开所属分组。
 */

type Section = {
  /** 侧栏显示的分区名 */
  nav: string;
  /** 该分区主区域 h2 的文案（AdminPageHeader title / 面板内 h2） */
  heading: string;
  /** 展开这个分组才能看到分区；null 表示该项始终可见 */
  group: string | null;
};

const SECTIONS: Section[] = [
  { nav: '系统总览', heading: '后台数据看板', group: null },
  { nav: '聊天记录', heading: '会话列表', group: '对话与内容' },
  { nav: '公告设计', heading: '用户公告设计台', group: '对话与内容' },
  { nav: '记忆管理', heading: '所有用户记忆', group: '对话与内容' },
  { nav: '智能体配置', heading: '智能体目录', group: '智能体与能力' },
  { nav: 'AI 提供商', heading: 'AI 提供商', group: '智能体与能力' },
  { nav: 'Skill 管理', heading: '本地 Skill 目录', group: '智能体与能力' },
  { nav: '知识库', heading: '知识库管理', group: '智能体与能力' },
  { nav: '网站部署', heading: '部署审批', group: '智能体与能力' },
  { nav: '用户管理', heading: '账号与权限', group: '组织与系统' },
  { nav: '权限管理', heading: '权限管理', group: '组织与系统' },
  { nav: '集成管理', heading: '第三方集成', group: '组织与系统' },
  { nav: 'API Key', heading: 'API Key', group: '组织与系统' },
  { nav: '对外接口', heading: '网关与接入', group: '组织与系统' },
  { nav: '系统设置', heading: 'LDAP 认证', group: '组织与系统' },
];

test.describe('admin sections', () => {
  for (const { nav, heading, group } of SECTIONS) {
    test(`${nav} renders`, { session: 'admin' }, async ({ app, screen }) => {
      await app.open('/admin');
      if (group) {
        await screen.getByRole('button', new RegExp(`^${group}`)).tap();
      }
      await screen.getByRole('button', new RegExp(`^${nav}`)).tap();

      await expect(screen.getByRole('heading', heading)).toBeVisible();
      // 组件崩溃时 ErrorBoundary 会渲染这个标题
      await expect(screen.getByText('组件渲染出错')).toHaveCount(0);
    });
  }
});
