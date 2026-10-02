import { describe, it, expect } from 'vitest';
import {
  syncTextBlocks,
  syncReasoningBlocks,
  syncToolBlocks,
  blocksFromLegacy,
  resolveBlocks,
  toolCallIdOf,
} from '../messageBlocks';
import type { MessageBlock, ToolCall } from '../../types';

const call = (id: string, name = 'time'): ToolCall => ({ id, name, status: 'success' });

describe('syncTextBlocks（增量语义）', () => {
  it('首次文本开新块，块内只存增量', () => {
    const blocks = syncTextBlocks([], '你好', 0);
    expect(blocks).toEqual([{ kind: 'text', text: '你好' }]);
  });

  it('同一块续写：只追加本次新增部分', () => {
    let blocks = syncTextBlocks([], '你', 0);
    blocks = syncTextBlocks(blocks, '你好', 1);
    expect(blocks).toEqual([{ kind: 'text', text: '你好' }]);
  });

  it('ReAct 多轮：每轮重发累计全文也不产生重复', () => {
    // 第 1 轮输出"先查时间"，第 2 轮工具后输出累计全文"先查时间现在是…"
    let blocks = syncTextBlocks([], '先查时间', 0);
    blocks = syncToolBlocks(blocks, [call('t1')], []);
    blocks = syncTextBlocks(blocks, '先查时间现在是九点', 4);
    const text = blocks
      .filter((b): b is Extract<typeof b, { kind: 'text' }> => b.kind === 'text')
      .map((b) => b.text)
      .join('');
    expect(text).toBe('先查时间现在是九点');
    expect(text).toBe('先查时间现在是九点'.slice(0, text.length)); // 不含重复前缀
  });

  it('工具块后开新文本块', () => {
    let blocks = syncTextBlocks([], '先做这个', 0);
    blocks = syncToolBlocks(blocks, [call('t1')], []);
    blocks = syncTextBlocks(blocks, '先做这个然后做那个', 4);
    expect(blocks.map((b) => b.kind)).toEqual(['text', 'tool', 'text']);
    expect(blocks[2]).toEqual({ kind: 'text', text: '然后做那个' });
  });

  it('空文本或无新增内容不改变块', () => {
    const blocks = syncTextBlocks([], 'a', 0);
    expect(syncTextBlocks(blocks, '', 1)).toBe(blocks);
    expect(syncTextBlocks(blocks, 'a', 1)).toBe(blocks); // 没有新增字符
  });

  it('不改入参数组（不可变）', () => {
    const blocks = syncTextBlocks([], 'a', 0);
    syncTextBlocks(blocks, 'ab', 1);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toEqual({ kind: 'text', text: 'a' });
  });
});

describe('syncReasoningBlocks（增量语义）', () => {
  it('思考续写同一块', () => {
    let blocks = syncReasoningBlocks([], '想', 0);
    blocks = syncReasoningBlocks(blocks, '想一下', 1);
    expect(blocks).toEqual([{ kind: 'reasoning', text: '想一下' }]);
  });

  it('工具块后的思考开新块且只存增量', () => {
    let blocks = syncToolBlocks([], [call('t1')], []);
    blocks = syncReasoningBlocks(blocks, '先想', 0);
    blocks = syncTextBlocks(blocks, '正文', 0);
    blocks = syncReasoningBlocks(blocks, '先想再想', 2);
    expect(blocks.map((b) => b.kind)).toEqual(['tool', 'reasoning', 'text', 'reasoning']);
    expect(blocks[3]).toEqual({ kind: 'reasoning', text: '再想' });
  });
});

describe('syncToolBlocks', () => {
  it('为新调用追加块', () => {
    const blocks = syncToolBlocks([], [call('t1'), call('t2')], []);
    expect(blocks).toEqual([
      { kind: 'tool', toolCallId: 't1' },
      { kind: 'tool', toolCallId: 't2' },
    ]);
  });

  it('已存在的调用保持原位不重复', () => {
    let blocks = syncToolBlocks([], [call('t1')], []);
    blocks = syncTextBlocks(blocks, '正文', 0);
    blocks = syncToolBlocks(blocks, [call('t1'), call('t2')], [call('t1')]);
    expect(blocks.map((b) => b.kind)).toEqual(['tool', 'text', 'tool']);
  });

  it('缺 id 时用 name#index 兜底', () => {
    const blocks = syncToolBlocks([], [{ name: 'calc', status: 'success' }], []);
    expect(blocks).toEqual([{ kind: 'tool', toolCallId: 'calc#0' }]);
    expect(toolCallIdOf({ name: 'calc', status: 'success' }, 0)).toBe('calc#0');
  });
});

describe('blocksFromLegacy', () => {
  it('旧式消息回退：思考 → 工具 → 正文', () => {
    const blocks = blocksFromLegacy({
      reasoningText: '思考中',
      toolCalls: [call('t1')],
      text: '答案',
    });
    expect(blocks.map((b) => b.kind)).toEqual(['reasoning', 'tool', 'text']);
  });

  it('只有正文时只回退一个文本块', () => {
    expect(blocksFromLegacy({ text: '答案' })).toEqual([{ kind: 'text', text: '答案' }]);
  });

  it('空消息回退为空数组', () => {
    expect(blocksFromLegacy({ text: '' })).toEqual([]);
  });
});

describe('resolveBlocks', () => {
  it('有 blocks 时直接使用', () => {
    const blocks: MessageBlock[] = [{ kind: 'text', text: 'a' }];
    expect(resolveBlocks({ blocks, text: 'a' })).toBe(blocks);
  });

  it('无 blocks 时回退三桶', () => {
    const resolved = resolveBlocks({ text: '答案', toolCalls: [call('t1')] });
    expect(resolved.map((b) => b.kind)).toEqual(['tool', 'text']);
  });

  it('blocks 为空数组时也回退', () => {
    const resolved = resolveBlocks({ blocks: [], text: '答案' });
    expect(resolved).toEqual([{ kind: 'text', text: '答案' }]);
  });
});