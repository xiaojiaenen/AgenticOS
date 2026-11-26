/**
 * 会话列表 helper 回归（issues 5 / 11）。
 *
 * 历史故障：
 * 5. loadFromBackend 用后端快照校正 currentSessionId 时，把本轮前端新建、
 *    还没落库的会话 ID（时间戳格式）置 null；
 * 11. 删除会话失败回滚了列表，却没恢复 currentSessionId。
 *
 * isLocalPendingSessionId 是 useChatSessions 提取的纯 helper，锁住「本地新建
 * ID 不被误判成后端已删除」的语义。
 */
import { describe, expect, it } from 'vitest';
import { isLocalPendingSessionId } from '../useChatSessions';

describe('isLocalPendingSessionId', () => {
  it('识别本地新建 ID（时间戳-随机后缀）', () => {
    expect(isLocalPendingSessionId('1764123456789-ab3x9z')).toBe(true);
    expect(isLocalPendingSessionId(`${Date.now()}-q1w2e3`)).toBe(true);
  });

  it('不误判后端真实 session_id', () => {
    expect(isLocalPendingSessionId('s-abc123')).toBe(false);
    expect(isLocalPendingSessionId('550e8400-e29b-41d4-a716-446655440000')).toBe(false);
    expect(isLocalPendingSessionId('session-1')).toBe(false);
  });

  it('不误判带其他前缀的伪本地 ID', () => {
    expect(isLocalPendingSessionId('1764123456789')).toBe(false); // 缺随机后缀
    expect(isLocalPendingSessionId('pending-1764123456789')).toBe(false);
  });
});
