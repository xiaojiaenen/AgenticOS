/**
 * EmailPreviewPanel 回归测试。
 *
 * 用户明确要求的两条：
 *  1. 预览里切换模板要「瞬间切换」—— 走纯函数预览端点，不经 AI 重写；
 *  2. 用户只能编辑内容，不能编辑 HTML 源码 —— 面板里没有源码输入框，
 *     预览区是只读的渲染结果。
 * 外加：确认发送要把「最终渲染结果 + 改过的内容」作为 modified_arguments 回传。
 *
 * 用 react-dom/client + act（与项目里其他组件测试一致），mock 掉
 * agentService 的两个 API 函数，避免真实网络。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';

vi.mock('../../../services/agentService', () => ({
  listEmailTemplates: vi.fn(async () => [
    { id: 'plain', label: '纯文本' },
    { id: 'swiss', label: '瑞士网格' },
    { id: 'bodoni', label: '报刊 Didone' },
    { id: 'notice', label: '系统通知' },
    { id: 'custom', label: '自定义' },
  ]),
  previewEmailTemplate: vi.fn(async (p: { template: string; body: string }) => ({
    html: p.template === 'plain' ? p.body : `<div data-theme="${p.template}">${p.body}</div>`,
    is_html: p.template !== 'plain',
    template: p.template,
    needs_ai: p.template === 'custom',
  })),
}));

import { EmailPreviewPanel, type EmailPreview } from '../EmailPreviewPanel';
import { previewEmailTemplate } from '../../../services/agentService';

const EMAIL: EmailPreview = {
  approval_id: 'appr-1',
  to: 'zhangsan@corp.com',
  subject: '关于例会的调整',
  body: '各位好，例会改到周四下午三点。\n\n有议题请会前发给我。',
  is_html: false,
};

let container: HTMLDivElement;
let root: Root;

// 让 React 18/19 的 act() 生效，消除 "not configured to support act" 警告
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  vi.clearAllMocks();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const flush = async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 350)); // 越过 260ms 防抖
  });
};

describe('EmailPreviewPanel', () => {
  it('切换模板时调用纯函数预览端点，且只调预览不触发 AI 重写', async () => {
    const onDecision = vi.fn();
    await act(async () => {
      root.render(<EmailPreviewPanel emails={[EMAIL]} onDecision={onDecision} />);
    });
    await flush();

    const select = container.querySelector('select[aria-label="选择邮件模板"]') as HTMLSelectElement;
    expect(select).toBeTruthy();

    const before = (previewEmailTemplate as ReturnType<typeof vi.fn>).mock.calls.length;
    await act(async () => {
      select.value = 'bodoni';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await flush();

    const calls = (previewEmailTemplate as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.length).toBeGreaterThan(before);
    const last = calls[calls.length - 1][0] as { template: string };
    expect(last.template).toBe('bodoni');
    // 预览区体现了新模板的渲染结果
    expect(container.innerHTML).toContain('data-theme="bodoni"');
  });

  it('不提供 HTML 源码编辑：只有内容字段，没有承载源码的 textarea', async () => {
    const onDecision = vi.fn();
    await act(async () => {
      root.render(<EmailPreviewPanel emails={[EMAIL]} onDecision={onDecision} />);
    });
    await flush();

    // 展开编辑
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      (b.textContent || '').includes('编辑内容')
    ) as HTMLButtonElement;
    expect(editBtn).toBeTruthy();
    await act(async () => { editBtn.click(); });

    const textareas = Array.from(container.querySelectorAll('textarea'));
    // 唯一的 textarea 是「正文（纯文本）」，不允许编辑 HTML 源码
    expect(textareas.length).toBe(1);
    const label = textareas[0].previousElementSibling?.textContent || '';
    expect(label).toContain('正文');
    expect(label).toContain('纯文本');
    // 预览区是只读 div，不是可编辑控件
    const preview = container.querySelector('[class*="只读"], .max-h-56') as HTMLElement;
    expect(preview).toBeTruthy();
    expect(preview.querySelector('textarea, input, [contenteditable="true"]')).toBeNull();
  });

  it('确认发送把渲染后的 HTML 与改过的内容作为 modified_arguments 回传', async () => {
    const onDecision = vi.fn();
    await act(async () => {
      root.render(<EmailPreviewPanel emails={[EMAIL]} onDecision={onDecision} />);
    });
    await flush();

    // 切到 swiss（渲染成 HTML）
    const select = container.querySelector('select[aria-label="选择邮件模板"]') as HTMLSelectElement;
    await act(async () => {
      select.value = 'swiss';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await flush();

    const approve = Array.from(container.querySelectorAll('button')).find((b) =>
      (b.textContent || '').includes('确认发送')
    ) as HTMLButtonElement;
    await act(async () => { approve.click(); });

    expect(onDecision).toHaveBeenCalledTimes(1);
    const [id, status, modified] = onDecision.mock.calls[0] as [
      string, string, Record<string, unknown> | undefined,
    ];
    expect(id).toBe('appr-1');
    expect(status).toBe('approved');
    expect(modified).toBeTruthy();
    expect(modified!.is_html).toBe(true);
    expect(String(modified!.body)).toContain('data-theme="swiss"');
    expect(modified!.subject).toBe('关于例会的调整');
    expect(modified!.to).toBe('zhangsan@corp.com');
  });
});
