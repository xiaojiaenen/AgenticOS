import React, { useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { RandomMascot } from '../components/ui/RandomMascot';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { PasswordInput } from '../components/ui/PasswordInput';
import { register as registerUser } from '../services/authService';

export const Signup = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const user = await registerUser(name, email, password);
      navigate(user.role === 'admin' ? '/admin' : '/chat', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="min-h-screen bg-gradient-to-br from-[#dbeafe] via-[#bae6fd] to-[#38bdf8] relative flex items-center justify-center p-4 selection:bg-zinc-200 selection:text-zinc-900 overflow-hidden"
    >
      <motion.button
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/login')}
        className="fixed top-6 left-6 z-20 flex items-center gap-2 px-4 py-2 glass-medium border border-white/60 rounded-2xl shadow-sm text-slate-600 hover:text-zinc-900 hover:shadow-md transition-all group font-medium"
        aria-label="返回登录"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:-translate-x-1 transition-transform"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回登录
      </motion.button>

      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        {/* Animated ambient blobs */}
        <div className="absolute -top-20 -left-12 w-[50vw] h-[50vw] rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.20),transparent_70%)] blur-[70px] animate-[bg-blob-2_15s_ease-in-out_infinite]" />
        <div className="absolute -bottom-16 -right-10 w-[48vw] h-[48vw] rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.18),transparent_70%)] blur-[70px] animate-[bg-blob-4_17s_ease-in-out_infinite]" />
        <div className="absolute top-1/2 left-1/5 w-[38vw] h-[38vw] rounded-full bg-[radial-gradient(circle,rgba(6,182,212,0.15),transparent_70%)] blur-[80px] animate-[bg-blob-1_14s_ease-in-out_infinite]" />
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.03]" />
      </div>

      <main id="main-content" className="w-full max-w-md relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="w-full bg-[var(--surface-2)] backdrop-blur-2xl rounded-[2rem] shadow-xl shadow-brand-500/10 border border-white/60 p-10"
        >
          <div className="flex flex-col items-center mb-10">
            <div className="mb-6">
              <Logo iconSize={48} showText={false} />
            </div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">注册 AgenticOS</h1>
            <p className="text-slate-500 mt-2.5 text-sm font-medium">创建账号，开始你的智能协作</p>
          </div>

        <form className="space-y-5" onSubmit={handleSignup}>
          <Input
            label="昵称"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="请输入您的昵称"
            required
            autoComplete="name"
          />
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
  <label className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.15em] text-slate-500">密码</label>
  <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 6 位" minLength={6} autoComplete="new-password" />
</div>

          {error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-3 text-sm font-medium text-rose-700">
              {error}
            </div>
          )}

          <Button variant="primary" type="submit" disabled={isSubmitting} className="w-full h-14 text-lg rounded-2xl mt-4">
            {isSubmitting ? '正在注册...' : '注册账号'}
          </Button>
        </form>

        <div className="mt-10 text-center text-sm text-slate-500 font-medium">
          已有账号？ <a href="#" onClick={(e) => { e.preventDefault(); navigate('/login'); }} className="text-brand-600 hover:text-brand-700 font-bold underline decoration-brand-200 underline-offset-4">立即登录</a>
        </div>
      </motion.div>
      </main>
    </motion.div>
  );
};
