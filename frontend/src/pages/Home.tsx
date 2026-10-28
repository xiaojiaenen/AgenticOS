import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { Button } from '../components/shadcn/button';
import { RandomMascot } from '../components/ui/RandomMascot';
import { AgentSelector } from '../components/ui/AgentSelector';
import { InlineSpinner } from '../components/ui/Skeletons';
import { MascotSurprised, SendIcon } from '../components/ui/AnimatedIcons';
import { AuroraBackground } from '../components/backgrounds/AuroraBackground';
import { getStoredUser } from '../services/authService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';

export const Home = () => {
  const [inputValue, setInputValue] = useState('');
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [agentsState, setAgentsState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>(null);
  const navigate = useNavigate();
  const user = getStoredUser();
  const selectedAgent = agentProfiles.find((a) => a.id === selectedAgentProfileId) || null;

  const loadAgents = useCallback(() => {
    if (!user) return;
    setAgentsState('loading');
    getMyAgents()
      .then((res) => {
        setAgentProfiles(res.items);
        const general = res.items.find((a) => a.slug === 'general');
        if (general) setSelectedAgentProfileId(general.id);
        setAgentsState('idle');
      })
      .catch(() => setAgentsState('error'));
  }, [user]);

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
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      transition={{ duration: 0.3 }}
      className="min-h-screen relative overflow-hidden font-sans flex flex-col bg-[var(--surface-2)]"
    >
      {/* 极光雾背景（低饱和 indigo，WebGL 不可用时自动降级为静态渐变） */}
      <AuroraBackground className="absolute" />

      {/* 背景装饰 — 静态光晕 + 点阵，无 infinite 动画 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute -top-32 -left-20 w-[620px] h-[620px] rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.10),transparent_70%)] blur-[80px]" />
        <div className="absolute -bottom-24 left-1/3 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(129,140,248,0.08),transparent_70%)] blur-[90px]" />

        {/* Subtle dot grid */}
        <div className="absolute inset-0" style={{
          backgroundImage:
            'radial-gradient(circle, rgba(99,102,241,0.08) 1px, transparent 1px)',
          backgroundSize: '52px 52px',
          maskImage: 'linear-gradient(180deg, rgba(0,0,0,0.45), rgba(0,0,0,0.06) 55%, rgba(0,0,0,0.15))',
        }} />

        {/* Giant Mascot Background */}
        <div className="absolute inset-0 flex items-center justify-center opacity-[0.035] text-[var(--foreground)] pointer-events-none">
          <RandomMascot size={1000} />
        </div>
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

      {/* Hero Section */}
      <main id="main-content" className="flex-1 flex flex-col items-center justify-center px-4 relative z-10 w-full max-w-[1400px] mx-auto">
        <h1 className="text-4xl md:text-5xl font-semibold mb-6 flex items-center gap-4 tracking-tight text-[var(--foreground)]">
          一句话
          <MascotSurprised size={48} className="-rotate-6 text-[var(--foreground)]" />
          呈所想
        </h1>
        <p className="mb-10 text-base md:text-lg text-[var(--muted-foreground)]">
          与 AI 对话轻松创建应用和网站
        </p>

        {/* Big Input Box */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.4 }}
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
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="mt-6 flex flex-wrap justify-center gap-2 max-w-3xl"
        >
          {[
            { text: '帮我做个 PPT', mode: 'ppt' },
            { text: '写一个网站首页', mode: 'website' },
            { text: '帮我分析数据', mode: 'general' },
            { text: '写一封邮件', mode: 'general' },
          ].map((s) => (
            <React.Fragment key={s.text}>
              <button
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
                className="px-4 py-2 rounded-full text-sm font-medium border border-[var(--border-subtle)] bg-card text-[var(--muted-foreground)] hover:border-[var(--border-strong)] hover:text-[var(--foreground)] hover:shadow-sm transition-all active:scale-[0.98] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
              >
                {s.text}
              </button>
            </React.Fragment>
          ))}
        </motion.div>
      </main>
    </motion.div>
  );
};
