import { useState, useRef, useCallback, useEffect } from 'react';
import { authHeaders } from '../services/authService';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SUGGEST_ENDPOINT = `${API_BASE_URL}/api/v1/agent/suggest`;

// 本地缓存：相同前缀不重复请求
const CACHE_MAX = 200;
const cache = new Map<string, string>();

function getCached(prefix: string): string | undefined {
  return cache.get(prefix);
}

function setCache(prefix: string, value: string) {
  if (cache.size >= CACHE_MAX) {
    // 删除最早的 20% 条目
    const keys = [...cache.keys()];
    for (let i = 0; i < Math.floor(CACHE_MAX * 0.2); i++) {
      cache.delete(keys[i]);
    }
  }
  cache.set(prefix, value);
}

export function useInputSuggest() {
  const [suggestion, setSuggestion] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastQueryRef = useRef('');

  const fetchSuggestion = useCallback(async (query: string) => {
    if (query.length < 2) {
      setSuggestion('');
      return;
    }

    // 先查本地缓存
    const cached = getCached(query);
    if (cached !== undefined) {
      setSuggestion(cached);
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
      const suggestions: string[] = data.suggestions || [];
      // 优先找前缀匹配（用于 ghost text 续写），没有则用第一个子串匹配
      const prefixMatch = suggestions.find(s => s !== query && s.startsWith(query));
      const result = prefixMatch || '';
      setCache(query, result);
      // 只在请求成功后更新 suggestion，避免 abort 时误清
      if (!controller.signal.aborted) {
        setSuggestion(result);
      }
    } catch {
      // 忽略 abort 和网络错误
    }
  }, []);

  const onChange = useCallback((value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.length < 2) {
      setSuggestion('');
      lastQueryRef.current = '';
      return;
    }
    // 300ms 防抖，平衡响应速度和请求频率
    debounceRef.current = setTimeout(() => fetchSuggestion(value), 300);
  }, [fetchSuggestion]);

  const accept = useCallback((): string => {
    const accepted = suggestion;
    setSuggestion('');
    lastQueryRef.current = '';
    return accepted;
  }, [suggestion]);

  const dismiss = useCallback(() => {
    setSuggestion('');
    lastQueryRef.current = '';
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
