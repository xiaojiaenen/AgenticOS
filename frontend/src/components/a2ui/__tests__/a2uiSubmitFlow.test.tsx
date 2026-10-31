/**
 * 端到端（组件级）回归：A2UI 表单填写 + 点击提交 → 必须变成一条用户消息。
 *
 * 覆盖 MessagesList → ChatMessage → A2uiRenderer → lit Button → handleA2uiAction
 * 这一整条链路。任何一环断了，用户看到的就是「点提交没反应」。
 */
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { MessagesList } from '../../chat/MessagesList';
import type { Message } from '../../../types';

const SURFACE = 'form-e2e';
const CATALOG = 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';

/** 与 backend/app/services/a2ui/builder.form_page 完全一致的产出。 */
function formMessages() {
  return [
    { version: 'v0.9', createSurface: { surfaceId: SURFACE, catalogId: CATALOG, sendDataModel: true } },
    {
      version: 'v0.9',
      updateComponents: {
        surfaceId: SURFACE,
        components: [
          {
            id: 'root',
            component: 'Column',
            children: ['title', 'name-label', 'name', 'level-label', 'level', 'submit'],
          },
          { id: 'title', component: 'Text', text: '登记', variant: 'h2' },
          { id: 'name-label', component: 'Text', text: '姓名' },
          { id: 'name', component: 'TextField', label: '姓名', value: { path: '/name' } },
          { id: 'level-label', component: 'Text', text: '级别' },
          {
            id: 'level',
            component: 'ChoicePicker',
            options: [
              { label: '高', value: '高' },
              { label: '低', value: '低' },
            ],
            value: { path: '/level' },
          },
          { id: 'submit-label', component: 'Text', text: '提交' },
          { id: 'submit', component: 'Button', child: 'submit-label', action: { event: { name: 'submit_form' } } },
        ],
      },
    },
    { version: 'v0.9', updateDataModel: { surfaceId: SURFACE, value: { name: '', level: '高' } } },
  ];
}

describe('A2UI 表单提交链路', () => {
  it('点击提交按钮会转成一条用户消息（onSend 被调用）', async () => {
    const onSend = vi.fn();
    const assistantMessage: Message = {
      id: 'm1',
      role: 'model',
      text: '填一下登记表。',
      a2uiMessages: formMessages(),
    };

    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);

    await act(async () => {
      root.render(
        React.createElement(MessagesList, {
          currentSession: { messages: [assistantMessage] },
          isLoading: false,
          searchQuery: '',
          activeMatchId: null,
          onSend,
          onSuggestionClick: () => {},
          onOpenArtifact: () => {},
          messagesEndRef: { current: null },
        }),
      );
      await new Promise((r) => setTimeout(r, 100));
    });

    const btn = host.querySelector('a2ui-basic-button button') as HTMLButtonElement | null;
    expect(btn, 'A2UI 表单应渲染出提交按钮').toBeTruthy();
    expect(btn!.disabled, '按钮不该是禁用态').toBe(false);

    await act(async () => {
      btn!.click();
      await new Promise((r) => setTimeout(r, 60));
    });

    expect(onSend, '点击提交后必须发起一条用户消息').toHaveBeenCalledTimes(1);
    const sent = onSend.mock.calls[0][0] as string;
    expect(sent).toContain('submit_form');
    root.unmount();
  });
});
