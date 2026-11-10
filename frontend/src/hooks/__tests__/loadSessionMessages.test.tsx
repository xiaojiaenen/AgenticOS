/**
 * 回归：loadSessionMessages 的回源行为。
 *
 * 两个历史故障，都真实发生过：
 * 1. 新建对话的本地会话回源 404「会话不存在」刷控制台报错 —— 404 必须静默；
 * 2. 试图用「后端已知会话集合」守卫回源时，页面刷新恢复会话的场景下
 *    loadFromBackend 的列表请求尚未返回、集合还是空的，守卫误跳过回源，
 *    缓存剥离掉的 artifact HTML 永远补不回来，预览面板无法恢复。
 *    所以回源必须**无条件**发起，任何前置守卫都是回归。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { ApiError } from '../../services/apiClient';
import type { Session } from '../../types';

vi.mock('../../services/authService', () => ({
  getStoredUser: () => null,
}));

vi.mock('../../services/agentService', () => ({
  listSessions: vi.fn(async () => []),
  deleteSession: vi.fn(async () => true),
  getSessionMessages: vi.fn(),
  getSessionArtifacts: vi.fn(),
}));

import { useChatSessions } from '../useChatSessions';
import * as agentService from '../../services/agentService';

const getSessionMessages = agentService.getSessionMessages as unknown as ReturnType<typeof vi.fn>;
const getSessionArtifacts = agentService.getSessionArtifacts as unknown as ReturnType<typeof vi.fn>;
const listSessions = agentService.listSessions as unknown as ReturnType<typeof vi.fn>;

type Harness = {
  load: (sid: string) => Promise<boolean>;
  sessions: () => Session[];
};

async function mountHook() {
  const harness: Partial<Harness> = {};
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);

  function Probe() {
    const hook = useChatSessions();
    harness.load = hook.loadSessionMessages;
    harness.sessions = () => hook.sessions;
    return null;
  }

  await act(async () => {
    root.render(<Probe />);
  });
  // 等 mount effect 里的 listSessions 落地（被 mock 成立即返回）
  return {
    harness: harness as Harness,
    cleanup: () => {
      act(() => {
        root.unmount();
      });
      host.remove();
    },
  };
}

const OK_MESSAGES = [{ id: 'm1', role: 'user', text: '你好' }];

/** 预置一条本地缓存会话：真实流程里回源目标会话来自缓存/后端列表，而非凭空出现。 */
function seedCache(sessions: Array<Record<string, unknown>>) {
  localStorage.setItem('chat_sessions_guest', JSON.stringify(sessions));
}

beforeEach(() => {
  // React 19 在 jsdom 里默认会因 act 环境未声明而刷 console.error，
  // 不标记的话 404 静默断言会被这些告警污染
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  vi.clearAllMocks();
  getSessionMessages.mockReset();
  getSessionArtifacts.mockReset();
  listSessions.mockReset();
  getSessionArtifacts.mockResolvedValue({});
  listSessions.mockResolvedValue([]);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useChatSessions.loadSessionMessages', () => {
  it('正常回源：消息写入会话（不跳过）', async () => {
    seedCache([{ id: 's1', title: 'T', messages: [] as Session['messages'], updatedAt: Date.now() }]);
    getSessionMessages.mockResolvedValue(OK_MESSAGES);
    const { harness, cleanup } = await mountHook();

    let ok: boolean | undefined;
    await act(async () => {
      ok = await harness.load('s1');
    });

    expect(getSessionMessages).toHaveBeenCalledWith('s1');
    expect(ok).toBe(true);
    expect(harness.sessions()[0]?.messages?.[0]?.text).toBe('你好');
    cleanup();
  });

  it('会话列表请求挂起时（刷新恢复的时序竞态）回源仍执行', async () => {
    // 复现部署时踩到的回归：listSessions 永不返回 → "后端已知集合"为空。
    // 任何基于该集合的前置守卫都会在这里误跳过回源。
    listSessions.mockImplementation(() => new Promise(() => {}));
    getSessionMessages.mockResolvedValue(OK_MESSAGES);
    const { harness, cleanup } = await mountHook();

    let ok: boolean | undefined;
    await act(async () => {
      ok = await harness.load('s-pending');
    });

    expect(getSessionMessages).toHaveBeenCalledWith('s-pending');
    expect(ok).toBe(true);
    cleanup();
  });

  it('404 会话不存在：静默返回 false，不刷报错，不动本地消息', async () => {
    getSessionMessages.mockRejectedValue(
      new ApiError(404, { detail: '会话不存在' }, '会话不存在'),
    );
    const { harness, cleanup } = await mountHook();

    let ok: boolean | undefined;
    await act(async () => {
      ok = await harness.load('local-new-session');
    });

    expect(ok).toBe(false);
    expect(console.error).not.toHaveBeenCalled();
    cleanup();
  });

  it('非 404 错误仍然记录 console.error', async () => {
    getSessionMessages.mockRejectedValue(new ApiError(500, {}, '服务器错误'));
    const { harness, cleanup } = await mountHook();

    let ok: boolean | undefined;
    await act(async () => {
      ok = await harness.load('s1');
    });

    expect(ok).toBe(false);
    expect(console.error).toHaveBeenCalled();
    cleanup();
  });
});