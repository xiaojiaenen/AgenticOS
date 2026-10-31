/**
 * 公开智能体聊天页（/app/:slug）—— 一键发布产物的访客入口。
 *
 * 不要求登录：信息来自 GET /public/agents/{slug}，对话走
 * POST /public/agents/{slug}/chat（SSE）。独立轻量 SSE 客户端，
 * 不复用主聊天的事件状态机（那套绑定会话列表/审批/产物，公开页用不到）。
 * ?embed=1 = iframe 嵌入形态（widget.js 气泡打开的就是它）。
 */
import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';
import { Loader2, SendHorizontal, ShieldCheck } from 'lucide-react';

interface ChatItem {
  role: 'user' | 'assistant';
  text: string;
}

interface PublicAgentInfo {
  name: string;
  avatar: string | null;
  welcome: string;
  require_code: boolean;
}

export const PublicAgentChat = () => {
  const { slug = '' } = useParams();
  const [searchParams] = useSearchParams();
  const embedMode = searchParams.get('embed') === '1';

  const [info, setInfo] = useState<PublicAgentInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [accessCode, setAccessCode] = useState('');
  const [codeRequired, setCodeRequired] = useState(false);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`/api/v1/public/agents/${slug}`)
      .then(async (resp) => {
        if (!resp.ok) throw new Error((await resp.json().catch(() => ({})))?.detail || '加载失败');
        return resp.json();
      })
      .then((data) => {
        if (!alive) return;
        setInfo(data);
        setCodeRequired(Boolean(data.require_code));
        if (data.welcome) setItems([{ role: 'assistant', text: data.welcome }]);
      })
      .catch((err: Error) => alive && setLoadError(err.message));
    return () => {
      alive = false;
    };
  }, [slug]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items, streaming]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    setItems((prev) => [...prev, { role: 'user', text }, { role: 'assistant', text: '' }]);
    setStreaming(true);
    try {
      const resp = await fetch(`/api/v1/public/agents/${slug}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId, access_code: accessCode || undefined }),
      });
      if (!resp.ok || !resp.body) {
        const detail = (await resp.json().catch(() => ({})))?.detail;
        throw new Error(detail || `请求失败（${resp.status}）`);
      }
      // 解析 SSE：event/data 成对出现，delta 追加、done/session 更新
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = 'message';
      const updateAssistant = (fn: (prev: string) => string) =>
        setItems((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', text: fn(next[next.length - 1]?.text ?? '') };
          return next;
        });

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() ?? '';
        for (const chunk of chunks) {
          for (const line of chunk.split('\n')) {
            if (line.startsWith('event: ')) currentEvent = line.slice(7).trim();
            else if (line.startsWith('data: ')) {
              const raw = line.slice(6);
              let data: Record<string, unknown> = {};
              try {
                data = JSON.parse(raw) as Record<string, unknown>;
              } catch {
                continue;
              }
              if (currentEvent === 'session' && typeof data.session_id === 'string') {
                setSessionId(data.session_id);
              } else if (currentEvent === 'delta' && typeof data.content === 'string') {
                updateAssistant((prev) => prev + data.content);
              } else if (currentEvent === 'error') {
                const message = String(data.message ?? '出错了，请稍后重试');
                if (message.includes('访问码')) setCodeRequired(true);
                updateAssistant((prev) => prev + (prev ? `\n\n⚠️ ${message}` : `⚠️ ${message}`));
              } else if (currentEvent === 'run_status' && data.phase === 'thinking' && !data.detail) {
                updateAssistant((prev) => prev || '正在思考…');
              }
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '网络错误';
      setItems((prev) => [...prev, { role: 'assistant', text: `⚠️ ${message}` }]);
      if (message.includes('访问码')) setCodeRequired(true);
    } finally {
      setStreaming(false);
      // 清理「正在思考…」占位
      setItems((prev) => prev.map((i) => (i.role === 'assistant' && i.text === '正在思考…' ? { ...i, text: '' } : i)));
    }
  };

  const containerClass = embedMode
    ? 'flex h-screen flex-col bg-[var(--surface-0)]'
    : 'flex h-screen flex-col bg-[var(--surface-0)]';

  if (loadError) {
    return (
      <div className={`${containerClass} items-center justify-center`}>
        <div className="text-center">
          <div className="mb-2 text-lg font-semibold text-[var(--foreground)]">{loadError}</div>
          <div className="text-sm text-[var(--muted-foreground)]">链接可能已失效，请联系分享者</div>
        </div>
      </div>
    );
  }
  if (!info) {
    return (
      <div className={`${containerClass} items-center justify-center`}>
        <Loader2 className="animate-spin text-[var(--muted-foreground)]" />
      </div>
    );
  }

  return (
    <div className={containerClass}>
      <header className="flex items-center gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#2b87c2] text-sm font-semibold text-white">
          {info.name.slice(0, 1)}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--foreground)]">{info.name}</div>
          <div className="text-xs text-[var(--muted-foreground)]">由 AgenticOS 智能体驱动</div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {codeRequired && (
            <div className="mx-auto flex w-full max-w-md items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
              <ShieldCheck size={16} className="shrink-0 text-amber-600" />
              <input
                className="h-7 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-amber-500/70"
                placeholder="此应用需要访问码"
                type="password"
                value={accessCode}
                onChange={(e) => setAccessCode(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void send()}
              />
            </div>
          )}
          {items.map((item, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  item.role === 'user'
                    ? 'bg-[#2b87c2] text-white'
                    : 'border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)]'
                } ${item.role === 'assistant' && !item.text ? 'text-[var(--muted-foreground)]' : ''}`}
              >
                {item.text || (streaming && i === items.length - 1 ? '…' : '')}
              </div>
            </motion.div>
          ))}
          <div ref={bottomRef} />
        </div>
      </main>

      <footer className="border-t border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <input
            className="h-10 min-w-0 flex-1 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 text-sm outline-none focus:border-[#2b87c2]"
            placeholder={streaming ? '智能体正在回复…' : '输入你的问题'}
            value={input}
            disabled={streaming}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && void send()}
          />
          <button
            type="button"
            aria-label="发送"
            disabled={streaming || !input.trim()}
            onClick={() => void send()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#2b87c2] text-white transition active:scale-95 disabled:opacity-40"
          >
            {streaming ? <Loader2 size={16} className="animate-spin" /> : <SendHorizontal size={16} />}
          </button>
        </div>
      </footer>
    </div>
  );
};

export default PublicAgentChat;
