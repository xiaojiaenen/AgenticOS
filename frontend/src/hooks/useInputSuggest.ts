import { useState, useRef, useCallback, useEffect } from 'react';
import { authHeaders } from '../services/authService';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SUGGEST_ENDPOINT = `${API_BASE_URL}/api/v1/agent/suggest`;

export function useInputSuggest() {
  const [suggestion, setSuggestion] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchSuggestion = useCallback(async (query: string) => {
    if (query.length < 2) {
      setSuggestion('');
      return;
    }

    // 取消上一次请求
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(
        `${SUGGEST_ENDPOINT}?q=${encodeURIComponent(query)}&limit=1`,
        { headers: authHeaders(), signal: controller.signal },
      );
      if (!response.ok) return;
      const data = await response.json();
      const first = data.suggestions?.[0];
      if (first && first !== query && first.startsWith(query)) {
        setSuggestion(first);
      } else {
        setSuggestion('');
      }
    } catch {
      // 忽略 abort 和网络错误
    }
  }, []);

  const onChange = useCallback((value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.length < 2) {
      setSuggestion('');
      return;
    }
    debounceRef.current = setTimeout(() => fetchSuggestion(value), 300);
  }, [fetchSuggestion]);

  const accept = useCallback((): string => {
    const accepted = suggestion;
    setSuggestion('');
    return accepted;
  }, [suggestion]);

  const dismiss = useCallback(() => {
    setSuggestion('');
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return { suggestion, onChange, accept, dismiss };
}
