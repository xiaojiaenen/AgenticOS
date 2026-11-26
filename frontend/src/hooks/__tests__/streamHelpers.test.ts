/**
 * 流式悬挂状态清理的纯函数回归（issues 2 / 3 / 4）。
 *
 * 历史故障：
 * - pendingDecisions 在流结束 / 出错 / 停止后不清空，留下死卡片，点击静默失败；
 * - 上一轮流 finally 用裸 ID 比较清 loading，误伤同会话新开的流。
 *
 * pruneDecisionsForSession 是 useChatStream 提取的纯 helper，锁住「按会话清理，
 * 不误伤其它并行会话 / 新流」的语义。
 */
import { describe, expect, it } from 'vitest';
import { pruneDecisionsForSession } from '../useChatStream';

type D = { decision_id: string; session_id?: string };

describe('pruneDecisionsForSession', () => {
  it('清掉指定会话的决策卡片', () => {
    const decisions: D[] = [
      { decision_id: 'd1', session_id: 's1' },
      { decision_id: 'd2', session_id: 's2' },
    ];
    expect(pruneDecisionsForSession(decisions, 's1')).toEqual([
      { decision_id: 'd2', session_id: 's2' },
    ]);
  });

  it('不动其它并行会话的决策', () => {
    const decisions: D[] = [
      { decision_id: 'd1', session_id: 's1' },
      { decision_id: 'd2', session_id: 's2' },
    ];
    expect(pruneDecisionsForSession(decisions, 's3')).toBe(decisions); // 引用不变
  });

  it('无 session_id 的旧决策保留（无法归属，不冒险清理）', () => {
    const decisions: D[] = [{ decision_id: 'legacy' }];
    expect(pruneDecisionsForSession(decisions, 's1')).toBe(decisions);
  });

  it('空 targetId 时原样返回', () => {
    const decisions: D[] = [{ decision_id: 'd1', session_id: 's1' }];
    expect(pruneDecisionsForSession(decisions, null)).toBe(decisions);
  });
});
