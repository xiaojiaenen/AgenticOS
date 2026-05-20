import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { Button } from '../components/ui/Button';
import { RandomMascot } from '../components/ui/RandomMascot';
import { AgentSelector } from '../components/ui/AgentSelector';
import { MascotSurprised, SendIcon } from '../components/ui/AnimatedIcons';
import { getStoredUser } from '../services/authService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';

export const Home = () => {
  const [inputValue, setInputValue] = useState('');
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>(null);
  const navigate = useNavigate();
  const user = getStoredUser();

  const selectedAgent = agentProfiles.find((a) => a.id === selectedAgentProfileId) || null;

  useEffect(() => {
    if (user) {
      getMyAgents()
        .then((res) => {
          setAgentProfiles(res.items);
          const general = res.items.find((a) => a.slug === 'general');
          if (general) setSelectedAgentProfileId(general.id);
        })
        .catch(() => { /* non-critical, silent */ });
    }
  }, []);

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
      exit={{ opacity: 0, transition: { duration: 0.3 } }}
      className="min-h-screen relative overflow-hidden font-sans flex flex-col selection:bg-zinc-200 selection:text-zinc-900"
      style={{
        background:
          'linear-gradient(180deg, #def0f6 0%, #e7f4f9 28%, #e1f2f7 55%, #e3f2f7 100%)',
      }}
    >
      {/* Animated ambient blob layer */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        {/* Large cyan blob — top left */}
        <div className="absolute -top-32 -left-20 w-[620px] h-[620px] rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.18),transparent_70%)] blur-[80px] animate-[bg-blob-1_14s_ease-in-out_infinite]" />
        {/* Teal blob — top right */}
        <div className="absolute -top-28 -right-16 w-[540px] h-[540px] rounded-full bg-[radial-gradient(circle,rgba(6,182,212,0.15),transparent_70%)] blur-[80px] animate-[bg-blob-2_16s_ease-in-out_infinite]" />
        {/* Sky blue blob — bottom left */}
        <div className="absolute -bottom-24 left-1/3 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.14),transparent_70%)] blur-[90px] animate-[bg-blob-3_15s_ease-in-out_infinite]" />
        {/* Cyan blob — bottom right */}
        <div className="absolute -bottom-20 -right-10 w-[460px] h-[460px] rounded-full bg-[radial-gradient(circle,rgba(34,211,238,0.13),transparent_70%)] blur-[80px] animate-[bg-blob-4_13s_ease-in-out_infinite]" />

        {/* Subtle dot grid */}
        <div className="absolute inset-0" style={{
          backgroundImage:
            'radial-gradient(circle, rgba(14,165,233,0.10) 1px, transparent 1px)',
          backgroundSize: '52px 52px',
          maskImage: 'linear-gradient(180deg, rgba(0,0,0,0.45), rgba(0,0,0,0.06) 55%, rgba(0,0,0,0.15))',
        }} />

        {/* Shimmer overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(105deg,transparent_35%,rgba(255,255,255,0.18)_48%,transparent_62%)] animate-[bg-drift-slow_18s_ease-in-out_infinite]" />

        {/* Giant Mascot Background */}
        <div className="absolute inset-0 flex items-center justify-center opacity-[0.035] text-slate-900 mix-blend-overlay pointer-events-none">
          <RandomMascot size={1000} />
        </div>
      </div>

      {/* Top Navigation */}
      <nav className="flex items-center justify-between px-6 py-4 relative z-10 w-full max-w-[1400px] mx-auto">
        <Logo />
        <div className="flex items-center gap-4">
          <Button
            variant="secondary"
            onClick={() => navigate(user ? '/chat' : '/agents')}
          >
            {user ? '开始对话' : '智能体商店'}
          </Button>
          {user ? (
            <Button
              variant="secondary"
              onClick={() => navigate('/agents')}
            >
              {user.name}
            </Button>
          ) : (
            <Button onClick={() => navigate('/login')}>
              登录
            </Button>
          )}
        </div>
      </nav>

      <a href="#main-content" className="skip-link">跳转到主要内容</a>

      {/* Hero Section */}
      <main id="main-content" className="flex-1 flex flex-col items-center justify-center px-4 relative z-10 w-full max-w-[1400px] mx-auto">
        <motion.h1 
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.6 }}
          className="text-5xl md:text-6xl font-extrabold text-slate-900 mb-6 flex items-center gap-4 tracking-tight"
        >
          一句话 
          <MascotSurprised size={56} className="text-slate-900 transform -rotate-6 drop-shadow-xl" />
          呈所想
        </motion.h1>
        <motion.p 
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.6 }}
          className="text-slate-600 mb-10 text-base md:text-lg font-medium tracking-wide"
        >
          与 AI 对话轻松创建应用和网站
        </motion.p>

        {/* Big Input Box */}
        <motion.div 
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.6 }}
          className="w-full max-w-3xl bg-white/60 backdrop-blur-2xl rounded-[2rem] shadow-lg shadow-brand-500/10 border border-white/60 p-3 transition-all focus-within:shadow-glow focus-within:bg-white/90 z-20"
        >
          <textarea
            className="w-full h-32 bg-transparent resize-none outline-none text-slate-800 placeholder:text-slate-400 text-lg p-4 leading-relaxed focus:outline-none"
            placeholder="输入你想聊的内容，例如：帮我写一段 Python 代码..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={4000}
            autoFocus
          />
          <div className="flex justify-between items-center px-4 pb-3">
            {user && agentProfiles.length > 0 ? (
              <AgentSelector
                agents={agentProfiles}
                selectedId={selectedAgentProfileId}
                onSelect={(agent) => setSelectedAgentProfileId(agent.id)}
                variant="full"
              />
            ) : (
              <div />
            )}
            
            <button
              onClick={handleSend}
              disabled={!inputValue.trim()}
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-all flex-shrink-0 group ${
                inputValue.trim()
                  ? 'bg-slate-900 hover:bg-slate-800 text-white shadow-md'
                  : 'bg-slate-200 text-slate-400'
              }`}
              aria-label="发送消息"
            >
              <SendIcon size={20} className="group-hover:-translate-y-1 group-hover:scale-110" />
            </button>
          </div>
        </motion.div>
      </main>
    </motion.div>
  );
};
