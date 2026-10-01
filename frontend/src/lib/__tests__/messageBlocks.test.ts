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

describe('syncTextBlocks', () => {
  it('首次文本开新块', () => {
    const blocks = syncTextBlocks([], '你好', '');
    expect(blocks).toEqual([{ kind: 'text', text: '你好' }]);
  });

  it('续写同一块（累计全文以旧文本结尾）', () => {
    let blocks = syncTextBlocks([], '你', '');
    blocks = syncTextBlocks(blocks, '你好', '你');
    expect(blocks).toEqual([{ kind: 'text', text: '你好' }]);
  });

  it('中间夹了工具块后开新块', () => {
    let blocks = syncTextBlocks([], '先做这个', '');
    blocks = syncToolBlocks(blocks, [call('t1')], []);
    blocks = syncTextBlocks(blocks, '先做这个然后做那个', '先做这个');
    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toEqual({ kind: 'text', text: '先做这个' });
    expect(blocks[1]).toEqual({ kind: 'tool', toolCallId: 't1' });
    expect(blocks[2]).toEqual({ kind: 'text', text: '先做这个然后做那个' });
  });

  it('空文本不改变块', () => {
    const blocks = syncTextBlocks([], 'a', '');
    expect(syncTextBlocks(blocks, '', 'a')).toBe(blocks);
  });

  it('不修改入参数组（不可变）', () => {
    const blocks = syncTextBlocks([], 'a', '');
    syncTextBlocks(blocks, 'ab', 'a');
    expect(blocks).toHaveLength(1);
  });
});

describe('syncReasoningBlocks', () => {
  it('思考续写同一块', () => {
    let blocks = syncReasoningBlocks([], '想', '');
    blocks = syncReasoningBlocks(blocks, '想一下', '想');
    expect(blocks).toEqual([{ kind: 'reasoning', text: '想一下' }]);
  });

  it('工具块后的思考开新块', () => {
    let blocks = syncToolBlocks([], [call('t1')], []);
    blocks = syncReasoningBlocks(blocks, '先想', '');
    blocks = syncTextBlocks(blocks, '正文', '');
    blocks = syncReasoningBlocks(blocks, '先想再想', '先想');
    expect(blocks.map((b) => b.kind)).toEqual(['tool', 'reasoning', 'text', 'reasoning']);
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
    blocks = syncTextBlocks(blocks, '正文', '');
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