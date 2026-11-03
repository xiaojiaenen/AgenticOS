import { test, expect } from 'e2e';

/**
 * 全部智能体（5 个内置）的选择器 UI 遍历。
 *
 * 不调模型：只验证每个智能体都能在 AgentSelector 里选中并成为当前项。
 * bigdata 模式没有独立内置 profile，其系统提示词挂在 general 通道。
 */

const AGENTS = [
  '通用助手',
  'PPT 设计师',
  '网站工程师',
  '办公助手',
  '邮箱助手',
];

test.describe('agent selector', () => {
  /**
   * 会话一旦开始对话，AgentSelector 会被 disabled（isModeLocked）——
   * 这是产品行为，不是 bug。所以每个用例先点「新的对话」开一个空会话，
   * 选择器才可交互。
   */
  const openFreshChat = async (app: any, screen: any) => {
    await app.open('/chat');
    await screen.getByRole('button', '新的对话').tap();
  };

  test('lists all builtin agents', { session: 'admin' }, async ({ app, screen }) => {
    await openFreshChat(app, screen);

    await screen.getByRole('combobox', /当前智能体|选择智能体/).tap();
    for (const name of AGENTS) {
      await expect(screen.getByRole('option', name)).toBeVisible({ timeout: 10_000 });
    }
  });

  for (const name of AGENTS) {
    test(`selects ${name}`, { session: 'admin' }, async ({ app, screen }) => {
      await openFreshChat(app, screen);

      await screen.getByRole('combobox', /当前智能体|选择智能体/).tap();
      await expect(screen.getByRole('option', name)).toBeVisible({ timeout: 10_000 });
      await screen.getByRole('option', name).tap();

      // 选中后触发按钮的可访问名变为「当前智能体：<名字>」
      await expect(screen.getByRole('combobox', `当前智能体：${name}`)).toBeVisible();
      // 该选项处于选中态
      await expect(screen.getByRole('option', name)).toHaveAttribute('aria-selected', 'true');
    });
  }
});
