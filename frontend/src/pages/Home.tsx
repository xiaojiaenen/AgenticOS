import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, Globe, Mail, Presentation } from 'lucide-react';
import { Logo } from '../components/Logo';
import { Button } from '../components/shadcn/button';
import { AgentSelector } from '../components/ui/AgentSelector';
import { InlineSpinner } from '../components/ui/Skeletons';
import { MascotSurprised, SendIcon } from '../components/ui/AnimatedIcons';
import { AuroraBackground } from '../components/backgrounds/AuroraBackground';
import { getStoredUser } from '../services/authService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';
import { cn } from '../lib/utils';

/** 快捷入口：图标 + 一句话，一点即达（直接带着 initialMessage 进对话） */
const QUICK_STARTS = [
  { text: '帮我做个 PPT', hint: '结构化演示文稿', mode: 'ppt', icon: Presentation, tone: 'text-amber-600 bg-amber-500/10 dark:text-amber-300' },
  { text: '写一个网站首页', hint: '可部署的前端页面', mode: 'website', icon: Globe, tone: 'text-sky-600 bg-sky-500/10 dark:text-sky-300' },
  { text: '帮我分析数据', hint: '数据洞察一站式', mode: 'general', icon: BarChart3, tone: 'text-emerald-600 bg-emerald-500/10 dark:text-emerald-300' },
  { text: '写一封邮件', hint: '商务往来一键起草', mode: 'general', icon: Mail, tone: 'text-indigo-600 bg-indigo-500/10 dark:text-indigo-300' },
] as const;

export const Home = () => {
  const [inputValue, setInputValue] = useState('');
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [agentsState, setAgentsState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>(null);
  const navigate = useNavigate();
  // getStoredUser() 每次调用都 JSON.parse 出新对象：用惰性 state 只取一次，
  // 既拿到稳定的引用（可安全依赖），也能显示用户名。
  const [user] = useState(() => getStoredUser());
  const isLoggedIn = Boolean(user);
  const selectedAgent = agentProfiles.find((a) => a.id === selectedAgentProfileId) || null;

  // 默认选中只在「首次拿到列表」时做一次：之后任何重新拉取都不得覆盖用户的选择
  const hasAppliedDefaultRef = React.useRef(false);

  const loadAgents = useCallback(() => {
    if (!isLoggedIn) return;
    setAgentsState('loading');
    getMyAgents()
      .then((res) => {
        setAgentProfiles(res.items);
        // 默认选中只在首次拿到列表时做一次：重新拉取/重新渲染都不得覆盖
        // 用户的选择（否则选完就跳回「通用助手」）
        if (!hasAppliedDefaultRef.current) {
          const general = res.items.find((a) => a.slug === 'general');
          if (general) setSelectedAgentProfileId(general.id);
          hasAppliedDefaultRef.current = true;
        }
        setAgentsState('idle');
      })
      .catch(() => setAgentsState('error'));
  }, [isLoggedIn]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const handleSend = () => {
    if (!inputValue.trim()) return;
    navigate('/chat', {
      state: {
        initialMessage: inputValue,
        mode: selectedAgent?.response_mode || 'general',
        agentProfileId: selectedAgentProfileId,
      },
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // 中文 IME 组词中（nativeEvent.isComposing）不触发发送，否则选词即发送
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (nativeEvent.isComposing || e.key === 'Process') return;
    if (e.key === 'Enter' && e.shiftKey) {
      // Allow shift+enter for new line
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <motion.div
      key="home"
      /* 挂载即可见：整页可见性不依赖 motion 入场（防懒加载竞态白屏） */
      initial={false}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      className="min-h-screen relative overflow-hidden font-sans flex flex-col bg-[var(--surface-2)]"
    >
      {/* 极光雾背景（低饱和 indigo，WebGL 不可用时自动降级为静态渐变） */}
      <AuroraBackground className="absolute" />

      {/* 背景装饰 — 极光 + 单一静态光晕 + 细点阵。刻意不放巨型水印：
          1000px 吉祥物会把首屏变成「灰色糊底」，喧宾夺主（走查结论 2026-11） */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute -top-32 -left-20 w-[620px] h-[620px] rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.10),transparent_70%)] blur-[80px]" />

        {/* Subtle dot grid */}
        <div className="absolute inset-0" style={{
          backgroundImage:
            'radial-gradient(circle, rgba(99,102,241,0.08) 1px, transparent 1px)',
          backgroundSize: '52px 52px',
          maskImage: 'linear-gradient(180deg, rgba(0,0,0,0.45), rgba(0,0,0,0.06) 55%, rgba(0,0,0,0.15))',
        }} />
      </div>

      {/* Top Navigation */}
      <nav className="flex items-center justify-between px-6 py-4 relative z-10 w-full max-w-[1400px] mx-auto">
        <Logo />
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            onClick={() => navigate(user ? '/chat' : '/agents')}
          >
            {user ? '开始对话' : '智能体商店'}
          </Button>
          {user ? (
            <Button variant="outline" onClick={() => navigate('/agents')}>
              {user.name}
            </Button>
          ) : (
            <Button onClick={() => navigate('/login')}>
              登录
            </Button>
          )}
        </div>
      </nav>

      {/* Hero Section —— 入场编排：标题 → 副题 → 输入卡 → 快捷卡，统一 easeOutQuint */}
      <main id="main-content" className="flex-1 flex flex-col items-center justify-center px-4 relative z-10 w-full max-w-[1400px] mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col items-center"
        >
          <h1 className="text-4xl md:text-5xl font-semibold mb-5 flex items-center gap-4 tracking-tight text-[var(--foreground)]">
            一句话
            <MascotSurprised size={48} className="-rotate-6 text-[var(--foreground)]" />
            呈所想
          </h1>
          <p className="mb-10 text-base md:text-lg text-[var(--muted-foreground)]">
            与 AI 对话轻松创建应用和网站
          </p>
        </motion.div>

        {/* Big Input Box */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-3xl"
        >
          <div className="rounded-2xl border border-[var(--border-subtle)] bg-card shadow-md p-3 transition-all focus-within:border-[var(--ring)] focus-within:shadow-lg focus-within:ring-[3px] focus-within:ring-[var(--ring-halo)]">
            <textarea
              aria-label="输入消息"
              className="w-full h-20 bg-transparent resize-none outline-none text-lg p-3 leading-relaxed text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]"
              placeholder="输入你想聊的内容，例如：帮我写一段 Python 代码..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={4000}
            />
            <div className="flex justify-between items-center gap-3 px-4 pb-3">
              {user ? (
                agentsState === 'error' ? (
                  <span className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                    智能体加载失败
                    <button
                      type="button"
                      onClick={loadAgents}
                      className="font-semibold text-[var(--foreground)] underline underline-offset-2 hover:opacity-80"
                    >
                      重试
                    </button>
                  </span>
                ) : agentProfiles.length > 0 ? (
                  <AgentSelector
                    agents={agentProfiles}
                    selectedId={selectedAgentProfileId}
                    onSelect={(agent) => setSelectedAgentProfileId(agent.id)}
                    variant="full"
                  />
                ) : (
                  <InlineSpinner label="加载智能体列表中…" />
                )
              ) : (
                <span className="text-xs text-[var(--muted-foreground)]">
                  登录后可选择专属智能体
                </span>
              )}

              <button
                onClick={handleSend}
                disabled={!inputValue.trim()}
                className="size-10 rounded-full flex items-center justify-center transition-all flex-shrink-0 group bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)] disabled:opacity-40 disabled:cursor-not-allowed"
                aria-label="发送消息"
              >
                <SendIcon size={20} className="group-hover:-translate-y-0.5" />
              </button>
            </div>
          </div>
        </motion.div>
        {/* 快捷入口卡：图标 + 主文案 + 一句提示，桌面 4 列网格 */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="mt-6 grid w-full max-w-3xl grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4"
        >
          {QUICK_STARTS.map((s) => (
            <button
              key={s.text}
              onClick={() => {
                // 点击即发起，而不是只把文字填进输入框再让用户点一次发送 ——
                // 快捷入口的意义就是「一点即用」。
                setInputValue(s.text);
                if (!user) {
                  navigate('/login', { state: { from: s.text } });
                  return;
                }
                navigate('/chat', {
                  state: {
                    initialMessage: s.text,
                    mode: s.mode,
                    agentProfileId: selectedAgentProfileId,
                  },
                });
              }}
              className="group flex items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-card px-3.5 py-3 text-left shadow-xs transition-all duration-150 hover:-translate-y-0.5 hover:border-[var(--border-strong)] hover:shadow-md active:scale-[0.98] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
            >
              <span className={cn('mt-0.5 flex size-8 flex-shrink-0 items-center justify-center rounded-lg transition-transform duration-150 group-hover:scale-110', s.tone)}>
                <s.icon size={16} strokeWidth={2} />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-[var(--foreground)]">{s.text}</span>
                <span className="mt-0.5 block truncate text-xs text-[var(--muted-foreground)]">{s.hint}</span>
              </span>
            </button>
          ))}
        </motion.div>
      </main>
    </motion.div>
  );
};
