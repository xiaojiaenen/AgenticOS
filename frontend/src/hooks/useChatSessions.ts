import { useState, useEffect, useRef, useCallback } from 'react';
import { Session, Message } from '../types';
import { listSessions, deleteSession as deleteSessionApi, generateTitle, getSessionMessages } from '../services/agentService';
import { getStoredUser } from '../services/authService';

const MAX_PERSISTED_MESSAGES_PER_SESSION = 120;
const MAX_PERSISTED_TEXT_LENGTH = 30_000;
const MAX_PERSISTED_TOOL_RESULT_LENGTH = 10_000;

// 按用户 ID 隔离缓存 key
function getCacheKey(): string {
  const user = getStoredUser();
  return user ? `chat_sessions_${user.id}` : 'chat_sessions_guest';
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
    attachments: undefined,
    toolCalls: message.toolCalls?.map((tool) => ({
      ...tool,
      result: clampText(tool.result, MAX_PERSISTED_TOOL_RESULT_LENGTH),
    })),
    // 持久化 artifact 信息，包括 html（用于刷新后恢复预览）
    pptArtifact: message.pptArtifact
      ? {
          status: message.pptArtifact.status,
          artifactId: message.pptArtifact.artifactId,
          title: message.pptArtifact.title,
          slideCount: message.pptArtifact.slideCount,
          html: clampText(message.pptArtifact.html, 500_000), // 限制 500KB
          theme: message.pptArtifact.theme,
        }
      : undefined,
    websiteArtifact: message.websiteArtifact
      ? {
          status: message.websiteArtifact.status,
          artifactId: message.websiteArtifact.artifactId,
          title: message.websiteArtifact.title,
          projectSlug: message.websiteArtifact.projectSlug,
          html: clampText(message.websiteArtifact.html, 500_000),
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
  // 过滤掉空会话（没有消息的会话，除了当前正在创建的）
  const nonEmptySessions = sessions.filter(s => s.messages.length > 0);
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
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [visibleSessionsCount, setVisibleSessionsCount] = useState(10);
  const [isLoading, setIsLoading] = useState(true);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSession = sessions.find(s => s.id === currentSessionId);

  const visibleSessions = sessions.slice(0, visibleSessionsCount);
  const hasMoreSessions = sessions.length > visibleSessionsCount;

  // Load sessions from backend on mount
  useEffect(() => {
    let cancelled = false;

    async function loadFromBackend() {
      try {
        const backendSessions = await listSessions();
        if (cancelled) return;

        // Convert backend sessions to frontend Session format
        const converted: Session[] = backendSessions.map((s) => ({
          id: s.session_id,
          title: s.summary || (typeof s.metadata?.agent_profile_name === 'string' ? s.metadata.agent_profile_name : '') || '新对话',
          messages: [], // Messages will be loaded when session is selected
          createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
          updatedAt: s.updated_at ? new Date(s.updated_at).getTime() : Date.now(),
          summary: s.summary,
          messageCount: s.message_count,
          mode: (s.metadata?.response_mode as Session['mode']) || undefined,
          agentProfileId: (s.metadata?.agent_profile_id as number) ?? undefined,
        }));

        // Merge with cached sessions (preserve messages from cache)
        const cachedSessions = loadCachedSessions();
        const cachedMap = new Map(cachedSessions.map(s => [s.id, s]));

        const merged = converted.map((s) => {
          const cached = cachedMap.get(s.id);
          if (cached && cached.messages.length > 0) {
            return {
              ...s,
              messages: cached.messages,
              title: cached.title || s.title,
              mode: cached.mode || s.mode,
              agentProfileId: cached.agentProfileId ?? s.agentProfileId,
            };
          }
          return s;
        });

        // Use functional update to preserve sessions created in-flight
        // (e.g. from home page navigation) that haven't reached the backend yet
        setSessions((prev) => {
          const prevMap = new Map(prev.map((s) => [s.id, s]));
          const backendIds = new Set(merged.map((s) => s.id));
          // Start with backend sessions, merging in cached messages
          const result = merged.map((s) => {
            const existing = prevMap.get(s.id);
            if (existing) {
              return {
                ...s,
                messages: existing.messages.length > 0 ? existing.messages : s.messages,
                title: existing.title || s.title,
                mode: existing.mode || s.mode,
                agentProfileId: existing.agentProfileId ?? s.agentProfileId,
              };
            }
            return s;
          });
          // Preserve prev sessions not yet on backend (newly created)
          for (const s of prev) {
            if (!backendIds.has(s.id)) {
              result.unshift(s);
            }
          }
          saveSessionsToCache(result);
          return result;
        });
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

  const deleteSession = useCallback(async (id: string) => {
    try {
      await deleteSessionApi(id);
    } catch (error) {
      console.error('Failed to delete session from backend:', error);
    }
    // Always remove from local state
    setSessions(prev => prev.filter(s => s.id !== id));
    setCurrentSessionId(prev => (prev === id ? null : prev));
  }, []);

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
    setSessions(prev => [session, ...prev]);
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const backendSessions = await listSessions();
      const converted: Session[] = backendSessions.map((s) => ({
        id: s.session_id,
        title: s.summary || (typeof s.metadata?.agent_profile_name === 'string' ? s.metadata.agent_profile_name : '') || '新对话',
        messages: [],
        createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
        updatedAt: s.updated_at ? new Date(s.updated_at).getTime() : Date.now(),
        summary: s.summary,
        messageCount: s.message_count,
        mode: (s.metadata?.response_mode as Session['mode']) || undefined,
        agentProfileId: (s.metadata?.agent_profile_id as number) ?? undefined,
      }));

      // Preserve messages from current sessions
      const currentMap = new Map(sessions.map(s => [s.id, s]));
      const merged = converted.map((s) => {
        const current = currentMap.get(s.id);
        if (current && current.messages.length > 0) {
          return {
            ...s,
            messages: current.messages,
            title: current.title || s.title,
            mode: current.mode || s.mode,
            agentProfileId: current.agentProfileId ?? s.agentProfileId,
          };
        }
        return s;
      });

      setSessions((prev) => {
        const prevMap = new Map(prev.map((s) => [s.id, s]));
        const backendIds = new Set(converted.map((s) => s.id));
        const result = converted.map((s) => {
          const existing = prevMap.get(s.id);
          if (existing && existing.messages.length > 0) {
            return {
              ...s,
              messages: existing.messages,
              title: existing.title || s.title,
              mode: existing.mode || s.mode,
              agentProfileId: existing.agentProfileId ?? s.agentProfileId,
            };
          }
          return s;
        });
        for (const s of prev) {
          if (!backendIds.has(s.id)) {
            result.unshift(s);
          }
        }
        saveSessionsToCache(result);
        return result;
      });
    } catch (error) {
      console.error('Failed to refresh sessions:', error);
    }
  }, [sessions]);

  /** 从后端加载指定会话的完整消息历史（用于刷新后恢复） */
  const loadSessionMessages = useCallback(async (sessionId: string): Promise<boolean> => {
    // 检查当前会话是否已有消息
    const session = sessions.find(s => s.id === sessionId);
    if (session && session.messages.length > 0) return false; // 已有消息，无需加载

    try {
      const messages = await getSessionMessages(sessionId);
      if (messages.length === 0) return false;

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
