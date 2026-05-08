import { useState, useEffect, useRef, useCallback } from 'react';
import { Session, Message } from '../types';

const CHAT_CACHE_KEY = 'chat_sessions';
const MAX_PERSISTED_SESSIONS = 24;
const MAX_PERSISTED_MESSAGES_PER_SESSION = 80;
const MAX_PERSISTED_TEXT_LENGTH = 12_000;
const MAX_PERSISTED_TOOL_RESULT_LENGTH = 4_000;

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
    pptArtifact: message.pptArtifact
      ? {
          status: message.pptArtifact.status,
          artifactId: message.pptArtifact.artifactId,
          title: message.pptArtifact.title,
          slideCount: message.pptArtifact.slideCount,
        }
      : undefined,
  };
}

function serializeSessionsForStorage(sessions: Session[]): Session[] {
  return [...sessions]
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, MAX_PERSISTED_SESSIONS)
    .map((session) => ({
      ...session,
      messages: session.messages
        .slice(-MAX_PERSISTED_MESSAGES_PER_SESSION)
        .map((message) => compactMessageForStorage(message)),
    }));
}

function loadStoredSessions(): Session[] {
  const saved = localStorage.getItem(CHAT_CACHE_KEY);
  if (!saved) return [];
  try {
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) ? parsed as Session[] : [];
  } catch {
    return [];
  }
}

export function useChatSessions() {
  const [sessions, setSessions] = useState<Session[]>(() => loadStoredSessions());
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [visibleSessionsCount, setVisibleSessionsCount] = useState(10);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSession = sessions.find(s => s.id === currentSessionId);

  const visibleSessions = sessions.slice(0, visibleSessionsCount);
  const hasMoreSessions = sessions.length > visibleSessionsCount;

  // Persist to localStorage with throttle during streaming
  useEffect(() => {
    if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    const data = serializeSessionsForStorage(sessions);
    persistTimerRef.current = setTimeout(() => {
      localStorage.setItem(CHAT_CACHE_KEY, JSON.stringify(data));
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

  const deleteSession = useCallback((id: string) => {
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
  };
}
