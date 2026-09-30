import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { Logo } from '../components/Logo';
import { RandomMascot } from '../components/ui/RandomMascot';
import { AuroraBackground } from '../components/backgrounds/AuroraBackground';
import { PasswordField } from '../components/auth/PasswordField';
import { Button } from '../components/shadcn/button';
import { Input } from '../components/shadcn/input';
import { Label } from '../components/shadcn/label';
import { Card, CardContent } from '../components/shadcn/card';
import { registerWithCode, sendVerificationCode } from '../services/authService';
import { cn } from '../lib/utils';

const EMAIL_SUFFIXES = [
  '@qq.com', '@163.com', '@126.com', '@gmail.com',
  '@outlook.com', '@hotmail.com', '@foxmail.com',
  '@yeah.net', '@sina.com', '@aliyun.com',
];

// 校验规则与旧手写逻辑等价：昵称必填 / 邮箱格式 / 密码 ≥6 / 验证码 6 位
const signupSchema = z.object({
  name: z.string().trim().min(1, '请输入昵称'),
  email: z
    .string()
    .trim()
    .min(1, '请输入邮箱地址')
    .regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/, '请输入有效的邮箱地址'),
  password: z.string().min(6, '密码至少 6 位'),
  code: z.string().length(6, '请输入 6 位验证码'),
});

type SignupFormValues = z.infer<typeof signupSchema>;

export const Signup = () => {
  const navigate = useNavigate();
  const [codeSent, setCodeSent] = useState(false);
  const [codeCountdown, setCodeCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestionIdx, setSelectedSuggestionIdx] = useState(-1);

  const emailRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { name: '', email: '', password: '', code: '' },
  });

  const email = watch('email');

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
      setError('email', { message: '请输入邮箱地址' });
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('email', { message: '请输入有效的邮箱地址' });
      return;
    }
    setIsSendingCode(true);
    try {
      await sendVerificationCode(email.trim(), 'register');
      setCodeSent(true);
      setCodeCountdown(60);
      toast.success('验证码已发送，请查收邮箱');
    } catch (err) {
      const message = err instanceof Error ? err.message : '发送验证码失败';
      toast.error(message);
    } finally {
      setIsSendingCode(false);
    }
  };

  const onSignup = handleSubmit(async (values) => {
    if (!codeSent) {
      setError('root', { message: '请先发送验证码' });
      return;
    }
    try {
      const user = await registerWithCode(values.name, values.email, values.password, values.code);
      navigate(user.role === 'admin' ? '/admin' : '/chat', { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : '注册失败';
      setError('root', { message });
      toast.error(message);
    }
  });

  const selectSuggestion = (value: string) => {
    setValue('email', value, { shouldValidate: false });
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
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      transition={{ duration: 0.3 }}
      className="relative min-h-screen overflow-hidden bg-zinc-50 flex items-center justify-center p-4"
    >
      <AuroraBackground className="fixed" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-zinc-900 opacity-[0.03]" />
      </div>

      <button
        onClick={() => navigate('/login')}
        className="fixed top-6 left-6 z-20 flex items-center gap-2 px-4 py-2 rounded-xl border border-zinc-200 bg-white/80 text-sm font-medium text-zinc-600 shadow-sm transition-all hover:border-zinc-300 hover:text-zinc-900 hover:shadow-md group"
        aria-label="返回登录"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:-translate-x-1"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回登录
      </button>

      <main id="main-content" className="w-full max-w-md relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="flex flex-col items-center mb-8">
            <div className="mb-5">
              <Logo iconSize={48} showText={false} />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">注册 AgenticOS</h1>
            <p className="mt-2 text-sm text-zinc-500">创建账号，开始你的智能协作</p>
          </div>

          <Card className="py-8 shadow-md">
            <CardContent className="px-8">
              <form className="space-y-5" onSubmit={onSignup} noValidate>
                <div className="space-y-2">
                  <Label htmlFor="signup-name">昵称</Label>
                  <Input
                    id="signup-name"
                    type="text"
                    autoComplete="name"
                    placeholder="请输入您的昵称"
                    aria-invalid={!!errors.name}
                    {...register('name')}
                  />
                  {errors.name && (
                    <p className="text-xs font-medium text-red-600" role="alert">{errors.name.message}</p>
                  )}
                </div>

                {/* 邮箱输入 + 补全 */}
                <div ref={emailRef} className="relative space-y-2">
                  <Label htmlFor="signup-email">邮箱地址</Label>
                  <Input
                    id="signup-email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    aria-invalid={!!errors.email}
                    {...register('email', {
                      onChange: () => {
                        setShowSuggestions(true);
                        setSelectedSuggestionIdx(-1);
                      },
                    })}
                    onFocus={() => setShowSuggestions(true)}
                    onKeyDown={handleEmailKeyDown}
                  />
                  {errors.email && (
                    <p className="text-xs font-medium text-red-600" role="alert">{errors.email.message}</p>
                  )}
                  <AnimatePresence>
                    {showSuggestions && suggestions.length > 0 && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-zinc-200 bg-popover shadow-lg overflow-hidden z-50"
                      >
                        {suggestions.map((s, i) => (
                          <button
                            key={s}
                            type="button"
                            onMouseDown={(e) => { e.preventDefault(); selectSuggestion(s); }}
                            className={cn(
                              'w-full px-4 py-2 text-left text-sm transition-colors',
                              i === selectedSuggestionIdx
                                ? 'bg-accent text-accent-foreground'
                                : 'text-zinc-600 hover:bg-zinc-50'
                            )}
                          >
                            <span className="text-zinc-400">{email}</span>
                            <span className="font-medium">{s.slice(email.length)}</span>
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="signup-password">密码</Label>
                  <PasswordField
                    id="signup-password"
                    placeholder="至少 6 位"
                    autoComplete="new-password"
                    aria-invalid={!!errors.password}
                    {...register('password')}
                  />
                  {errors.password && (
                    <p className="text-xs font-medium text-red-600" role="alert">{errors.password.message}</p>
                  )}
                </div>

                {/* 邮箱验证码 */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="signup-code">邮箱验证码</Label>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleSendCode}
                      disabled={codeCountdown > 0 || isSendingCode}
                      className="shrink-0"
                    >
                      {codeCountdown > 0 ? `${codeCountdown}s` : '发送验证码'}
                    </Button>
                  </div>
                  <Input
                    id="signup-code"
                    type="text"
                    inputMode="numeric"
                    placeholder="输入 6 位验证码"
                    maxLength={6}
                    aria-invalid={!!errors.code}
                    {...register('code', {
                      setValueAs: (v: string) => v.replace(/\D/g, '').slice(0, 6),
                    })}
                  />
                  {errors.code && (
                    <p className="text-xs font-medium text-red-600" role="alert">{errors.code.message}</p>
                  )}
                  {codeSent && !errors.code && (
                    <p className="text-xs font-medium text-emerald-600">验证码已发送到您的邮箱，请查收</p>
                  )}
                </div>

                {errors.root && (
                  <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                    {errors.root.message}
                  </div>
                )}

                <Button type="submit" disabled={isSubmitting} className="w-full h-11 text-sm">
                  {isSubmitting ? '正在注册...' : '注册账号'}
                </Button>
              </form>

              <div className="mt-8 text-center text-sm text-zinc-500">
                已有账号？ <a href="#" onClick={(e) => { e.preventDefault(); navigate('/login'); }} className="text-primary hover:text-primary/80 font-medium underline underline-offset-4">立即登录</a>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </main>
    </motion.div>
  );
};
