import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

/**
 * 聊天页冒烟。
 *
 * 默认只验证外壳：输入框、发送/上传按钮、智能体商店。全部是精确断言，
 * 不调模型、不发消息、不产生任何 LLM 费用。
 *
 * 真跑一次对话的用例默认跳过 —— 它会真的调产品侧的大模型，消耗 token。
 * 要跑时显式打开：
 *   E2E_RUN_LLM=1 npx e2e run
 */

/** 跑真实对话的开关。不开就跳过，避免日常回归白烧 token。 */
const RUN_LLM = process.env.E2E_RUN_LLM === '1';

test.describe('chat', () => {
  test('composer renders', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/chat');

    await expect(screen.getByRole('textbox', '输入消息')).toBeVisible();
    await expect(screen.getByRole('button', '发送')).toBeVisible();
    await expect(screen.getByRole('button', '上传文件')).toBeVisible();
    await expect(screen.getByRole('button', '退出登录')).toBeVisible();
    await expect(screen.getByText('组件渲染出错')).toHaveCount(0);
  });

  test('agent store opens', { session: 'admin' }, async ({ app, screen, browser }) => {
    await app.open('/agents');
    await expect(browser).toHaveURL('/agents');
    await expect(screen.getByText('组件渲染出错')).toHaveCount(0);
  });

  test(
    'a message reaches the assistant',
    {
      tags: ['llm'],
      session: 'admin',
      skip: RUN_LLM ? false : '需要 E2E_RUN_LLM=1：会真实调用大模型并消耗 token',
    },
    async ({ app, screen }) => {
      await app.open('/chat');
      await screen.getByRole('textbox', '输入消息').fill('用一句话介绍你自己');
      await screen.getByRole('button', '发送').tap();

      // 消息气泡没有 ARIA role，用「· N 字」这个稳定文案判断回复已渲染完成
      await expect(screen.getByText(/· \d+ 字/)).toBeVisible({ timeout: 90_000 });
      // 侧栏会话标题也会命中同一段文字，取最后一个（消息区在 DOM 末尾）
      await expect(screen.getByText('用一句话介绍你自己').last()).toBeVisible();
    },
  );
});
