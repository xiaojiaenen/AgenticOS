/**
 * 流收尾原因判定回归（issue 9）。
 *
 * 历史故障：`!state.finishReason && (signal.aborted || state.text)` 把三种来源
 * 混为一谈 —— (a) 有正文但无 done 的 SSE error 被误判成 interrupted，错误
 * 事件穿透成「成功」；(b) 用户点停止与网络断开无法区分。
 *
 * resolveFinishReason 是 stream.ts 提取的纯函数，这里直接喂来源组合。
 */
import { describe, expect, it } from 'vitest';
import { resolveFinishReason } from '../agent/stream';

type State = Parameters<typeof resolveFinishReason>[0];

describe('resolveFinishReason：三种来源 distinctly', () => {
  it('已有 done 的 finishReason 原样保留', () => {
    expect(resolveFinishReason({ finishReason: 'length', text: 'hi' } as State, true, true)).toBe('length');
  });

  it('收到 error 事件 → error，即便已有正文（不能误判 interrupted）', () => {
    expect(
      resolveFinishReason({ finishReason: null, text: '半截正文' } as State, false, true),
    ).toBe('error');
  });

  it('state 上的 errorEventReceived 标记同样生效', () => {
    expect(
      resolveFinishReason(
        { finishReason: null, text: '半截正文', errorEventReceived: true } as State,
        false,
        false,
      ),
    ).toBe('error');
  });

  it('用户主动中断（signal.aborted）→ interrupted', () => {
    expect(resolveFinishReason({ finishReason: null, text: '' } as State, true, false)).toBe('interrupted');
  });

  it('error 优先于 signal.aborted', () => {
    expect(resolveFinishReason({ finishReason: null, text: 'hi' } as State, true, true)).toBe('error');
  });

  it('静默断开、已有正文、无 signal、无 error → interrupted（保留已生成内容）', () => {
    expect(resolveFinishReason({ finishReason: null, text: '半截正文' } as State, false, false)).toBe('interrupted');
  });

  it('完全空流、无 done → error', () => {
    expect(resolveFinishReason({ finishReason: null, text: '' } as State, false, false)).toBe('error');
  });
});
