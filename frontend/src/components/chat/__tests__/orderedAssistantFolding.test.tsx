import { describe, expect, it, vi } from 'vitest';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';
import { OrderedAssistantContent } from '../OrderedAssistantContent';
import type { Message, ToolCall } from '../../../types';

// jsdom 下让 React act() 生效（与仓库其它组件测试一致）
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/**
 * 思考/工具折叠组的流式开合契约（问题 2）：
 * 流式期间 details 必须展开，流式结束后必须收起。
 *
 * 历史 bug：原实现用 open={isStreaming || undefined}，React 对受控属性
 * true→undefined 不会移除 DOM 上已有的 open 属性，details 一直展开。
 * 修复用 ref + layout effect 显式同步，这里回归该行为。
 */

// ToolGroup 内部 useToolLabels 会去拉工具目录（then 里 setState）。测试不关心标签，
// 用永不 resolve 的 promise 让它停在空表，避免挂载后异步 setState 触发 act() 警告。
vi.mock('@/services/toolConfigService', () => ({
  loadToolLabels: () => new Promise(() => {}),
}));

const reasoningMessage: Message = {
  id: 'm-reasoning',
  role: 'model',
  text: '',
  blocks: [{ kind: 'reasoning', text: '先想想怎么算' }],
};

const tool: ToolCall = { id: 'c1', name: 'read_file', status: 'success', result: 'done' };
const toolsMessage: Message = {
  id: 'm-tools',
  role: 'model',
  text: '',
  toolCalls: [tool, { ...tool, id: 'c2' }, { ...tool, id: 'c3' }],
  // 三个连续同名工具 → ToolGroup（折叠成一行）
  blocks: [
    { kind: 'tool', toolCallId: 'c1' },
    { kind: 'tool', toolCallId: 'c2' },
    { kind: 'tool', toolCallId: 'c3' },
  ],
};

describe('OrderedAssistantContent 流式结束后自动折叠', () => {
  let container: HTMLElement;
  let root: Root;

  function mount(message: Message, isStreaming: boolean) {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <OrderedAssistantContent
          message={message}
          counter={{ current: 0 }}
          searchQuery=""
          activeMatchId={null}
          isAdmin={false}
          isStreaming={isStreaming}
        />,
      );
    });
  }

  function rerender(message: Message, isStreaming: boolean) {
    act(() => {
      root.render(
        <OrderedAssistantContent
          message={message}
          counter={{ current: 0 }}
          searchQuery=""
          activeMatchId={null}
          isAdmin={false}
          isStreaming={isStreaming}
        />,
      );
    });
  }

  it('思考组：流式 true 展开，false 收起', () => {
    mount(reasoningMessage, true);
    const details = container.querySelector('details') as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(true);

    rerender(reasoningMessage, false);
    expect(details.open).toBe(false);
  });

  it('工具组：流式 true 展开，false 且无 pending 时收起', () => {
    mount(toolsMessage, true);
    const details = container.querySelector('details') as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(true);

    rerender(toolsMessage, false);
    expect(details.open).toBe(false);
  });

  it('思考组：流式结束后用户手动展开，后续重渲染不会被强制收起', () => {
    mount(reasoningMessage, true);
    rerender(reasoningMessage, false);

    const details = container.querySelector('details') as HTMLDetailsElement;
    expect(details.open).toBe(false);

    // 用户点开 summary
    act(() => {
      (details.querySelector('summary') as HTMLElement).click();
    });
    expect(details.open).toBe(true);

    // 思考段落增长等普通重渲染（isStreaming 仍为 false）不应覆盖用户意图
    rerender(
      { ...reasoningMessage, blocks: [{ kind: 'reasoning', text: '先想想怎么算' }, { kind: 'reasoning', text: '再验证一下' }] },
      false,
    );
    expect(details.open).toBe(true);
  });

  it('工具组：仍有 pending 工具时，即使流式结束也保持展开', () => {
    const pendingTools: Message = {
      ...toolsMessage,
      toolCalls: [tool, { ...tool, id: 'c2' }, { ...tool, id: 'c3', status: 'pending' }],
    };
    mount(pendingTools, true);
    rerender(pendingTools, false);
    const details = container.querySelector('details') as HTMLDetailsElement;
    expect(details.open).toBe(true);
  });
});
