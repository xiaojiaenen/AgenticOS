/**
 * 回归：点「停止」之后气泡不能是空的。
 *
 * 5.5 的第三种形态。agent 是多轮工具循环，停止发生在循环中间时，最后一条
 * assistant 往往只有过渡 content（'\n\n'）或干脆为空、只剩 tool_calls。
 * 工具链折叠后气泡里一个字都没有 —— 用户看到「停完之后一片空白」。
 *
 * 这里锁住 markStoppedTurn 的两条职责：
 * 1. 悬挂的审批请求要被标记为已拒绝（否则审批面板一直挂着，点了没反应）；
 * 2. 本轮最后一条模型消息若完全无内容，补「（已停止）」占位；
 *    但有思考 / 产物 / 文字的气泡不许覆盖。
 */
import { describe, expect, it } from 'vitest';
import { markStoppedTurn } from '../useChatStream';
import type { Message } from '../../types';

function model(overrides: Partial<Message> = {}): Message {
  return { id: 'm1', role: 'model', text: '', ...overrides } as Message;
}

function user(text: string): Message {
  return { id: 'u1', role: 'user', text } as Message;
}

describe('markStoppedTurn', () => {
  it('空模型气泡补「（已停止）」', () => {
    const out = markStoppedTurn([user('构建网站'), model({ text: '\n\n' })]);
    expect(out[1].text).toBe('（已停止）');
  });

  it('只有 tool_calls 的过渡气泡也补占位', () => {
    const out = markStoppedTurn([
      user('跑个任务'),
      model({
        text: '',
        toolCalls: [{ id: 'tc1', name: 'build_website', status: 'success' }],
      }),
    ]);
    expect(out[1].text).toBe('（已停止）');
    // 工具信息本身不能被抹掉
    expect(out[1].toolCalls).toHaveLength(1);
  });

  it('有思考内容的气泡不覆盖（思考就是可见内容）', () => {
    const out = markStoppedTurn([
      user('想想'),
      model({ text: '', reasoningText: '先分析一下…' }),
    ]);
    expect(out[1].text).toBe('');
    expect(out[1].reasoningText).toBe('先分析一下…');
  });

  it('有可见文本的气泡不覆盖', () => {
    const out = markStoppedTurn([user('hi'), model({ text: '部分回答' })]);
    expect(out[1].text).toBe('部分回答');
  });

  it('有产物（A2UI / 图表）的气泡不覆盖', () => {
    const a2ui = markStoppedTurn([
      user('出个表单'),
      model({ text: '', a2uiMessages: [{ surfaceId: 's1' }] as never }),
    ]);
    expect(a2ui[1].text).toBe('');

    const chart = markStoppedTurn([
      user('画个图'),
      model({ text: '', chartMessages: [{ option: {} }] as never }),
    ]);
    expect(chart[1].text).toBe('');
  });

  it('悬挂审批被标记为已拒绝，并带上停止说明', () => {
    const out = markStoppedTurn([
      user('删个文件'),
      model({
        text: '准备删除',
        toolCalls: [{ id: 'tc1', name: 'file', status: 'approval_required', approvalId: 'a1' }],
      }),
    ]);
    expect(out[1].toolCalls?.[0].status).toBe('rejected');
    expect(out[1].toolCalls?.[0].result).toContain('停止');
  });

  it('本轮没有任何模型消息时不动用户消息', () => {
    const out = markStoppedTurn([user('刚发出去就停了')]);
    expect(out).toHaveLength(1);
    expect(out[0].text).toBe('刚发出去就停了');
  });

  it('只看本轮最后一条模型消息，不碰上一轮', () => {
    const out = markStoppedTurn([
      user('第一轮'),
      model({ id: 'old', text: '第一轮的回答' }),
      user('第二轮'),
      model({ id: 'new', text: '' }),
    ]);
    expect(out[1].text).toBe('第一轮的回答');
    expect(out[3].text).toBe('（已停止）');
  });
});
