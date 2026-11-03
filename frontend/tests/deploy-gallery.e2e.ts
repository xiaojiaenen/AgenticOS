import { test, expect } from 'e2e';

/**
 * 部署审批与作品库 UI。
 *
 * 前置数据（种子脚本写入本地库）：
 * - 若干 deployed 状态的网站作品（公开 + 私密，均属 admin 账号）
 * - 全部走真实登录会话，不调模型。
 */

test.describe('gallery', () => {
  test('renders with cards and visibility badges', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/gallery');
    // Gallery 是 lazy chunk：先等懒加载完成再断言
    await expect(screen.getByText('作品库')).toBeVisible({ timeout: 20_000 });
    // 三个筛选页签
    await expect(screen.getByRole('button', /全部 \d+/)).toBeVisible();
    await expect(screen.getByRole('button', /公开 \d+/)).toBeVisible();
    await expect(screen.getByRole('button', /私密 \d+/)).toBeVisible();

    // 至少一张作品卡（种子数据保证）
    await expect(screen.getByText(/公开|私密/).first()).toBeVisible();
    // 公开作品的「打开」按钮
    await expect(screen.getByRole('link', '打开').first()).toBeVisible();
  });

  test('filter switches between visibility tabs', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/gallery');
    await expect(screen.getByText('作品库')).toBeVisible({ timeout: 20_000 });

    await screen.getByRole('button', /私密 \d+/).tap();
    // 切到私密后，卡片上的「公开」徽章应为 0
    await expect(screen.getByText('公开').first()).toHaveCount(0);
  });

  test('private card offers reset access button', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/gallery');
    // 种子数据里有私密作品 → 重置链接按钮存在
    await expect(
      screen.getByRole('button', '重置私密访问链接').first(),
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('deploy approval preview', () => {
  test('approval panel shows preview buttons', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/admin');
    // 展开分组后进入网站部署分区
    await screen.getByRole('button', /智能体与能力/).tap();
    await screen.getByRole('button', /网站部署/).tap();

    await expect(screen.getByText('部署审批')).toBeVisible();
    // 预览按钮在「全部记录」tab（默认的待审批 tab 可能为空）
    await screen.getByRole('tab', /全部记录/).tap();
    await expect(screen.getByRole('button', '预览').first()).toBeVisible({ timeout: 10_000 });
  });
});
