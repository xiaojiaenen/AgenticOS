import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { Button } from '../components/ui/Button';
import { RandomMascot } from '../components/ui/RandomMascot';
import { MascotSurprised, MascotHappy, SendIcon, ChevronDownIcon } from '../components/ui/AnimatedIcons';
import { cn } from '../lib/utils';
import { getStoredUser } from '../services/authService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';

export const Home = () => {
  const [inputValue, setInputValue] = useState('');
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [menuFocusIndex, setMenuFocusIndex] = useState(-1);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuItemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const navigate = useNavigate();
  const user = getStoredUser();

  const selectedAgent = agentProfiles.find((a) => a.id === selectedAgentProfileId) || null;
  const selectableAgents = agentProfiles;

  useEffect(() => {
    if (user) {
      getMyAgents()
        .then((res) => {
          setAgentProfiles(res.items);
          const general = res.items.find((a) => a.slug === 'general');
          if (general) setSelectedAgentProfileId(general.id);
        })
        .catch(() => {});
    }
  }, []);

  // Handle click outside to close menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMenu]);

  const handleMenuKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setMenuFocusIndex((prev) => (prev + 1) % selectableAgents.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setMenuFocusIndex((prev) => (prev - 1 + selectableAgents.length) % selectableAgents.length);
    } else if (e.key === 'Enter' && menuFocusIndex >= 0) {
      e.preventDefault();
      const agent = selectableAgents[menuFocusIndex];
      if (agent) {
        setSelectedAgentProfileId(agent.id);
        setShowMenu(false);
        setMenuFocusIndex(-1);
      }
    } else if (e.key === 'Escape') {
      setShowMenu(false);
      setMenuFocusIndex(-1);
    }
  };

  // Focus the active menu item when focus index changes
  useEffect(() => {
    if (showMenu && menuFocusIndex >= 0 && menuItemRefs.current[menuFocusIndex]) {
      menuItemRefs.current[menuFocusIndex]?.focus();
    }
  }, [menuFocusIndex, showMenu]);

  // Reset focus index when menu opens/closes
  useEffect(() => {
    if (!showMenu) setMenuFocusIndex(-1);
  }, [showMenu]);

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
      className="min-h-screen bg-gradient-to-br from-[#e0fbfc] via-[#cffafe] to-[#7dd3fc] relative overflow-hidden font-sans flex flex-col selection:bg-zinc-200 selection:text-zinc-900"
    >
      {/* Mesh Gradient Background with Noise and Giant Mascot */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[60vw] h-[60vw] bg-sky-200 rounded-full mix-blend-overlay filter blur-[80px] opacity-25"></div>

        {/* Giant Mascot Background */}
        <div className="absolute inset-0 flex items-center justify-center opacity-[0.03] text-slate-900 mix-blend-overlay pointer-events-none">
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
              onClick={() => navigate('/chat')}
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
            className="w-full h-32 bg-transparent resize-none outline-none text-slate-800 placeholder:text-slate-400 text-lg p-4 leading-relaxed"
            placeholder="输入你想聊的内容，例如：帮我写一段 Python 代码..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
          />
          <div className="flex justify-between items-center px-4 pb-3">
            {user && selectableAgents.length > 0 ? (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setShowMenu(!showMenu)}
                className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-2xl text-sm font-bold transition-all active:scale-95 border border-slate-200/50"
                aria-label="选择智能体"
              >
                <div className={cn("w-6 h-6 rounded-lg flex items-center justify-center transition-all shadow-sm",
                  selectedAgentProfileId ? "bg-sky-500 text-white shadow-glow" : "bg-slate-200")}>
                  <MascotHappy size={14} />
                </div>
                {selectedAgent?.name || '选择智能体'}
                <ChevronDownIcon size={14} className={cn("transition-transform", showMenu && "rotate-180")} />
              </button>

              <AnimatePresence>
                {showMenu && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 10 }}
                    className="absolute bottom-full left-0 mb-2 max-h-64 w-56 overflow-y-auto bg-white/95 backdrop-blur-xl border border-slate-200/50 rounded-3xl shadow-2xl z-40 p-2"
                    onKeyDown={handleMenuKeyDown}
                  >
                    {selectableAgents.map((agent, idx) => (
                      <button
                        key={agent.id}
                        ref={(el) => { menuItemRefs.current[idx] = el; }}
                        onClick={() => {
                          setSelectedAgentProfileId(agent.id);
                          setShowMenu(false);
                        }}
                        className={cn(
                          'mb-1 flex w-full items-center gap-3 rounded-2xl p-2.5 text-left transition-all last:mb-0 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60',
                          selectedAgentProfileId === agent.id ? 'bg-sky-50/70 ring-1 ring-sky-100' : '',
                        )}
                      >
                        <span className={cn('flex h-8 w-8 items-center justify-center rounded-xl text-sm shadow-sm transition-transform',
                          selectedAgentProfileId === agent.id ? 'bg-sky-500 text-white' : 'bg-slate-100 text-slate-500')}>
                          <MascotHappy size={20} />
                        </span>
                        <div className="min-w-0 flex flex-col">
                          <span className={cn('truncate text-xs font-bold transition-colors', selectedAgentProfileId === agent.id ? 'text-sky-700' : 'text-slate-700')}>{agent.name}</span>
                          <span className="truncate text-[9px] font-medium text-slate-400">{agent.description || '智能体'}</span>
                        </div>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            ) : (
              <div />
            )}
            
            <button
              onClick={handleSend}
              disabled={!inputValue.trim()}
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-all flex-shrink-0 group ${
                inputValue.trim()
                  ? 'bg-slate-900 hover:bg-slate-800 text-white shadow-md'
                  : 'bg-slate-200 text-white'
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
