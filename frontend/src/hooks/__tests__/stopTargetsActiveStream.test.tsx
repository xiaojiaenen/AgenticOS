/**
 * 「停止生成」目标会话回归（issue 2）。
 *
 * 历史故障：handleStopGeneration 用 `currentSessionId ?? loadingSessionId` 作目标，
 * 后台流场景（用户已切到 B，A 仍在跑）会优先取当前展示的 B —— A 的流还在跑，
 * 却把 B 标成「已停止」（空壳气泡 + 悬挂审批被拒），真正该停的没停。
 *
 * 本测试钉住：切到 B 后点停止，被 abort 的必须是 A（实际在跑的会话），B 不受影响。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { createRoot } from 'react-dom/client';
import { act } from 'react';

const streamCalls: Array<{ signal?: AbortSignal; sessionId?: string | null }> = [];

vi.mock('../../services/authService', () => ({
  getStoredUser: () => null,
}));

vi.mock('../../services/agentService', () => ({
  sendMessageStream: vi.fn(async (_text: string, options: { signal?: AbortSignal; sessionId?: string | null }) => {
    streamCalls.push({ signal: options.signal, sessionId: options.sessionId });
    await new Promise<void>((resolve) => {
      if (options.signal?.aborted) return resolve();
      options.signal?.addEventListener('abort', () => resolve(), { once: true });
      setTimeout(resolve, 5_000);
    });
    return { finishReason: 'stop' };
  }),
  submitApprovalDecision: vi.fn(),
  submitUserDecision: vi.fn(),
  submitApiApproval: vi.fn(),
  getSessionMessages: vi.fn(async () => []),
  getSessionArtifacts: vi.fn(async () => ({})),
  listSessions: vi.fn(async () => []),
  deleteSession: vi.fn(async () => true),
}));

import { useChatStream } from '../useChatStream';

type Hook = ReturnType<typeof useChatStream>;

function Harness(props: { currentSessionId: string | null; onReady: (hook: Hook) => void }) {
  const hook = useChatStream({
    currentSessionId: props.currentSessionId,
    currentSession: null,
    chatMode: 'general',
    approvalMode: 'auto',
    planMode: false,
    selectedAgentProfileId: null,
    selectedAgent: null,
    sessions: [],
    setSessions: () => {},
    setCurrentSessionId: () => {},
    applySessionState: () => {},
    setArtifact: () => {},
    setInputValue: () => {},
  });
  props.onReady(hook);
  return null;
}

async function waitForStreamStarted(count = 1, timeoutMs = 2_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (streamCalls.length < count && Date.now() < deadline) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
  }
}

describe('handleStopGeneration 指向真正运行的会话', () => {
  beforeEach(() => {
    streamCalls.length = 0;
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  });

  it('当前展示 B、后台 A 在跑：停止应 abort A 而非 B', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    let hook: Hook | null = null;
    const render = (currentSessionId: string | null) =>
      act(async () => {
        root.render(
          <Harness
            currentSessionId={currentSessionId}
            onReady={(h) => {
              hook = h;
            }}
          />,
        );
      });

    await render('session-A');
    await act(async () => {
      void hook!.handleSend('A 的长任务').catch(() => {});
    });
    await waitForStreamStarted();
    const signalA = streamCalls[0].signal!;
    expect(signalA.aborted).toBe(false);

    // 用户切到 B，但 B 没有流
    await render('session-B');
    expect(signalA.aborted, '切会话不应打断 A').toBe(false);

    // 在 B 点停止 —— 应 abort 实际在跑的 A
    await act(async () => {
      hook!.handleStopGeneration();
      await Promise.resolve();
    });
    expect(signalA.aborted, '必须停止真正在跑的 A').toBe(true);

    await act(async () => root.unmount());
    container.remove();
  });
});
