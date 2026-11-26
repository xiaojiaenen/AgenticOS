/**
 * 搜索匹配指纹回归（issue 8）。
 *
 * 历史故障：useChatSearch 的匹配 effect 依赖 [searchQuery, currentSession?.id]，
 * 流式新增 token 时 session.id 不变 —— 搜索结果停留在流开始前的快照，新增
 * 内容搜不到。messageFingerprint 随时间文本变化，保证重算。
 */
import { describe, expect, it } from 'vitest';
import { messageFingerprint } from '../useChatSearch';

describe('messageFingerprint', () => {
  it('末条消息文本增长 → 指纹变化（流式新增内容触发重算）', () => {
    const before = messageFingerprint([
      { id: 'm1', text: '你好' },
      { id: 'm2', text: '正在回' },
    ] as never);
    const after = messageFingerprint([
      { id: 'm1', text: '你好' },
      { id: 'm2', text: '正在回复你' },
    ] as never);
    expect(after).not.toBe(before);
  });

  it('消息条数变化 → 指纹变化', () => {
    const before = messageFingerprint([{ text: 'hello' }]);
    const after = messageFingerprint([{ text: 'hello' }, { text: 'world' }]);
    expect(after).not.toBe(before);
  });

  it('文本不变、无关字段变化 → 指纹不变（不因每帧 setSessions 反复重算）', () => {
    const before = messageFingerprint([{ text: 'hello' }]);
    const after = messageFingerprint([{ text: 'hello', toolCalls: [] } as never]);
    expect(after).toBe(before);
  });

  it('空消息列表 / undefined 安全', () => {
    expect(messageFingerprint(undefined)).toBe('0:0:');
    expect(messageFingerprint([])).toBe('0:0:');
  });
});
