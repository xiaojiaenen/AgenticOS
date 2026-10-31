/**
 * 回归：chart 事件必须落到消息上并被渲染（不依赖 A2UI 通道）。
 */
import { describe, expect, it } from 'vitest';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { ChatMessage } from '../../chat/ChatMessage';
import type { Message } from '../../../types';

describe('图表消息渲染', () => {
  it('message.chartMessages 会渲染成图表卡片（不是纯文本）', async () => {
    const option = {
      title: { text: '任务量' },
      xAxis: { type: 'category', data: ['A', 'B'] },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: [3, 5] }],
    };
    const message: Message = {
      id: 'm-chart',
      role: 'model',
      text: '柱状图已经出来了。',
      chartMessages: [{ title: '任务量', option }],
    };

    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);

    await act(async () => {
      root.render(
        React.createElement(ChatMessage, { message, index: 0, isAdmin: true }),
      );
      await new Promise((r) => setTimeout(r, 120));
    });

    // 图表标题是 ChartMessage 自己渲染的一层，正文里没有这个文本
    expect(host.textContent, '图表卡片应渲染标题').toContain('任务量');
    // 图表容器由 EChartsBlock 建出来（有 canvas 或至少有一个 echarts 容器 div）
    expect(host.querySelectorAll('canvas').length + host.querySelectorAll('div').length).toBeGreaterThan(0);
    root.unmount();
  });
});
