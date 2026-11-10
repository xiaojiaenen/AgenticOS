/**
 * 回归：切换会话不能打断正在运行的流。
 *
 * 线上反馈的真实症状：在 A 会话提问、生成到一半切到 B，切回 A 只剩半截回复。
 * 根因是 useChatStream 只有一个 abortControllerRef，切换会话的 effect 里
 * 无条件 abort()，后端因此收到 CancelledError，整轮 LLM 生成作废。
 *
 * 本测试钉死的语义：
 * 1. 切换会话不调用 abort；
 * 2. 「停止」只 abort 当前会话那一版 controller，其它会话后台流不受影响；
 * 3. 组件卸载才 abort 全部。
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
    // 模拟一个长时间不结束的流：一直等到被 abort
    await new Promise<void>((resolve) => {
      if (options.signal?.aborted) return resolve();
      options.signal?.addEventListener('abort', () => resolve(), { once: true });
      // 兜底超时，避免测试挂死
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

/** 等到 sendMessageStream 被调用至少 N 次（真实链路含 rAF / 上传等异步边界）。 */
async function waitForStreamStarted(count = 1, timeoutMs = 2_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (streamCalls.length < count && Date.now() < deadline) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
  }
}

type Hook = ReturnType<typeof useChatStream>;

function Harness(props: {
  currentSessionId: string | null;
  onReady: (hook: Hook) => void;
}) {
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

async function mount(props: { currentSessionId: string | null }, onHook: (h: Hook) => void) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  let latest: Hook | null = null;
  await act(async () => {
    root.render(
      <Harness
        currentSessionId={props.currentSessionId}
        onReady={(h) => {
          latest = h;
          onHook(h);
        }}
      />,
    );
  });
  const rerender = async (currentSessionId: string | null) => {
    await act(async () => {
      root.render(
        <Harness
          currentSessionId={currentSessionId}
          onReady={(h) => {
            latest = h;
            onHook(h);
          }}
        />,
      );
    });
  };
  const unmount = async () => {
    await act(async () => root.unmount());
    container.remove();
  };
  return {
    rerender,
    unmount,
    get hook() {
      return latest!;
    },
  };
}

describe('useChatStream：切换会话不打断后台流', () => {
  beforeEach(() => {
    streamCalls.length = 0;
  });

  it('切到别的会话时，正在跑的流不被 abort', async () => {
    const view = await mount({ currentSessionId: 'session-A' }, () => {});

    // 在 A 里发起一轮（不 await：模拟长时间生成）
    void view.hook.handleSend('你好').catch(() => {});
    await waitForStreamStarted();
    expect(streamCalls.length).toBeGreaterThan(0);
    const signal = streamCalls[0].signal!;
    expect(signal.aborted).toBe(false);

    // 切到 B
    await view.rerender('session-B');
    expect(signal.aborted).toBe(false);

    // 再切回 A —— 依然不该 abort
    await view.rerender('session-A');
    expect(signal.aborted).toBe(false);

    // 只有卸载才真正 abort（清理在途请求）
    await view.unmount();
    expect(signal.aborted).toBe(true);
  });

  it('「停止」只终止当前会话，不影响其它会话的后台流', async () => {
    const view = await mount({ currentSessionId: 'session-A' }, () => {});
    void view.hook.handleSend('第一轮').catch(() => {});
    await waitForStreamStarted();
    const signalA = streamCalls[0].signal!;

    await view.rerender('session-B');
    void view.hook.handleSend('第二轮').catch(() => {});
    await waitForStreamStarted(2);
    const signalB = streamCalls[streamCalls.length - 1].signal!;
    expect(signalB).toBeDefined();
    expect(signalA.aborted).toBe(false);

    // 在 B 点停止：只应 abort B
    await act(async () => {
      view.hook.handleStopGeneration();
      await Promise.resolve();
    });
    expect(signalB.aborted).toBe(true);
    expect(signalA.aborted).toBe(false);

    await view.unmount();
  });
});
