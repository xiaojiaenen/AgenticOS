import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { RandomMascot } from '../components/ui/RandomMascot';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { PasswordInput } from '../components/ui/PasswordInput';
import { login as loginUser, loginWithCode, sendVerificationCode } from '../services/authService';
import { useIsGlassTheme } from '../components/liquid-glass';
import { Ferrofluid, LightRays } from '../components/liquid-glass';
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';
import { cn } from '../lib/utils';

const EMAIL_SUFFIXES = [
  '@qq.com', '@163.com', '@126.com', '@gmail.com',
  '@outlook.com', '@hotmail.com', '@foxmail.com',
  '@yeah.net', '@sina.com', '@aliyun.com',
];

export const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const isGlass = useIsGlassTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loginMode, setLoginMode] = useState<'password' | 'code'>('password');
  const [codeSent, setCodeSent] = useState(false);
  const [codeCountdown, setCodeCountdown] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestionIdx, setSelectedSuggestionIdx] = useState(-1);

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
      await sendVerificationCode(email, 'login');
      setCodeSent(true);
      setCodeCountdown(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送验证码失败');
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      let user;
      if (loginMode === 'password') {
        user = await loginUser(email, password);
      } else {
        if (!codeSent) {
          setError('请先发送验证码');
          setIsSubmitting(false);
          return;
        }
        user = await loginWithCode(email, code);
      }
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || (user.role === 'admin' ? '/admin' : '/chat'), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
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
        "min-h-screen relative flex items-center justify-center p-4 overflow-hidden",
        isGlass ? "text-white selection:bg-sky-200/60 selection:text-sky-900" : "selection:bg-zinc-200 selection:text-zinc-900"
      )}
      style={{
        background: isGlass ? '#000000' : 'linear-gradient(180deg, #def0f6 0%, #e7f4f9 28%, #e1f2f7 55%, #e3f2f7 100%)',
      }}
    >
      {isGlass ? (
        <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
          <Ferrofluid
            colors={['#1a1a2e', '#16213e', '#0f3460']}
            speed={0.3} scale={1.2} turbulence={0.8} fluidity={0.15}
            rimWidth={0.15} sharpness={2} shimmer={1} glow={1.5}
            flowDirection="down" opacity={0.6}
            mouseInteraction={true} mouseStrength={0.8}
            mouseRadius={0.3} mouseDampening={0.2}
          />
          <LightRays
            raysOrigin="top-center"
            raysColor="#4a9eff"
            raysSpeed={0.6}
            lightSpread={1.5}
            rayLength={3}
            fadeDistance={1.5}
            saturation={0.6}
            followMouse={true}
            mouseInfluence={0.12}
          />
        </div>
      ) : (
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute -top-24 -left-16 w-[55vw] h-[55vw] rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.22),transparent_70%)] blur-[70px] animate-[bg-blob-1_12s_ease-in-out_infinite]" />
        <div className="absolute -bottom-20 -right-12 w-[50vw] h-[50vw] rounded-full bg-[radial-gradient(circle,rgba(6,182,212,0.19),transparent_70%)] blur-[70px] animate-[bg-blob-2_14s_ease-in-out_infinite]" />
        <div className="absolute top-1/3 left-1/4 w-[40vw] h-[40vw] rounded-full bg-[radial-gradient(circle,rgba(34,211,238,0.16),transparent_70%)] blur-[80px] animate-[bg-blob-3_13s_ease-in-out_infinite]" />
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.03]" />
      </div>
      )}
      <motion.button
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate('/')}
        className={cn("fixed top-6 left-6 z-20 flex items-center gap-2 px-4 py-2 rounded-2xl shadow-sm font-medium transition-all group", isGlass ? "bg-white/10 border border-white/15 text-white/70 hover:text-white hover:bg-white/15" : "glass-medium border border-white/60 text-slate-600 hover:text-zinc-900 hover:shadow-md")}
        aria-label="返回首页"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:-translate-x-1 transition-transform"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回首页
      </motion.button>

      <main id="main-content" className="w-full max-w-md relative z-10">
        {(() => {
          const formPanel = (
            <>
              <div className="flex flex-col items-center mb-10">
                <div className="mb-6">
                  <Logo iconSize={48} showText={false} />
                </div>
                <h1 className={cn("text-3xl font-black tracking-tight", isGlass ? "text-white" : "text-slate-900")}>登录 AgenticOS</h1>
                <p className={cn("mt-2.5 text-sm font-medium", isGlass ? "text-white/50" : "text-slate-500")}>欢迎回来，登录以继续使用</p>
              </div>

            {/* 登录模式切换 */}
            <div className={cn("flex rounded-xl p-1 mb-6", isGlass ? "bg-white/8" : "bg-slate-100/80")}>
              <button
                type="button"
                onClick={() => { setLoginMode('password'); setError(null); }}
                className={cn(
                  "flex-1 py-2 text-sm font-semibold rounded-lg transition-all",
                  loginMode === 'password'
                    ? isGlass ? 'bg-white/15 text-white shadow-sm' : 'bg-white text-slate-900 shadow-sm'
                    : isGlass ? 'text-white/50 hover:text-white' : 'text-slate-500 hover:text-slate-700'
                )}
              >
                密码登录
              </button>
              <button
                type="button"
                onClick={() => { setLoginMode('code'); setError(null); }}
                className={cn(
                  "flex-1 py-2 text-sm font-semibold rounded-lg transition-all",
                  loginMode === 'code'
                    ? isGlass ? 'bg-white/15 text-white shadow-sm' : 'bg-white text-slate-900 shadow-sm'
                    : isGlass ? 'text-white/50 hover:text-white' : 'text-slate-500 hover:text-slate-700'
                )}
              >
                验证码登录
              </button>
            </div>

            <form className="space-y-5" onSubmit={handleLogin}>
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
                        "absolute left-0 right-0 top-full mt-1 rounded-xl border shadow-lg overflow-hidden z-50 backdrop-blur-xl",
                        isGlass ? "bg-white/10 border-white/20" : "bg-white border-slate-200"
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
                              : isGlass ? 'text-white/70 hover:bg-white/10' : 'text-slate-600 hover:bg-slate-50'
                          }`}
                        >
                          <span className={isGlass ? "text-white/40" : "text-slate-400"}>{email}</span>
                          <span className="font-medium">{s.slice(email.length)}</span>
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* 密码模式 */}
              <AnimatePresence mode="wait">
                {loginMode === 'password' && (
                  <motion.div
                    key="password"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <div className="flex justify-between items-center mb-2 ml-1">
                      <label htmlFor="login-password" className={cn("text-xs font-bold uppercase tracking-[0.15em]", isGlass ? "text-white/50" : "text-slate-500")}>密码</label>
                      <span className={cn("text-xs font-bold", isGlass ? "text-white/40" : "text-slate-400")}>忘记密码请联系管理员</span>
                    </div>
                    <PasswordInput id="login-password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
                  </motion.div>
                )}

                {/* 验证码模式 */}
                {loginMode === 'code' && (
                  <motion.div
                    key="code"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-3"
                  >
                    <div>
                      <label className={cn("text-xs font-bold uppercase tracking-[0.15em] mb-2 block ml-1", isGlass ? "text-white/50" : "text-slate-500")}>验证码</label>
                      <div className="flex gap-2">
                        <Input
                          type="text"
                          value={code}
                          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                          placeholder="输入 6 位验证码"
                          maxLength={6}
                          className="flex-1"
                          required={loginMode === 'code'}
                        />
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={handleSendCode}
                          disabled={codeCountdown > 0}
                          className="shrink-0 px-4 whitespace-nowrap"
                        >
                          {codeCountdown > 0 ? `${codeCountdown}s` : '发送验证码'}
                        </Button>
                      </div>
                    </div>
                    {codeSent && (
                      <p className="text-xs text-emerald-600 font-medium">验证码已发送到您的邮箱，请查收</p>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {error && (
                <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-3 text-sm font-medium text-rose-700">
                  {error}
                </div>
              )}

              <Button variant="primary" type="submit" disabled={isSubmitting} className="w-full h-14 text-lg rounded-2xl mt-4">
                {isSubmitting ? '正在登录...' : '进入工作台'}
              </Button>
            </form>

            <div className={cn("mt-10 text-center text-sm font-medium", isGlass ? "text-white/50" : "text-slate-500")}>
              还没有账号？ <a href="#" onClick={(e) => { e.preventDefault(); navigate('/signup'); }} className="text-brand-600 hover:text-brand-700 font-bold underline decoration-brand-200 underline-offset-4">立即注册</a>
            </div>
            </>          // close formPanel Fragment
          );
          return (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className={cn("w-full", isGlass ? "" : "backdrop-blur-2xl rounded-[2rem] shadow-xl p-10 bg-[var(--surface-2)] border border-white/60 shadow-brand-500/10")}
            >
              {isGlass ? (
                <LiquidGlass
                  {...glassPresets.card}
                  tint="rgba(255,255,255,0.08)"
                  radius={32}
                  style={{ width: '100%', padding: '40px' }}
                >
                  {formPanel}
                </LiquidGlass>
              ) : (
                <div className="w-full">{formPanel}</div>
              )}
            </motion.div>
          );
        })()}
      </main>
    </motion.div>
  );
};
