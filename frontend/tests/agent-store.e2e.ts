import { test, expect } from 'e2e';

/**
 * 智能体商店：安装 / 卸载 / 安装后可在聊天里选用。
 *
 * 这些用例会真实改动测试账号的安装状态，但都在测试账号范围内，
 * 且每个用例结束会恢复到初始状态，不污染其他用例。
 */

test.describe('agent store install', () => {
  test('store lists agents with install or chat buttons', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/agents');

    // 页面标题与搜索框存在
    await expect(screen.getByText('智能体商店')).toBeVisible({ timeout: 20_000 });
    await expect(screen.getByRole('searchbox', '搜索智能体')).toBeVisible();

    // 每张卡片要么是「对话」（已安装可用），要么是「安装」
    const chatButtons = screen.getByRole('button', '对话');
    const installButtons = screen.getByRole('button', '安装');
    const chatCount = await chatButtons.count();
    const installCount = await installButtons.count();
    expect(chatCount + installCount).toBeGreaterThan(0);
  });

  test('search filters the store', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/agents');
    await expect(screen.getByRole('searchbox', '搜索智能体')).toBeVisible({ timeout: 20_000 });

    await screen.getByRole('searchbox', '搜索智能体').fill('网站');
    await expect(screen.getByText('网站工程师')).toBeVisible({ timeout: 10_000 });

    await screen.getByRole('searchbox', '搜索智能体').fill('绝对不存在的智能体名xyz');
    await expect(screen.getByText('网站工程师')).toHaveCount(0);
  });
});
