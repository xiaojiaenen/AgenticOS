import { describe, expect, it } from 'vitest';
import { createRoot, Root } from 'react-dom/client';
import { act } from 'react';
import { PendingApprovalPanel } from '../PendingApprovalPanel';
import type { ToolCall } from '../../../types';

/** 改参（edit 决策）通用 UI 契约（3G.1）：
 * 1. 参数为 JSON 时展示「改参数」入口，展开 JSON 编辑器；
 * 2. 编辑合法 JSON →「按新参数批准」出现，回调带改后参数；
 * 3. 非法 JSON → error 提示且按钮保持「批准」（原参数语义）；
 * 4. 非 JSON 参数的工具不展示改参入口；
 * 5. 代答回调与改参共用第 5 位 payload（status 二分语义）。 */

const baseApproval = (result: string): ToolCall => ({
  id: 'call-1',
  name: '计算',
  status: 'approval_required',
  approvalId: 'appr-1',
  result,
});

function findByLabel(root: HTMLElement, label: string): HTMLElement | null {
  return root.querySelector(`[aria-label="${label}"]`);
}

describe('PendingApprovalPanel 改参 UI', () => {
  let container: HTMLElement;
  let root: Root;

  function mount(
    approvals: ToolCall[],
    onDecision: (
      id: string,
      status: string,
      isApiApproval?: boolean,
      allowAll?: boolean,
      payload?: string,
    ) => void,
  ) {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<PendingApprovalPanel approvals={approvals} onDecision={onDecision} />);
    });
  }

  function type(ta: HTMLTextAreaElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value',
    )!.set!;
    act(() => {
      setter.call(ta, value);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  it('合法 JSON 编辑后按钮变「按新参数批准」且回调携带新参数', () => {
    const decisions: Array<{ id: string; status: string; payload?: string }> = [];
    mount(
      [baseApproval('{ "expression": "111 * 222" }')],
      (id, status, _api, _allow, payload) => {
        decisions.push({ id, status, payload });
      },
    );

    const editBtn = findByLabel(document.body, '修改工具参数')!;
    expect(editBtn).toBeTruthy();
    act(() => { editBtn.click(); });

    const editor = findByLabel(document.body, '工具参数 JSON') as HTMLTextAreaElement;
    expect(editor).toBeTruthy();
    expect(editor.value).toContain('111 * 222');

    type(editor, '{"expression": "333 * 444"}');

    const approve = findByLabel(document.body, '按修改后的参数批准')!;
    expect(approve).toBeTruthy();
    act(() => { approve.click(); });

    expect(decisions).toHaveLength(1);
    expect(decisions[0].status).toBe('approved');
    expect(JSON.parse(decisions[0].payload!)).toEqual({ expression: '333 * 444' });
  });

  it('非法 JSON 显示错误且按钮保持「批准」原语义', () => {
    const decisions: Array<{ id: string; status: string; payload?: string }> = [];
    mount(
      [baseApproval('{ "expression": "111 * 222" }')],
      (id, status, _api, _allow, payload) => {
        decisions.push({ id, status, payload });
      },
    );

    act(() => { findByLabel(document.body, '修改工具参数')!.click(); });
    const editor = findByLabel(document.body, '工具参数 JSON') as HTMLTextAreaElement;
    type(editor, '{broken json');

    expect(document.body.textContent).toContain('JSON 语法错误');
    act(() => { findByLabel(document.body, '批准工具调用')!.click(); });
    expect(decisions[0].payload).toBeUndefined();
  });

  it('非 JSON 参数不展示改参入口', () => {
    mount([baseApproval('等待你确认后继续执行。')], () => {});
    expect(findByLabel(document.body, '修改工具参数')).toBeNull();
  });

  it('代答回调 payload=response（status 二分共用第 5 位）', () => {
    const decisions: Array<{ id: string; status: string; payload?: string }> = [];
    mount(
      [baseApproval('任何文案')],
      (id, status, _api, _allow, payload) => {
        decisions.push({ id, status, payload });
      },
    );
    const input = findByLabel(document.body, '人工代答输入') as HTMLInputElement
      ?? (document.body.querySelector('input[placeholder*="代答"]') as HTMLInputElement);
    expect(input).toBeTruthy();
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )!.set!;
    act(() => {
      setter.call(input, '答案是 42');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    act(() => { findByLabel(document.body, '人工代答')!.click(); });
    expect(decisions[0]).toEqual({ id: 'appr-1', status: 'respond', payload: '答案是 42' });
  });
});
