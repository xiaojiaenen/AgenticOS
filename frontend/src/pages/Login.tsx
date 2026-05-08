import React, { useState } from 'react';
import { motion } from 'motion/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { RandomMascot } from '../components/ui/RandomMascot';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { login as loginUser } from '../services/authService';

export const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
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
      <motion.button
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/')}
        className="fixed top-6 left-6 z-20 flex items-center gap-2 px-4 py-2 glass-medium border border-white/60 rounded-2xl shadow-sm text-slate-600 hover:text-zinc-900 hover:shadow-md transition-all group font-medium"
        aria-label="返回首页"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:-translate-x-1 transition-transform"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回首页
      </motion.button>

      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.03]" />
        <div className="absolute top-[-10%] left-[-10%] w-[60vw] h-[60vw] bg-teal-300 rounded-full mix-blend-overlay filter blur-[150px] opacity-40" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[60vw] h-[60vw] bg-blue-400 rounded-full mix-blend-overlay filter blur-[150px] opacity-40" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md bg-white/60 backdrop-blur-2xl rounded-[32px] shadow-xl shadow-brand-500/10 border border-white/60 p-10 relative z-10"
      >
        <div className="flex flex-col items-center mb-10">
          <div className="mb-6">
            <Logo iconSize={48} showText={false} />
          </div>
          <h2 className="text-3xl font-black text-slate-900 tracking-tight">欢迎回来</h2>
          <p className="text-slate-500 mt-2.5 text-sm font-medium">登录以继续使用 AgenticOS</p>
        </div>

        <form className="space-y-5" onSubmit={handleLogin}>
          <Input
            label="邮箱地址"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
            autoComplete="email"
          />
          <div>
            <div className="flex justify-between items-center mb-2 ml-1">
              <label className="text-xs font-black uppercase tracking-[0.2em] text-slate-400">密码</label>
              <span className="text-xs text-slate-400 font-bold">忘记密码请联系管理员</span>
            </div>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                autoComplete="current-password"
                className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 pr-12 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-brand-200 focus:bg-white focus:ring-4 focus:ring-brand-100/80"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 transition-colors"
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
              >
                {showPassword ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-3 text-sm font-medium text-rose-700">
              {error}
            </div>
          )}

          <Button variant="primary" type="submit" disabled={isSubmitting} className="w-full h-14 text-lg rounded-2xl mt-4">
            {isSubmitting ? 'Signing in...' : '进入工作台'}
          </Button>
        </form>

        <div className="mt-10 text-center text-sm text-slate-500 font-medium">
          还没有账号？ <a href="#" onClick={(e) => { e.preventDefault(); navigate('/signup'); }} className="text-brand-600 hover:text-brand-700 font-bold underline decoration-brand-200 underline-offset-4">立即注册</a>
        </div>
      </motion.div>
    </motion.div>
  );
};
