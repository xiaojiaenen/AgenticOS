import { test } from '@e2e-dev/web';
import { expect, credentials } from 'e2e';

/**
 * 登录一次并保存会话，其余用例用 { session: 'admin' } 复用。
 * 单独跑某个用例时，setup 仍会被自动带上。
 */
test.setup('authenticate as admin', { sessions: ['admin'] }, async ({ app, screen, session, browser }) => {
  const admin = credentials.user('admin');

  await app.open('/login');
  await screen.getByLabel('邮箱地址').fill(admin.username);
  await screen.getByLabel('密码').fill(admin.password);
  await screen.getByRole('button', '进入工作台').tap();

  // 管理员登录后会被重定向到 /admin —— 用它证明登录真的成功了再存会话
  await expect(browser).toHaveURL('/admin');
  await session.save('admin');
});
