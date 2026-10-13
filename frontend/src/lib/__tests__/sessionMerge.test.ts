import { describe, it, expect } from 'vitest';
import {
  MAX_SESSIONS,
  convertBackendSession,
  mergeLocalIntoConverted,
  reconcileBackendWithLocal,
} from '../sessionMerge';
import type { Session } from '../../types';

function makeSession(partial: Partial<Session> & { id: string }): Session {
  return {
    title: partial.id,
    messages: [],
    updatedAt: 1_700_000_000_000,
    ...partial,
  };
}

describe('convertBackendSession', () => {
  it('正常转换：summary 作为标题，metadata 解析 mode 与 agentProfileId', () => {
    const session = convertBackendSession({
      session_id: 's1',
      summary: '季度汇报',
      metadata: {
        response_mode: 'ppt',
        agent_profile_id: 42,
      },
      message_count: 5,
      created_at: '2024-01-15T08:30:00',
      updated_at: '2024-01-15T09:00:00.123',
    });

    expect(session).toMatchObject({
      id: 's1',
      title: '季度汇报',
      messages: [],
      summary: '季度汇报',
      messageCount: 5,
      mode: 'ppt',
      agentProfileId: 42,
    });
    // 无时区的时间串按 +08:00 解析（2024-01-15T08:30:00+08:00）
    expect(session.createdAt).toBe(new Date('2024-01-15T08:30:00+08:00').getTime());
    expect(session.updatedAt).toBe(new Date('2024-01-15T09:00:00.123+08:00').getTime());
  });

  it('标题优先用后端 title（首条用户消息摘录），不再回退成智能体名', () => {
    // 回归用例：曾经用 summary（实际是上下文压缩摘要，正常为空）当标题，
    // 回退到 metadata.agent_profile_name → 刷新后列表全变成"通用助手"
    const fromTitle = convertBackendSession({
      session_id: 's2',
      summary: null,
      title: '帮我分析上周的转化率',
      metadata: { agent_profile_name: '数据分析师' },
      message_count: 2,
    });
    expect(fromTitle.title).toBe('帮我分析上周的转化率');

    // 后端尚未生成 title（如刚创建未落库）→ 新对话，不使用智能体名
    const byProfileName = convertBackendSession({
      session_id: 's3',
      summary: null,
      metadata: { agent_profile_name: '数据分析师' },
      message_count: 0,
    });
    expect(byProfileName.title).toBe('新对话');
    expect(byProfileName.mode).toBeUndefined();
    expect(byProfileName.agentProfileId).toBeUndefined();
  });

  it('缺失时间戳时回退到当前时间', () => {
    const before = Date.now();
    const session = convertBackendSession({ session_id: 's4', message_count: 0 });
    const after = Date.now();
    expect(session.createdAt).toBeGreaterThanOrEqual(before);
    expect(session.createdAt).toBeLessThanOrEqual(after);
    expect(session.updatedAt).toBe(session.createdAt);
  });
});

describe('mergeLocalIntoConverted', () => {
  it('keepMessagesOnly：保留本地消息，但标题以后端为准', () => {
    const converted = [
      makeSession({ id: 'a', title: '后端标题' }),
      makeSession({ id: 'b', title: '后端标题B' }),
    ];
    const local = [
      makeSession({ id: 'a', title: '本地标题', messages: [{ id: 'm1', role: 'user', text: 'hi' }] }),
      makeSession({ id: 'b', title: '本地空会话' }),
    ];

    const merged = mergeLocalIntoConverted(converted, local, { keepMessagesOnly: true });
    // 后端已有真实标题 → 覆盖本地旧标题（避免错误标题粘住）
    expect(merged[0]).toMatchObject({ id: 'a', title: '后端标题' });
    expect(merged[0].messages).toHaveLength(1);
    // 本地空会话（无消息）→ 保留后端结果
    expect(merged[1]).toMatchObject({ id: 'b', title: '后端标题B' });
    expect(merged[1].messages).toHaveLength(0);
  });

  it('默认语义（loadFromBackend prev 合并）：本地存在即覆盖元信息，消息仅在非空时保留', () => {
    const converted = [makeSession({ id: 'a', title: '后端标题', agentProfileId: 7 })];
    const prev = [makeSession({ id: 'a', title: '', agentProfileId: null })];

    const merged = mergeLocalIntoConverted(converted, prev);
    // 本地 title 为空 → 保留后端标题；agentProfileId 为 null → 保留后端值
    expect(merged[0].title).toBe('后端标题');
    expect(merged[0].agentProfileId).toBe(7);

    // 后端没有真实标题（新对话）→ 本地命名兜底
    const converted2 = [makeSession({ id: 'x', title: '新对话' })];
    const prev2 = [makeSession({ id: 'x', title: '本地命名' })];
    expect(mergeLocalIntoConverted(converted2, prev2)[0].title).toBe('本地命名');
  });

  it('agentProfileId 空值合并：null/undefined 不覆盖后端值，有值时覆盖', () => {
    const converted = [makeSession({ id: 'a', agentProfileId: 9 })];
    expect(mergeLocalIntoConverted(converted, [makeSession({ id: 'a', agentProfileId: undefined })])[0].agentProfileId).toBe(9);
    expect(mergeLocalIntoConverted(converted, [makeSession({ id: 'a', agentProfileId: 3 })])[0].agentProfileId).toBe(3);
  });
});

describe('reconcileBackendWithLocal', () => {
  it('保留本地未同步（尚未到达后端）的会话并置于列表最前', () => {
    const converted = [makeSession({ id: 'b1' }), makeSession({ id: 'b2' })];
    const prev = [makeSession({ id: 'local-new' }), makeSession({ id: 'b1' }), makeSession({ id: 'older-local' })];

    const result = reconcileBackendWithLocal(converted, prev);
    const ids = result.map(s => s.id);
    // 未同步的本地会话前置（按 prev 倒序 unshift），后端会话保持相对顺序
    expect(ids).toEqual(['older-local', 'local-new', 'b1', 'b2']);
  });

  it('截断到 MAX_SESSIONS（24）', () => {
    expect(MAX_SESSIONS).toBe(24);
    const converted = Array.from({ length: 30 }, (_, i) => makeSession({ id: `s${i}` }));
    const result = reconcileBackendWithLocal(converted, []);
    expect(result).toHaveLength(MAX_SESSIONS);
    // 截断保留前面的（最新的）会话
    expect(result[0].id).toBe('s0');
    expect(result[MAX_SESSIONS - 1].id).toBe(`s${MAX_SESSIONS - 1}`);
  });

  it('本地未同步会话计入截断上限', () => {
    const converted = Array.from({ length: MAX_SESSIONS }, (_, i) => makeSession({ id: `s${i}` }));
    const prev = [makeSession({ id: 'pending' })];
    const result = reconcileBackendWithLocal(converted, prev);
    expect(result).toHaveLength(MAX_SESSIONS);
    expect(result[0].id).toBe('pending');
  });
});
