/**
 * 诊断测试：真实渲染 A2uiRenderer（含 lit Web Component），点提交按钮，
 * 验证 action 是否能冒泡到 onAction 回调。
 */
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { A2uiRenderer } from '../A2uiRenderer';

const SURFACE = 'form-diag';
const CATALOG = 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';

function formMessages() {
  return [
    { version: 'v0.9', createSurface: { surfaceId: SURFACE, catalogId: CATALOG, sendDataModel: true } },
    {
      version: 'v0.9',
      updateComponents: {
        surfaceId: SURFACE,
        components: [
          { id: 'root', component: 'Column', children: ['title', 'name', 'submit'] },
          { id: 'title', component: 'Text', text: '登记', variant: 'h2' },
          { id: 'name', component: 'TextField', label: '姓名', value: { path: '/name' } },
          { id: 'submit-label', component: 'Text', text: '提交' },
          { id: 'submit', component: 'Button', child: 'submit-label', action: { event: { name: 'submit_form' } } },
        ],
      },
    },
    { version: 'v0.9', updateDataModel: { surfaceId: SURFACE, value: { name: '' } } },
  ];
}

describe('A2uiRenderer click path', () => {
  it('点击提交按钮会触发 onAction', async () => {
    const onAction = vi.fn();
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);

    await act(async () => {
      root.render(React.createElement(A2uiRenderer, { messages: formMessages(), onAction }));
      await new Promise((r) => setTimeout(r, 80));
    });

    const btn = host.querySelector('a2ui-basic-button button') as HTMLButtonElement | null;
    expect(btn, '应渲染出按钮元素').toBeTruthy();

    await act(async () => {
      btn!.click();
      await new Promise((r) => setTimeout(r, 40));
    });

    expect(onAction).toHaveBeenCalled();
    expect(onAction.mock.calls[0][0]).toMatchObject({ name: 'submit_form', surfaceId: SURFACE });
    root.unmount();
  });
});
