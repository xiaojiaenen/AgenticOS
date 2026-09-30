import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { AnimatePresence } from 'motion/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
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
import {
  login as loginUser,
  loginWithCode,
  sendVerificationCode,
} from '../services/authService';
import { cn } from '../lib/utils';

const EMAIL_SUFFIXES = [
  '@qq.com', '@163.com', '@126.com', '@gmail.com',
  '@outlook.com', '@hotmail.com', '@foxmail.com',
  '@yeah.net', '@sina.com', '@aliyun.com',
];

// 与后端 authService 请求字段对齐；校验规则与旧手写逻辑等价
const EMAIL_FIELD = z
  .string()
  .trim()
  .min(1, '请输入邮箱地址')
  .regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/, '请输入有效的邮箱地址');

type LoginMode = 'password' | 'code';

interface LoginFormValues {
  email: string;
  password: string;
  code: string;
}

export const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [loginMode, setLoginMode] = useState<LoginMode>('password');
  const [codeSent, setCodeSent] = useState(false);
  const [codeCountdown, setCodeCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestionIdx, setSelectedSuggestionIdx] = useState(-1);

  const emailRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const modeRef = useRef<LoginMode>(loginMode);
  modeRef.current = loginMode;

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    trigger,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    defaultValues: { email: '', password: '', code: '' },
  });

  const email = watch('email');

  // 模式切换时清掉另一种模式的校验错误
  useEffect(() => {
    clearErrors();
  }, [loginMode, clearErrors]);

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
    const emailValid = await trigger('email');
    if (!emailValid) return;
    setIsSendingCode(true);
    try {
      await sendVerificationCode(email.trim(), 'login');
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

  const zodSchema = useMemo(
    () =>
      z
        .object({
          email: EMAIL_FIELD,
          password: z.string(),
          code: z.string(),
        })
        .superRefine((v, ctx) => {
          if (modeRef.current === 'password') {
            if (!v.password) {
              ctx.addIssue({ code: 'custom', path: ['password'], message: '请输入密码' });
            } else if (v.password.length < 6) {
              ctx.addIssue({ code: 'custom', path: ['password'], message: '密码至少 6 位' });
            }
          } else if (v.code.length !== 6) {
            ctx.addIssue({ code: 'custom', path: ['code'], message: '请输入 6 位验证码' });
          }
        }),
    [],
  );

  const onLogin = handleSubmit(async (values) => {
    if (loginMode === 'code' && !codeSent) {
      setError('root', { message: '请先发送验证码' });
      return;
    }
    const parsed = zodSchema.safeParse(values);
    if (!parsed.success) {
      const flat = parsed.error.flatten().fieldErrors;
      if (flat.password?.[0]) setError('password', { message: flat.password[0] });
      if (flat.code?.[0]) setError('code', { message: flat.code[0] });
      return;
    }
    try {
      const user =
        loginMode === 'password'
          ? await loginUser(parsed.data.email, parsed.data.password)
          : await loginWithCode(parsed.data.email, parsed.data.code);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || (user.role === 'admin' ? '/admin' : '/chat'), { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : '登录失败';
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
        onClick={() => navigate('/')}
        className="fixed top-6 left-6 z-20 flex items-center gap-2 px-4 py-2 rounded-xl border border-zinc-200 bg-white/80 text-sm font-medium text-zinc-600 shadow-sm transition-all hover:border-zinc-300 hover:text-zinc-900 hover:shadow-md group"
        aria-label="返回首页"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:-translate-x-1"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回首页
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
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">登录 AgenticOS</h1>
            <p className="mt-2 text-sm text-zinc-500">欢迎回来，登录以继续使用</p>
          </div>

          <Card className="py-8 shadow-md">
            <CardContent className="px-8">
              {/* 登录模式切换 */}
              <div className="flex rounded-lg p-1 mb-6 bg-zinc-100">
                <button
                  type="button"
                  onClick={() => setLoginMode('password')}
                  className={cn(
                    'flex-1 py-1.5 text-sm font-medium rounded-md transition-all',
                    loginMode === 'password'
                      ? 'bg-white text-zinc-900 shadow-sm'
                      : 'text-zinc-500 hover:text-zinc-700'
                  )}
                >
                  密码登录
                </button>
                <button
                  type="button"
                  onClick={() => setLoginMode('code')}
                  className={cn(
                    'flex-1 py-1.5 text-sm font-medium rounded-md transition-all',
                    loginMode === 'code'
                      ? 'bg-white text-zinc-900 shadow-sm'
                      : 'text-zinc-500 hover:text-zinc-700'
                  )}
                >
                  验证码登录
                </button>
              </div>

              <form className="space-y-5" onSubmit={onLogin} noValidate>
                {/* 邮箱输入 + 补全 */}
                <div ref={emailRef} className="relative space-y-2">
                  <Label htmlFor="login-email">邮箱地址</Label>
                  <Input
                    id="login-email"
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
                  {/* 邮箱后缀建议 */}
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

                {/* 密码模式 */}
                {loginMode === 'password' && (
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <Label htmlFor="login-password">密码</Label>
                      <span className="text-xs text-zinc-400">忘记密码请联系管理员</span>
                    </div>
                    <PasswordField
                      id="login-password"
                      placeholder="••••••••"
                      autoComplete="current-password"
                      aria-invalid={!!errors.password}
                      {...register('password')}
                    />
                    {errors.password && (
                      <p className="text-xs font-medium text-red-600" role="alert">{errors.password.message}</p>
                    )}
                  </div>
                )}

                {/* 验证码模式 */}
                {loginMode === 'code' && (
                  <div className="space-y-2">
                    <Label htmlFor="login-code">验证码</Label>
                    <div className="flex gap-2">
                      <Input
                        id="login-code"
                        type="text"
                        inputMode="numeric"
                        placeholder="输入 6 位验证码"
                        maxLength={6}
                        className="flex-1"
                        aria-invalid={!!errors.code}
                        {...register('code', {
                          setValueAs: (v: string) => v.replace(/\D/g, '').slice(0, 6),
                        })}
                      />
                      <Button
                        type="button"
                        variant="outline"
                        onClick={handleSendCode}
                        disabled={codeCountdown > 0 || isSendingCode}
                        className="shrink-0 whitespace-nowrap"
                      >
                        {codeCountdown > 0 ? `${codeCountdown}s` : '发送验证码'}
                      </Button>
                    </div>
                    {errors.code && (
                      <p className="text-xs font-medium text-red-600" role="alert">{errors.code.message}</p>
                    )}
                    {codeSent && !errors.code && (
                      <p className="text-xs font-medium text-emerald-600">验证码已发送到您的邮箱，请查收</p>
                    )}
                  </div>
                )}

                {errors.root && (
                  <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                    {errors.root.message}
                  </div>
                )}

                <Button type="submit" disabled={isSubmitting} className="w-full h-11 text-sm">
                  {isSubmitting ? '正在登录...' : '进入工作台'}
                </Button>
              </form>

              <div className="mt-8 text-center text-sm text-zinc-500">
                还没有账号？ <a href="#" onClick={(e) => { e.preventDefault(); navigate('/signup'); }} className="text-primary hover:text-primary/80 font-medium underline underline-offset-4">立即注册</a>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </main>
    </motion.div>
  );
};
