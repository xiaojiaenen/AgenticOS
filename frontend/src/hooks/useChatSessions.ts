import { useState, useEffect, useRef, useCallback } from 'react';
import { Session, Message } from '../types';
import { listSessions, deleteSession as deleteSessionApi, getSessionMessages, getSessionArtifacts } from '../services/agentService';
import { getStoredUser } from '../services/authService';
import {
  MAX_SESSIONS,
  convertBackendSession,
  mergeLocalIntoConverted,
  reconcileBackendWithLocal,
} from '../lib/sessionMerge';

const MAX_PERSISTED_MESSAGES_PER_SESSION = 120;
const MAX_PERSISTED_TEXT_LENGTH = 30_000;
const MAX_PERSISTED_TOOL_RESULT_LENGTH = 10_000;

// 按用户 ID 隔离缓存 key
function getCacheKey(): string {
  const user = getStoredUser();
  return user ? `chat_sessions_${user.id}` : 'chat_sessions_guest';
}

/** 上次打开的会话 id：刷新后恢复到原会话（含 PPT/网站预览面板） */
const CURRENT_SESSION_KEY = 'chat_current_session_id';

function loadCachedCurrentSessionId(): string | null {
  try {
    return localStorage.getItem(CURRENT_SESSION_KEY);
  } catch {
    return null;
  }
}

function clampText(value: string | undefined, limit: number): string | undefined {
  if (!value) return value;
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function compactMessageForStorage(message: Message): Message {
  return {
    ...message,
    text: clampText(message.text, MAX_PERSISTED_TEXT_LENGTH) || '',
    reasoningText: clampText(message.reasoningText, MAX_PERSISTED_TEXT_LENGTH),
    // blob URL 无法跨刷新恢复；保留元数据供 UI 提示「附件需重新上传」
    attachments: message.attachments?.map((att) => ({
      name: att.name,
      type: att.type,
      url: '',
    })),
    toolCalls: message.toolCalls?.map((tool) => ({
      ...tool,
      result: clampText(tool.result, MAX_PERSISTED_TOOL_RESULT_LENGTH),
    })),
    // 缓存瘦身：剥离 artifact HTML（单份最大可达 500KB），只保留元数据。
    // 预览恢复走回源：loadSessionMessages → getSessionArtifacts（Chat.tsx 会话切换时触发）。
    pptArtifact: message.pptArtifact
      ? {
          status: message.pptArtifact.status,
          artifactId: message.pptArtifact.artifactId,
          title: message.pptArtifact.title,
          slideCount: message.pptArtifact.slideCount,
          html: undefined,
          theme: message.pptArtifact.theme,
        }
      : undefined,
    websiteArtifact: message.websiteArtifact
      ? {
          status: message.websiteArtifact.status,
          artifactId: message.websiteArtifact.artifactId,
          title: message.websiteArtifact.title,
          projectSlug: message.websiteArtifact.projectSlug,
          html: undefined,
        }
      : undefined,
  };
}

function loadCachedSessions(): Session[] {
  const key = getCacheKey();
  const saved = localStorage.getItem(key);
  if (!saved) return [];
  try {
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) ? parsed as Session[] : [];
  } catch {
    return [];
  }
}

function saveSessionsToCache(sessions: Session[]) {
  const key = getCacheKey();
  // 过滤掉空会话（没有消息的会话，除了当前正在创建的），并限制总数为 24
  const nonEmptySessions = sessions.filter(s => s.messages.length > 0).slice(0, MAX_SESSIONS);
  const compacted = nonEmptySessions.map((session) => ({
    ...session,
    messages: session.messages
      .slice(-MAX_PERSISTED_MESSAGES_PER_SESSION)
      .map((message) => compactMessageForStorage(message)),
  }));
  try {
    localStorage.setItem(key, JSON.stringify(compacted));
  } catch (e) {
    // QuotaExceededError: 配额超限，逐个会话缩减直到能存下
    if (e instanceof DOMException && e.name === 'QuotaExceededError') {
      console.warn('localStorage quota exceeded, reducing cache size');
      try {
        // 只保留最近 5 个会话，每个最多 20 条消息
        const minimal = compacted.slice(0, 5).map(s => ({
          ...s,
          messages: s.messages.slice(-20),
        }));
        localStorage.setItem(key, JSON.stringify(minimal));
      } catch {
        // 仍然超限，清空缓存
        try { localStorage.removeItem(key); } catch { /* ignore */ }
      }
    }
  }
}

export function useChatSessions() {
  const [sessions, setSessions] = useState<Session[]>(() => loadCachedSessions());
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(loadCachedCurrentSessionId);
  const [visibleSessionsCount, setVisibleSessionsCount] = useState(10);
  const [isLoading, setIsLoading] = useState(true);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSession = sessions.find(s => s.id === currentSessionId);

  const visibleSessions = sessions.slice(0, visibleSessionsCount);
  const hasMoreSessions = sessions.length > visibleSessionsCount;

  // 持久化当前会话 id，刷新后回到同一会话（否则刷新即回到空态，
  // 用户会以为 PPT/网站产物丢了）
  useEffect(() => {
    try {
      if (currentSessionId) {
        localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId);
      } else {
        localStorage.removeItem(CURRENT_SESSION_KEY);
      }
    } catch {
      /* 隐私模式/配额限制：忽略 */
    }
  }, [currentSessionId]);

  // Load sessions from backend on mount
  useEffect(() => {
    let cancelled = false;

    async function loadFromBackend() {
      try {
        const backendSessions = await listSessions();
        if (cancelled) return;

        // Convert backend sessions to frontend Session format
        const converted: Session[] = backendSessions.map(convertBackendSession);

        // Merge with cached sessions (preserve messages from cache)
        const cachedSessions = loadCachedSessions();
        const merged = mergeLocalIntoConverted(converted, cachedSessions, { keepMessagesOnly: true });

        // Use functional update to preserve sessions created in-flight
        // (e.g. from home page navigation) that haven't reached the backend yet
        setSessions((prev) => {
          // 持久化交给下方 [sessions] 防抖 effect 统一处理（不在 setState updater 内做副作用）
          return reconcileBackendWithLocal(mergeLocalIntoConverted(merged, prev), prev);
        });

        // 缓存的当前会话可能已被删除（另一标签页/后端清理），此时退回空态
        setCurrentSessionId((prevId) =>
          prevId && merged.some((s) => s.id === prevId) ? prevId : null,
        );
      } catch (error) {
        console.error('Failed to load sessions from backend:', error);
        // Keep cached sessions on error
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadFromBackend();

    return () => {
      cancelled = true;
    };
  }, []);

  // Persist to localStorage with throttle during streaming
  useEffect(() => {
    if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    persistTimerRef.current = setTimeout(() => {
      saveSessionsToCache(sessions);
    }, 800);
    return () => {
      if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    };
  }, [sessions]);

  const loadMoreSessions = useCallback(() => {
    setVisibleSessionsCount(prev => prev + 10);
  }, []);

  const createNewChat = useCallback(() => {
    setCurrentSessionId(null);
  }, []);

  /**
   * 可靠删除：先乐观移除本地，调用后端 DELETE；失败时回滚本地状态。
   * 返回 true=成功，false=失败（已回滚）。
   */
  const deleteSession = useCallback(async (id: string): Promise<boolean> => {
    // 快照用于失败回滚（在 updater 外读取，避免 StrictMode 下 updater 双调用污染快照）
    const snapshot = sessions;
    setSessions(prev => prev.filter(s => s.id !== id));
    setCurrentSessionId(prev => (prev === id ? null : prev));

    try {
      await deleteSessionApi(id);
      return true;
    } catch (error) {
      console.error('Failed to delete session from backend:', error);
      // 后端失败 → 回滚本地删除
      setSessions(snapshot);
      return false;
    }
  }, [sessions]);

  const applySessionState = useCallback((targetId: string, state: {
    session_id: string;
    summary?: string | null;
    context_compressed?: boolean;
    storage?: string;
    last_usage?: Record<string, number> | null;
    last_latency_ms?: number | null;
    last_llm_calls?: number | null;
  }) => {
    setSessions(prev => prev.map(session => (
      session.id === targetId || session.id === state.session_id
        ? {
            ...session,
            id: state.session_id || session.id,
            summary: state.summary ?? session.summary,
            contextCompressed: state.context_compressed ?? session.contextCompressed,
            storage: state.storage ?? session.storage,
            lastUsage: state.last_usage ?? session.lastUsage,
            latencyMs: state.last_latency_ms ?? session.latencyMs,
            llmCalls: state.last_llm_calls ?? session.llmCalls,
          }
        : session
    )));
    if (targetId !== state.session_id && state.session_id) {
      setCurrentSessionId(prev => (prev === targetId ? state.session_id : prev));
    }
  }, []);

  const updateSessionMessage = useCallback((sessionId: string, messageId: string, updater: (msg: Message) => Message) => {
    setSessions(prev => prev.map(s => (
      s.id === sessionId
        ? { ...s, updatedAt: Date.now(), messages: s.messages.map(m => m.id === messageId ? updater(m) : m) }
        : s
    )));
  }, []);

  const addMessagesToSession = useCallback((sessionId: string, messages: Message[]) => {
    setSessions(prev => prev.map(s => (
      s.id === sessionId
        ? { ...s, updatedAt: Date.now(), messages: [...s.messages, ...messages] }
        : s
    )));
  }, []);

  const createSession = useCallback((session: Session) => {
    setSessions(prev => [session, ...prev].slice(0, MAX_SESSIONS));
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const backendSessions = await listSessions();
      const converted: Session[] = backendSessions.map(convertBackendSession);

      setSessions((prev) => {
        // 持久化交给 [sessions] 防抖 effect 统一处理（不在 setState updater 内做副作用）
        return reconcileBackendWithLocal(
          mergeLocalIntoConverted(converted, prev, { keepMessagesOnly: true }),
          prev,
        );
      });
    } catch (error) {
      console.error('Failed to refresh sessions:', error);
    }
  }, [sessions]);

  /** 从后端加载指定会话的完整消息历史（用于刷新后恢复） */
  const loadSessionMessages = useCallback(async (sessionId: string): Promise<boolean> => {
    // 检查当前会话是否已有消息
    const session = sessions.find(s => s.id === sessionId);
    const hasCachedMessages = session && session.messages.length > 0;
    
    // 即使有缓存消息，也要尝试拉取 artifacts 来恢复预览面板
    // 只有当既有缓存消息又已有带 HTML 的 artifact 时才跳过
    // （缓存中的 artifact 已剥离 HTML，需回源补全）
    if (hasCachedMessages) {
      const hasArtifact = session.messages.some(
        m => m.role === 'model' && ((m.pptArtifact && m.pptArtifact.html) || (m.websiteArtifact && m.websiteArtifact.html)),
      );
      if (hasArtifact) return false; // 已有消息且 artifact HTML 完整，无需加载
    }

    try {
      // 并行加载消息 + 会话最新制品（PPT/website），用于恢复预览面板
      const [messages, artifactsResp] = await Promise.all([
        hasCachedMessages ? Promise.resolve(session.messages) : getSessionMessages(sessionId),
        getSessionArtifacts(sessionId).catch(err => {
          console.warn('Failed to load session artifacts:', err);
          return null;
        }),
      ]);
      if (!hasCachedMessages && messages.length === 0) return false;

      // 把最新 artifact 挂到最后一条 model 消息上（与 useChatStream 的挂载逻辑一致）
      const pptArt = artifactsResp?.ppt_artifact;
      if (pptArt) {
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === 'model') {
            messages[i] = {
              ...messages[i],
              pptArtifact: {
                status: 'ready',
                artifactId: pptArt.artifact_id,
                title: pptArt.title,
                slideCount: pptArt.slide_count,
                html: pptArt.html,
                theme: pptArt.theme,
                mode: 'ppt',
              },
            };
            break;
          }
        }
      }

      // website 制品同样回源补全（缓存剥离 HTML 后依赖此路径恢复预览）
      const wsArt = artifactsResp?.website_artifact;
      if (wsArt) {
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === 'model') {
            messages[i] = {
              ...messages[i],
              websiteArtifact: {
                status: 'ready',
                artifactId: wsArt.artifact_id,
                title: wsArt.title,
                projectSlug: wsArt.project_slug,
                stack: wsArt.stack,
                html: wsArt.preview_html,
              },
            };
            break;
          }
        }
      }

      setSessions(prev => prev.map(s =>
        s.id === sessionId
          ? { ...s, messages, updatedAt: Date.now() }
          : s
      ));
      return true;
    } catch (error) {
      console.error('Failed to load session messages:', error);
      return false;
    }
  }, [sessions]);

  return {
    sessions,
    setSessions,
    currentSessionId,
    setCurrentSessionId,
    currentSession,
    visibleSessions,
    hasMoreSessions,
    loadMoreSessions,
    createNewChat,
    deleteSession,
    applySessionState,
    updateSessionMessage,
    addMessagesToSession,
    createSession,
    isLoading,
    refreshSessions,
    loadSessionMessages,
  };
}
