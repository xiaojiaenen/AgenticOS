import React, { useState } from 'react';
import { motion } from 'motion/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { RandomMascot } from '../components/ui/RandomMascot';
import { Button } from '../components/ui/Button';
import { login as loginUser } from '../services/authService';

export const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const user = await loginUser(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || (user.role === 'admin' ? '/admin' : '/chat'), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] relative flex items-center justify-center p-4 selection:bg-zinc-200 selection:text-zinc-900 overflow-hidden"
    >
      {/* 返回首页按钮 */}
      <motion.button
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/')}
        className="fixed top-6 left-6 z-20 flex items-center gap-2 px-4 py-2 bg-white/80 backdrop-blur-md border border-white rounded-2xl shadow-sm text-slate-600 hover:text-zinc-900 hover:shadow-md transition-all group font-medium"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:-translate-x-1 transition-transform"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回首页
      </motion.button>

      {/* 网格渐变背景 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        {/* 吉祥物阴影 */}
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.03]" />
        
        <div className="absolute top-[-10%] left-[-10%] w-[60vw] h-[60vw] bg-teal-300 rounded-full mix-blend-overlay filter blur-[150px] opacity-40"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[60vw] h-[60vw] bg-blue-400 rounded-full mix-blend-overlay filter blur-[150px] opacity-40"></div>
        {/* 颗粒噪点叠层 */}
        <div className="absolute inset-0 opacity-[0.04] mix-blend-overlay" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=%220 0 200 200%22 xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter id=%22noiseFilter%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.8%22 numOctaves=%223%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23noiseFilter)%22/%3E%3C/svg%3E")' }}></div>
      </div>

      <motion.div 
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md bg-white/60 backdrop-blur-2xl rounded-[40px] shadow-[0_32px_64px_-16px_rgba(56,189,248,0.2)] border border-white/60 p-10 relative z-10"
      >
        <div className="flex flex-col items-center mb-10">
          <div className="mb-6">
            <Logo iconSize={48} showText={false} />
          </div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">欢迎回来</h2>
          <p className="text-slate-500 mt-2.5 text-sm font-medium">登录以继续使用 AgenticOS</p>
        </div>

        <form className="space-y-6" onSubmit={handleLogin}>
          <div className="space-y-2">
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest ml-1">邮箱地址</label>
            <input 
              type="text" 
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full px-5 py-4 rounded-2xl bg-white/40 border border-white/60 focus:border-cyan-300 focus:ring-4 focus:ring-cyan-500/10 focus:bg-white/60 outline-none transition-all text-slate-800 placeholder:text-slate-400 font-medium"
            />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center ml-1">
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest">密码</label>
              <a href="#" className="text-xs text-zinc-600 hover:text-zinc-900 font-bold">忘记密码？</a>
            </div>
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full px-5 py-4 rounded-2xl bg-white/40 border border-white/60 focus:border-cyan-300 focus:ring-4 focus:ring-cyan-500/10 focus:bg-white/60 outline-none transition-all text-slate-800 placeholder:text-slate-400 font-medium"
            />
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-3 text-sm font-medium text-rose-700">
              {error}
            </div>
          )}

          <Button variant="primary" type="submit" disabled={isSubmitting} className="w-full h-14 text-lg rounded-2xl shadow-lg mt-4">
            {isSubmitting ? 'Signing in...' : '进入工作台'}
          </Button>
        </form>

        <div className="mt-10 text-center text-sm text-slate-500 font-medium">
          还没有账号？ <a href="#" onClick={(e) => { e.preventDefault(); navigate('/signup'); }} className="text-zinc-800 hover:text-zinc-900 font-bold underline decoration-zinc-300 underline-offset-4">立即注册</a>
        </div>
      </motion.div>
    </motion.div>
  );
};
