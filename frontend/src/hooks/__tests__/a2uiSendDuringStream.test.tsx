/**
 * 回归：A2UI 提交在流式进行中必须真正发出（不能静默丢弃）。
 *
 * 历史故障：A2UI 界面是在本轮流式过程中下发的（tool_end 后立刻推给前端）。
 * 用户填完表点提交时 isLoading 仍为 true，handleSend 的守卫直接
 * `return false` —— 前端一行日志都没有，用户看到的就是「点提交没反应」。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';

// 必须在 import 之前 mock：hook 顶部静态 import 了 sendMessageStream
vi.mock('../../services/agentService', async () => {
  const actual = await vi.importActual<typeof import('../../services/agentService')>(
    '../../services/agentService',
  );
  return {
    ...actual,
    sendMessageStream: vi.fn(),
  };
});

import { useChatStream } from '../useChatStream';
import * as agentService from '../../services/agentService';
import type { Session } from '../../types';

const sendMessageStream = agentService.sendMessageStream as unknown as ReturnType<typeof vi.fn>;

type Harness = {
  send: (text: string, files?: File[], source?: 'composer' | 'a2ui') => Promise<boolean>;
  isLoading: () => boolean;
};

/** 把 hook 挂进一个真实 React 树里，暴露调用入口。 */
function mountHook(initialSessions: Session[]) {
  const harness: Partial<Harness> = {};
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);

  function Probe() {
    const [sessions, setSessions] = React.useState<Session[]>(initialSessions);
    const [currentSessionId, setCurrentSessionId] = React.useState<string | null>(
      initialSessions[0]?.id ?? null,
    );
    const [, setInputValue] = React.useState('');
    const [, setArtifact] = React.useState<null>(null);
    const stream = useChatStream({
      sessions,
      setSessions,
      currentSessionId,
      setCurrentSessionId,
      currentSession: sessions.find((s) => s.id === currentSessionId) ?? null,
      chatMode: 'general',
      approvalMode: 'auto',
      planMode: false,
      selectedAgentProfileId: null,
      selectedAgent: null,
      applySessionState: () => {},
      setArtifact: setArtifact as never,
      setInputValue,
    });
    harness.send = stream.handleSend as never;
    harness.isLoading = () => stream.isLoading;
    return React.createElement('div', null, `loading=${stream.isLoading}`);
  }

  act(() => {
    root.render(React.createElement(Probe));
  });
  return { harness: harness as Harness, root, host };
}

/** 一个可被 abort 结束的流：模拟"本轮还在流式输出"。 */
function pendingStream() {
  let finish: (() => void) | null = null;
  sendMessageStream.mockImplementation(
    (_text: string, options: { signal?: AbortSignal }) =>
      new Promise((resolve) => {
        const settle = (finishReason: string) => () =>
          resolve({
            sessionId: 's1',
            text: 'done',
            finishReason,
            toolCalls: undefined,
            sessionState: undefined,
          });
        finish = settle('stop');
        // 真实 sendMessageStream 在 signal abort 时会以 interrupted 收尾，
        // 这里必须照做，否则 loadingSessionId 永远落不下来、排队 effect 不触发
        options.signal?.addEventListener('abort', settle('interrupted'), { once: true });
      }),
  );
  return () => finish?.();
}

beforeEach(() => {
  sendMessageStream.mockReset();
});

describe('A2UI 提交不被 isLoading 丢弃', () => {
  it('流式进行中点提交：不静默失败，且结束后真正发出', async () => {
    const release = pendingStream();
    const { harness, root } = mountHook([
      { id: 's1', title: 't', messages: [], updatedAt: Date.now() },
    ]);

    // 第一轮：输入框发起，进入 loading
    await act(async () => {
      void harness.send('开始', undefined, 'composer');
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(harness.isLoading(), '第一轮应处于流式状态').toBe(true);

    // 输入框在流式中发送 → 仍应被拒（防重复提交）
    let composerResult: boolean | undefined;
    await act(async () => {
      composerResult = await harness.send('重复提交', undefined, 'composer');
    });
    expect(composerResult, '输入框在流式中应被拒绝').toBe(false);

    // A2UI 提交 → 必须被接受（不能静默丢弃）
    let a2uiResult: boolean | undefined;
    await act(async () => {
      a2uiResult = await harness.send('我点击了提交按钮', undefined, 'a2ui');
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(a2uiResult, 'A2UI 提交不能被静默丢弃').toBe(true);

    // 收尾：放行第一轮，排队动作应被真正发出
    await act(async () => {
      release();
      await new Promise((r) => setTimeout(r, 120));
    });

    const sentTexts = sendMessageStream.mock.calls.map((c) => c[0] as string);
    expect(sentTexts, '排队的 A2UI 动作必须在流结束后真正发出').toContain('我点击了提交按钮');

    root.unmount();
  });
});
