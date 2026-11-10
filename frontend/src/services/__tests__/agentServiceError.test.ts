/**
 * 错误文案归一化回归：HTTP 非 2xx（FastAPI 的 {"detail": "..."} 包装）
 * 必须解出人话，不能把整段 JSON 原样展示给用户。
 *
 * 背景：/agent/stream 加了每用户频控（429 + Retry-After），同时既有
 * 403（无权访问该会话）/500（ensure_ready 失败）一直存在 —— 这些
 * 端点级错误的响应体都是 {"detail": "..."}，旧实现会把 JSON 原样抛给
 * useChatStream 展示成错误气泡。
 */
import { describe, expect, it } from 'vitest';
import { normalizeAgentError } from '../agentService';

describe('normalizeAgentError: FastAPI detail 信封解包', () => {
  it('解包 {"detail": "..."}，展示后端原文（429 频控文案带秒数）', () => {
    const raw = JSON.stringify({ detail: '运行过于频繁，请 300 秒后再试' });
    expect(normalizeAgentError(raw, '429')).toBe('运行过于频繁，请 300 秒后再试');
  });

  it('403 无权访问同样解包', () => {
    const raw = JSON.stringify({ detail: '无权访问该会话' });
    expect(normalizeAgentError(raw, '403')).toBe('无权访问该会话');
  });

  it('纯文本（SSE error 事件 message）原样保留', () => {
    expect(normalizeAgentError('预算耗尽: tokens 200000 >= 100000', 'BudgetExhausted')).toBe(
      '预算耗尽: tokens 200000 >= 100000',
    );
  });

  it('非 detail 键的 JSON 保持原文（不吞掉有用信息）', () => {
    const raw = JSON.stringify({ foo: 'bar' });
    expect(normalizeAgentError(raw, '500')).toBe(raw);
  });

  it('余额不足 / api key 等既有映射不受影响', () => {
    expect(
      normalizeAgentError(JSON.stringify({ detail: 'Error code: 402 - Insufficient Balance' }), '500'),
    ).toBe('模型服务余额不足，请联系管理员充值或切换可用模型。');
    expect(
      normalizeAgentError(JSON.stringify({ detail: 'Incorrect API key provided' }), '500'),
    ).toBe('模型服务密钥配置异常，请联系管理员检查配置。');
  });
});
