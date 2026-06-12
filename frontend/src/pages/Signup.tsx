import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { RandomMascot } from '../components/ui/RandomMascot';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { PasswordInput } from '../components/ui/PasswordInput';
import { registerWithCode, sendVerificationCode } from '../services/authService';
import { useIsGlassTheme } from '../components/liquid-glass';
import { cn } from '../lib/utils';

const EMAIL_SUFFIXES = [
  '@qq.com', '@163.com', '@126.com', '@gmail.com',
  '@outlook.com', '@hotmail.com', '@foxmail.com',
  '@yeah.net', '@sina.com', '@aliyun.com',
];

export const Signup = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [codeCountdown, setCodeCountdown] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestionIdx, setSelectedSuggestionIdx] = useState(-1);

  const isGlass = useIsGlassTheme();

  const emailRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 邮箱后缀补全
  const getEmailSuggestions = useCallback(() => {
    if (!email || email.includes('@')) return [];
    return EMAIL_SUFFIXES.map((suffix) => email + suffix);
  }, [email]);

  // 点击外部关闭建议
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (emailRef.current && !emailRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 倒计时
  useEffect(() => {
    if (codeCountdown > 0) {
      countdownRef.current = setInterval(() => {
        setCodeCountdown((prev) => {
          if (prev <= 1) {
            if (countdownRef.current) clearInterval(countdownRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [codeCountdown]);

  const handleSendCode = async () => {
    if (!email.trim()) {
      setError('请输入邮箱地址');
      return;
    }
    setError(null);
    try {
      await sendVerificationCode(email, 'register');
      setCodeSent(true);
      setCodeCountdown(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送验证码失败');
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    if (!codeSent) {
      setError('请先发送验证码');
      return;
    }
    if (code.length !== 6) {
      setError('请输入 6 位验证码');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const user = await registerWithCode(name, email, password, code);
      navigate(user.role === 'admin' ? '/admin' : '/chat', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectSuggestion = (value: string) => {
    setEmail(value);
    setShowSuggestions(false);
    setSelectedSuggestionIdx(-1);
  };

  const handleEmailKeyDown = (e: React.KeyboardEvent) => {
    const suggestions = getEmailSuggestions();
    if (!showSuggestions || suggestions.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedSuggestionIdx((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedSuggestionIdx((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter' && selectedSuggestionIdx >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[selectedSuggestionIdx]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  const suggestions = getEmailSuggestions();

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'min-h-screen relative flex items-center justify-center p-4 overflow-hidden',
        isGlass
          ? 'selection:bg-sky-200/60 selection:text-sky-900'
          : 'bg-gradient-to-br from-[#dbeafe] via-[#bae6fd] to-[#38bdf8] selection:bg-zinc-200 selection:text-zinc-900'
      )}
      style={isGlass ? { background: 'linear-gradient(180deg, #d9edf4 0%, #e3f2f8 28%, #dceff5 55%, #dff0f5 100%)' } : undefined}
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
          className={cn(
            'w-full backdrop-blur-2xl rounded-[2rem] shadow-xl p-10',
            isGlass
              ? 'bg-white/8 border border-white/15 shadow-brand-500/5'
              : 'bg-[var(--surface-2)] border border-white/60 shadow-brand-500/10'
          )}
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

            {/* 邮箱输入 + 补全 */}
            <div ref={emailRef} className="relative">
              <Input
                label="邮箱地址"
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setShowSuggestions(true);
                  setSelectedSuggestionIdx(-1);
                }}
                onFocus={() => setShowSuggestions(true)}
                onKeyDown={handleEmailKeyDown}
                placeholder="you@example.com"
                required
                autoComplete="email"
              />
              {/* 邮箱后缀建议 */}
              <AnimatePresence>
                {showSuggestions && suggestions.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className={cn(
                      'absolute left-0 right-0 top-full mt-1 rounded-xl overflow-hidden z-50',
                      isGlass
                        ? 'bg-white/10 border-white/20 backdrop-blur-xl border shadow-lg'
                        : 'bg-white border border-slate-200 shadow-lg'
                    )}
                  >
                    {suggestions.map((s, i) => (
                      <button
                        key={s}
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); selectSuggestion(s); }}
                        className={`w-full px-4 py-2.5 text-left text-sm transition-colors ${
                          i === selectedSuggestionIdx
                            ? 'bg-sky-50 text-sky-700'
                            : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <span className="text-slate-400">{email}</span>
                        <span className="font-medium">{s.slice(email.length)}</span>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <div>
              <label htmlFor="signup-password" className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.15em] text-slate-500">密码</label>
              <PasswordInput id="signup-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 6 位" minLength={6} autoComplete="new-password" />
            </div>

            {/* 邮箱验证码（必填） */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold uppercase tracking-[0.15em] text-slate-500 ml-1">
                  邮箱验证码
                </label>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleSendCode}
                  disabled={codeCountdown > 0}
                  className="shrink-0 px-3 py-1 text-xs"
                >
                  {codeCountdown > 0 ? `${codeCountdown}s` : '发送验证码'}
                </Button>
              </div>
              <Input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="输入 6 位验证码"
                maxLength={6}
                required
              />
              {codeSent && (
                <p className="text-xs text-emerald-600 font-medium">验证码已发送到您的邮箱，请查收</p>
              )}
            </div>

            {error && (
              <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-3 text-sm font-medium text-rose-700">
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
