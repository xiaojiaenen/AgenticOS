/**
 * 用**线上真实会话数据**验证 mapper 的空泡合并与工具名归一。
 *
 * fixture 来自 192.168.159.11 的会话 1794556944894-y3dle1（56 条原始消息）：
 * 用户报「模型服务请求过于频繁 → 生成中消息都没了 → 刷新后出现这么多空气泡」，
 * 那份数据里正好有 15 条「无正文 + 有 tool_calls + 有 reasoning」的 assistant。
 *
 * 两个真实缺陷：
 * 1. 后端落库的 tool_calls 是 OpenAI 嵌套格式 `{function:{name,arguments}}`，
 *    mapper 只读 `tc.name` → 工具名全 undefined，工具块渲染成空白行。
 * 2. 「有思考就保留」的旧规则让十几条纯空壳各占一个气泡 → 整屏空气泡。
 */
import { describe, expect, it } from 'vitest';
import { mapBackendMessages, normalizeToolCall } from '../backendMessageMapper';
import fixture from './fixtures/session_dump.json';

const raw = fixture as unknown as Parameters<typeof mapBackendMessages>[0];

describe('normalizeToolCall', () => {
  it('解析 OpenAI 嵌套格式（后端落库的真实形态）', () => {
    const out = normalizeToolCall(
      {
        id: 'call_1',
        type: 'function',
        function: { name: 'check_svg_quality', arguments: {} },
      } as never,
      0,
    );
    expect(out.name).toBe('check_svg_quality');
    expect(out.id).toBe('call_1');
    expect(out.arguments).toEqual({});
  });

  it('兼容扁平格式', () => {
    const out = normalizeToolCall({ id: 'c2', name: 'calc', arguments: { a: 1 } } as never, 0);
    expect(out.name).toBe('calc');
    expect(out.arguments).toEqual({ a: 1 });
  });

  it('arguments 是 JSON 字符串时解析', () => {
    const out = normalizeToolCall(
      { id: 'c3', function: { name: 'x', arguments: '{"k":1}' } } as never,
      0,
    );
    expect(out.arguments).toEqual({ k: 1 });
  });

  it('坏 JSON 不抛错（退化为无参数）', () => {
    const out = normalizeToolCall({ id: 'c4', function: { name: 'x', arguments: '{bad' } } as never, 0);
    expect(out.arguments).toBeUndefined();
    expect(out.name).toBe('x');
  });

  it('两种格式都缺 name 时给占位名，不产出空白行', () => {
    const out = normalizeToolCall({ id: 'c5' } as never, 2);
    expect(out.name).toBe('tool_3');
  });
});

describe('真实会话数据（线上 fixture）', () => {
  const messages = mapBackendMessages(raw);

  it('不产生空泡（无正文/工具/思考的 model 气泡）', () => {
    const empty = messages.filter(
      (m) => m.role === 'model' && !m.text && !m.toolCalls?.length && !m.reasoningText,
    );
    expect(empty).toHaveLength(0);
  });

  it('连续空壳 assistant 合并：气泡数远少于原始 assistant 条数', () => {
    const assistantRows = raw.filter((m) => m.role === 'assistant').length;
    const modelBubbles = messages.filter((m) => m.role === 'model').length;
    expect(assistantRows).toBeGreaterThan(10);
    expect(modelBubbles).toBeLessThanOrEqual(3);
  });

  it('工具名全部解析出来，没有 undefined / 占位名', () => {
    const names = messages.flatMap((m) => m.toolCalls ?? []).map((t) => t.name);
    expect(names.length).toBeGreaterThan(10);
    expect(names.filter((n) => !n || /^tool_\d+$/.test(n))).toHaveLength(0);
  });

  it('工具链完整保留（合并后 toolCalls 总数不丢）', () => {
    const rawToolCount = raw.reduce((n, m) => n + (m.tool_calls?.length ?? 0), 0);
    const mappedToolCount = messages.flatMap((m) => m.toolCalls ?? []).length;
    expect(mappedToolCount).toBe(rawToolCount);
  });

  it('blocks 里 tool 块与 toolCalls 一一对应（渲染不丢行）', () => {
    messages
      .filter((m) => m.toolCalls?.length)
      .forEach((m) => {
        const toolBlocks = (m.blocks ?? []).filter((b) => b.kind === 'tool');
        expect(toolBlocks).toHaveLength(m.toolCalls!.length);
      });
  });

  it('用户消息与最终回答都在', () => {
    expect(messages.some((m) => m.role === 'user')).toBe(true);
    expect(messages.some((m) => m.role === 'model' && m.text.length > 50)).toBe(true);
  });
});
