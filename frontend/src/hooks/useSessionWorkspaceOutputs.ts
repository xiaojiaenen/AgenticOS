/**
 * 会话工作区产物拉取 + 流结束后侧栏自动展示。
 *
 * 数据只按「会话」拉，不按消息拉 —— 用户报的痛点是模型用
 * write_text_file("index.html") 写出的网页只在工作区文件面板里，
 * 对话下方和侧栏产物库都看不到。这里把工作区文件纳入统一的产物口径。
 *
 * 触发时机（刻意克制，避免每次流式帧都发请求）：
 * 1. 当前会话切换（仅非空 sessionId）；
 * 2. 一轮 run 结束（runStatus 进入 done），且本轮确实产出了新文件；
 * 3. 侧栏「文件/产物」面板手动刷新（refresh()）。
 *
 * 自动打开侧栏只发生在「本轮新增了可展示产物」时，不会每轮弹窗。
 */
import * as React from 'react';
import { apiFetch } from '../services/apiClient';
import { useChatStore } from '../stores/chatStore';
import {
  collectDisplayableOutputs,
  countMessageArtifacts,
  type WorkspaceEntry,
} from '../lib/workspaceArtifacts';
import { panelTab } from '../components/panel/tabs';
import type { Message } from '../types';

type WorkspaceResponse = { entries?: WorkspaceEntry[]; root_exists?: boolean };

async function fetchWorkspaceOutputs(sessionId: string): Promise<WorkspaceEntry[]> {
  const data = await apiFetch<WorkspaceResponse>(
    `/api/v1/files/workspace?session_id=${encodeURIComponent(sessionId)}&path=`,
    {},
    '加载会话产物失败',
  );
  return collectDisplayableOutputs(data.entries ?? []);
}

/**
 * @param sessionId 当前会话 id
 * @param messages 当前会话消息（用于判断结构化产物数是否增加）
 */
export function useSessionWorkspaceOutputs(sessionId: string | null, messages: Message[]) {
  const sessionWorkspaceOutputs = useChatStore((s) => s.sessionWorkspaceOutputs);
  const setSessionWorkspaceOutputs = useChatStore((s) => s.setSessionWorkspaceOutputs);
  const runPhase = useChatStore((s) => s.runStatus.phase);
  const openTab = useChatStore((s) => s.openSidebarTab);

  /** 记录上次已展示的产物签名，避免每轮 done 都弹侧栏。 */
  const lastSignatureRef = React.useRef<string>('');
  /** 上一帧的 run phase：只在「运行中 → done」的真实跃迁时才处理，
   *  避免会话切换 / 首次挂载时 runStatus 恰好停在 done 造成误弹。 */
  const prevPhaseRef = React.useRef(useChatStore.getState().runStatus.phase);
  const [initializedSession, setInitializedSession] = React.useState<string | null>(null);

  const refresh = React.useCallback(async (): Promise<WorkspaceEntry[]> => {
    if (!sessionId) {
      setSessionWorkspaceOutputs([]);
      return [];
    }
    try {
      const outputs = await fetchWorkspaceOutputs(sessionId);
      setSessionWorkspaceOutputs(outputs);
      return outputs;
    } catch {
      // 产物拉取失败不该打断对话；保留上次结果即可。
      return [];
    }
  }, [sessionId, setSessionWorkspaceOutputs]);

  // 会话切换：清空旧会话产物并拉一次新会话的。
  React.useEffect(() => {
    if (!sessionId) {
      setSessionWorkspaceOutputs([]);
      lastSignatureRef.current = '';
      setInitializedSession(null);
      return;
    }
    if (initializedSession === sessionId) return;
    setInitializedSession(sessionId);
    void refresh().then((outputs) => {
      lastSignatureRef.current = signature(outputs, countMessageArtifacts(messages));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // 一轮结束（done）：刷新产物，仅在本轮新增产物时自动打开侧栏产物库。
  React.useEffect(() => {
    const prev = prevPhaseRef.current;
    prevPhaseRef.current = runPhase;
    // 只有从「运行态」进入 done 才算一轮结束；会话切换（idle/done → done）
    // 与首次挂载都不触发自动弹窗。
    const activePhases = ['thinking', 'streaming', 'generating_ppt', 'rendering_ppt', 'rendering_website'];
    if (runPhase !== 'done' || !activePhases.includes(prev) || !sessionId) return;
    let cancelled = false;
    void (async () => {
      const outputs = await refresh();
      if (cancelled) return;
      const current = signature(outputs, countMessageArtifacts(messages));
      const previous = lastSignatureRef.current;
      lastSignatureRef.current = current;
      if (current && current !== previous) {
        // 新增产物：自动打开侧栏的「会话产物」tab（图一形态的入口）。
        openTab(panelTab('artifacts'));
      }
    })();
    return () => { cancelled = true; };
    // messages 不入依赖：流式每帧都会变，runPhase=done 时读的是当时最新值即可。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runPhase, sessionId]);

  return { sessionWorkspaceOutputs, refresh };
}

function signature(outputs: WorkspaceEntry[], messageArtifactCount: number): string {
  const paths = outputs.map((o) => o.path).sort().join('|');
  return `${messageArtifactCount}:${paths}`;
}
