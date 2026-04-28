import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { Button } from '../components/ui/Button';
import { RandomMascot } from '../components/ui/RandomMascot';
import { MascotSurprised, MascotHappy, SendIcon, ChevronDownIcon, CodeIcon, GlobeIcon, PresentationIcon } from '../components/ui/AnimatedIcons';
import { cn } from '../lib/utils';

export const Home = () => {
  const [inputValue, setInputValue] = useState('');
  const [chatMode, setChatMode] = useState<'general' | 'ppt' | 'website'>('general');
  const [showModeMenu, setShowModeMenu] = useState(false);
  const modeMenuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Handle click outside to close menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(event.target as Node)) {
        setShowModeMenu(false);
      }
    };
    if (showModeMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showModeMenu]);

  const handleSend = () => {
    if (!inputValue.trim()) return;
    navigate('/chat', { state: { initialMessage: inputValue, mode: chatMode } });
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
      className="min-h-screen bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] relative overflow-hidden font-sans flex flex-col selection:bg-zinc-200 selection:text-zinc-900"
    >
      {/* Mesh Gradient Background with Noise and Giant Mascot */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute bottom-[-20%] left-[-10%] w-[70vw] h-[70vw] bg-teal-300 rounded-full mix-blend-overlay filter blur-[120px] opacity-40"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[80vw] h-[80vw] bg-blue-400 rounded-full mix-blend-overlay filter blur-[120px] opacity-40"></div>
        <div className="absolute top-[10%] left-[30%] w-[50vw] h-[50vw] bg-cyan-300 rounded-full mix-blend-overlay filter blur-[120px] opacity-30"></div>
        
        {/* Giant Mascot Background */}
        <div className="absolute inset-0 flex items-center justify-center opacity-[0.03] text-slate-900 mix-blend-overlay pointer-events-none">
          <RandomMascot size={1000} />
        </div>

        {/* Noise Overlay */}
        <div className="absolute inset-0 opacity-[0.04] mix-blend-overlay" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noiseFilter%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.8%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noiseFilter)%22/%3E%3C/svg%3E")' }}></div>
      </div>

      {/* Top Navigation */}
      <nav className="flex items-center justify-between px-6 py-4 relative z-10 w-full max-w-[1400px] mx-auto">
        <Logo />
        <div className="flex items-center gap-4">
          <Button
            variant="secondary"
            onClick={() => navigate('/agents')}
          >
            智能体商店
          </Button>
          <Button 
            onClick={() => navigate('/login')}
          >
            登录
          </Button>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 relative z-10 w-full max-w-[1400px] mx-auto">
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
          className="w-full max-w-3xl bg-white/60 backdrop-blur-2xl rounded-[32px] shadow-[0_8px_30px_rgba(50,150,250,0.1)] border border-white/60 p-3 transition-all focus-within:shadow-[0_12px_40px_rgba(56,189,248,0.2)] focus-within:bg-white/90 z-20"
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
            <div className="relative" ref={modeMenuRef}>
              <button 
                onClick={() => setShowModeMenu(!showModeMenu)}
                className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-2xl text-sm font-bold transition-all active:scale-95 border border-slate-200/50"
              >
                <div className={cn("w-6 h-6 rounded-lg flex items-center justify-center transition-all shadow-sm", 
                  chatMode === 'general' ? "bg-slate-200" : "bg-sky-500 text-white shadow-[0_0_12px_rgba(14,165,233,0.4)]")}>
                  {chatMode === 'general' ? <MascotHappy size={14} /> : chatMode === 'ppt' ? <PresentationIcon size={14} /> : <GlobeIcon size={14} />}
                </div>
                {chatMode === 'general' ? '普通聊天' : chatMode === 'ppt' ? 'PPT 模式' : '网站模式'}
                <ChevronDownIcon size={14} className={cn("transition-transform", showModeMenu && "rotate-180")} />
              </button>

              <AnimatePresence>
                {showModeMenu && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 10 }}
                    className="absolute bottom-full left-0 mb-2 w-48 bg-white/90 backdrop-blur-xl border border-slate-200 rounded-3xl shadow-2xl z-40 p-2 overflow-hidden"
                  >
                      {[
                        { id: 'general', label: '普通聊天', icon: <MascotHappy size={20} />, desc: '日常问题与对话' },
                        { id: 'ppt', label: 'PPT 模式', icon: <PresentationIcon size={20} />, desc: '大纲与演示文稿' },
                        { id: 'website', label: '网站模式', icon: <GlobeIcon size={20} />, desc: '生成网页与应用' }
                      ].map((mode) => (
                        <button
                          key={mode.id}
                          onClick={() => {
                            setChatMode(mode.id as any);
                            setShowModeMenu(false);
                          }}
                          className={cn(
                            "w-full flex flex-col items-start p-3 rounded-2xl transition-all hover:bg-slate-50 text-left group",
                            chatMode === mode.id ? "bg-slate-100 ring-1 ring-slate-200" : ""
                          )}
                        >
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className={cn(chatMode === mode.id ? "text-sky-600" : "text-slate-400 group-hover:text-slate-600")}>
                              {mode.icon}
                            </span>
                            <span className="font-bold text-slate-800 text-sm">{mode.label}</span>
                          </div>
                          <span className="text-[10px] text-slate-400 font-medium px-6">{mode.desc}</span>
                        </button>
                      ))}
                    </motion.div>
                )}
              </AnimatePresence>
            </div>
            
            <button
              onClick={handleSend}
              disabled={!inputValue.trim()}
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-all flex-shrink-0 group ${
                inputValue.trim()
                  ? 'bg-slate-900 hover:bg-slate-800 text-white shadow-md'
                  : 'bg-slate-200 text-white'
              }`}
            >
              <SendIcon size={20} className="group-hover:-translate-y-1 group-hover:scale-110" />
            </button>
          </div>
        </motion.div>
      </main>
    </motion.div>
  );
};
