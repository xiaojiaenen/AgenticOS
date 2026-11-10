import { test, expect } from 'e2e';

/**
 * 产物版本条与历史版本弹窗。
 *
 * 回归背景：版本弹窗原先 absolute 挂在面板头部里，被头部 backdrop-blur 的
 * 包含块 + 面板根 overflow-hidden 遮挡 —— z-50 逃不出去，点历史版本条目
 * 实际点到的是下面的预览卡片，弹窗永远关不掉。修复后弹窗 portal 到 body。
 *
 * 断言策略：用版本按钮的 aria-expanded 断言弹窗开合 —— 点历史版本条目后
 * 弹窗必须真的关上。遮挡存在时 tap 落在遮挡物上，弹窗关不掉，expanded
 * 一直为 true。比"弹窗可见"更接近真实用户感受。
 * （不写两条 `/历史版本（\d+/` 正则断言：esbuild 对该字符序列重复出现存在
 * 解析怪癖，见本轮调试记录 —— aria-expanded 断言也更语义化。）
 *
 * 前置数据（backend 运行 scripts/seed_website_version_bar_e2e.py 写入本地库）：
 * 会话「E2E 版本条会话」（admin 名下，website 模式），带 v1/v2 两个网站版本。
 */

test.describe('artifact version bar', () => {
  test('version popup opens above the preview and switches versions', { session: 'admin' }, async ({ app, screen }) => {
    await app.open('/chat');
    await expect(screen.getByText('E2E 版本条会话')).toBeVisible({ timeout: 20_000 });
    await screen.getByText('E2E 版本条会话').tap();

    // 预览面板恢复后版本条出现（会话恢复走 /artifacts 回源，稍慢）
    const versionBtn = screen.getByRole('button', '查看历史版本');
    await expect(versionBtn).toBeVisible({ timeout: 20_000 });

    await versionBtn.tap();
    await expect(versionBtn).toHaveAttribute('aria-expanded', 'true', { timeout: 10_000 });
    // 弹窗条目可见（v1 是历史版本，非当前打开的 v2）
    await expect(screen.getByText('E2E v1')).toBeVisible({ timeout: 10_000 });

    // 点历史版本 v1：遮挡存在时这一下点不到弹窗，expanded 关不掉
    await screen.getByText('E2E v1').tap();
    await expect(versionBtn).toHaveAttribute('aria-expanded', 'false', { timeout: 10_000 });

    // 版本切换不得把面板渲染搞挂
    await expect(screen.getByText('组件渲染出错')).toHaveCount(0);
  });
});
