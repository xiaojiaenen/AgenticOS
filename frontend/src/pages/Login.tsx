import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { AnimatePresence } from 'motion/react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { toast } from 'sonner';
import { apiFetch } from '../services/apiClient';
import { Logo } from '../components/Logo';
import { PasswordField } from '../components/auth/PasswordField';
import { AuthShell } from '../components/auth/AuthShell';
import { Button } from '../components/shadcn/button';
import { Input } from '../components/shadcn/input';
import { Label } from '../components/shadcn/label';
import { Card, CardContent } from '../components/shadcn/card';
import {
  login as loginUser,
  loginWithCode,
  sendVerificationCode,
} from '../services/authService';
import { canEnterAdmin } from '../services/authTokenStore';
import { cn } from '../lib/utils';

const EMAIL_SUFFIXES = [
  '@qq.com', '@163.com', '@126.com', '@gmail.com',
  '@outlook.com', '@hotmail.com', '@foxmail.com',
  '@yeah.net', '@sina.com', '@aliyun.com',
];

/**
 * LDAP 形态的账号文案。
 *
 * 员工记住的是自己的企业邮箱，不是目录里的 sAMAccountName —— 让登录框直接
 * 收邮箱，用户才不用猜"我该输工号还是英文名"。
 */
export const LDAP_ACCOUNT_LABEL = '企业邮箱';
export const LDAP_ACCOUNT_REQUIRED = '请输入企业邮箱';

/** LDAP 形态的输入占位符：配了邮箱域名就把完整示例给出来。 */
export const ldapAccountPlaceholder = (emailDomain: string): string => {
  const domain = (emailDomain || '').trim().replace(/^@/, '');
  return domain ? `name@${domain}` : '请输入企业邮箱';
};

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
  // 登录形态：LDAP 形态下用企业邮箱登录（后端会把它映射到目录账号）。
  // 由后端 /auth/login-mode 下发，取不到时按本地邮箱登录（保守默认）。
  const [authMode, setAuthMode] = useState<{
    mode: 'ldap' | 'local';
    email_domain: string;
    allow_code: boolean;
    allow_register: boolean;
  }>({ mode: 'local', email_domain: '', allow_code: true, allow_register: true });
  const isLdap = authMode.mode === 'ldap';

  useEffect(() => {
    let alive = true;
    apiFetch<{ mode: 'ldap' | 'local'; email_domain: string; allow_code: boolean; allow_register: boolean }>(
      '/api/v1/auth/login-mode',
      {},
      '获取登录方式失败',
    )
      .then((info) => {
        if (alive && info) setAuthMode(info);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  // LDAP 形态默认走密码登录（后端验证码/注册路径本就拒绝）
  useEffect(() => {
    if (isLdap && loginMode !== 'password') setLoginMode('password');
  }, [isLdap, loginMode]);

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
    // LDAP 形态：补企业域名（用户只想敲名字时省掉后缀）；没配域名就不补
    if (authMode.mode === 'ldap') {
      const domain = (authMode.email_domain || '').trim().replace(/^@/, '');
      return domain ? [`${email}@${domain}`] : [];
    }
    return EMAIL_SUFFIXES.map((suffix) => email + suffix);
  }, [email, authMode.mode, authMode.email_domain]);

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

  // 邮箱变更后作废已发送的验证码：避免用 A 邮箱的码提交 B 邮箱，服务端只报
  // "验证码错误"而用户无从归因
  const handleEmailChangedForCode = useCallback(() => {
    if (codeSent) {
      setCodeSent(false);
      setCodeCountdown(0);
    }
  }, [codeSent]);

  const zodSchema = useMemo(
    () =>
      z
        .object({
          email: authMode.mode === 'ldap'
            ? z.string().trim().min(1, LDAP_ACCOUNT_REQUIRED)
            : EMAIL_FIELD,
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
    [authMode.mode],
  );

  const onLogin = handleSubmit(async (values) => {
    if (loginMode === 'code' && !codeSent) {
      setError('root', { message: '请先发送验证码' });
      return;
    }
    const parsed = zodSchema.safeParse(values);
    if (!parsed.success) {
      const flat = parsed.error.flatten().fieldErrors;
      if (flat.email?.[0]) setError('email', { message: flat.email[0] });
      if (flat.password?.[0]) setError('password', { message: flat.password[0] });
      if (flat.code?.[0]) setError('code', { message: flat.code[0] });
      return;
    }
    try {
      // 登录成功后 authService 已写入 localStorage（含 capabilities），
      // 这里按能力决定落地页，不硬编码角色名。
      if (loginMode === 'password') {
        await loginUser(parsed.data.email.trim(), parsed.data.password);
      } else {
        await loginWithCode(parsed.data.email, parsed.data.code);
      }
      // 优先 ProtectedRoute 的 state.from；apiClient 的 401 硬跳转（清 token
      // 后 location.assign）无法携带 state，改为读取 ?from= 查询参数兜底，
      // 否则用户登录后会被丢到默认页、丢掉原本要访问的页面。
      const from =
        (location.state as { from?: string } | null)?.from ??
        new URLSearchParams(location.search).get('from');
      toast.success('登录成功，正在进入工作台');
      navigate(from || (canEnterAdmin() ? '/admin' : '/chat'), { replace: true });
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
    <AuthShell backLabel="返回首页" backTo="/">
          <div className="flex flex-col items-center mb-8">
            <div className="mb-5">
              <Logo iconSize={48} showText={false} />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-[var(--foreground)]">登录 AgenticOS</h1>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">欢迎回来，登录以继续使用</p>
          </div>

          <Card className="py-8 shadow-md">
            <CardContent className="px-8">
              {/* 登录模式切换 */}
              {!isLdap && (
              <div role="tablist" aria-label="登录方式" className="flex rounded-lg p-1 mb-6 bg-[var(--surface-2)]">
                <button
                  type="button"
                  role="tab"
                  aria-selected={loginMode === 'password'}
                  onClick={() => setLoginMode('password')}
                  className={cn(
                    'flex-1 py-1.5 text-sm font-medium rounded-md transition-all focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
                    loginMode === 'password'
                      ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                      : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
                  )}
                >
                  密码登录
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={loginMode === 'code'}
                  onClick={() => setLoginMode('code')}
                  className={cn(
                    'flex-1 py-1.5 text-sm font-medium rounded-md transition-all focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
                    loginMode === 'code'
                      ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                      : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
                  )}
                >
                  验证码登录
                </button>
              </div>
              )}

              <form className="space-y-5" onSubmit={onLogin} noValidate>
                {/* 邮箱输入 + 补全 */}
                <div ref={emailRef} className="relative space-y-2">
                  <Label htmlFor="login-email">{isLdap ? LDAP_ACCOUNT_LABEL : '邮箱地址'}</Label>
                  <Input
                    id="login-email"
                    type="email"
                    autoComplete={isLdap ? 'username' : 'email'}
                    autoFocus
                    placeholder={isLdap ? ldapAccountPlaceholder(authMode.email_domain) : 'you@example.com'}
                    aria-invalid={!!errors.email}
                    role="combobox"
                    aria-expanded={showSuggestions && suggestions.length > 0}
                    aria-controls="login-email-suggestions"
                    aria-autocomplete="list"
                    aria-activedescendant={
                      showSuggestions && selectedSuggestionIdx >= 0
                        ? `login-email-suggestion-${selectedSuggestionIdx}`
                        : undefined
                    }
                    {...register('email', {
                      onChange: () => {
                        setShowSuggestions(true);
                        setSelectedSuggestionIdx(-1);
                        handleEmailChangedForCode();
                      },
                      // 注册校验规则：否则 trigger('email') 永远返回 true，
                      // 非法邮箱（如 "abc"）会绕过客户端校验直接请求验证码接口
                      validate: (v) => {
                        const trimmed = (v ?? '').trim();
                        if (authMode.mode === 'ldap') {
                          return trimmed ? true : LDAP_ACCOUNT_REQUIRED;
                        }
                        if (!trimmed) return '请输入邮箱地址';
                        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) return '请输入有效的邮箱地址';
                        return true;
                      },
                    })}
                    onFocus={() => setShowSuggestions(true)}
                    onKeyDown={handleEmailKeyDown}
                  />
                  {errors.email && (
                    <p className="text-xs font-medium text-red-600 dark:text-red-400" role="alert">{errors.email.message}</p>
                  )}
                  {/* 邮箱后缀建议 */}
                  <AnimatePresence>
                    {showSuggestions && suggestions.length > 0 && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        id="login-email-suggestions"
                        role="listbox"
                        aria-label="邮箱补全建议"
                        className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-[var(--border-subtle)] bg-popover shadow-lg overflow-hidden z-50"
                      >
                        {suggestions.map((s, i) => (
                          <button
                            key={s}
                            type="button"
                            role="option"
                            aria-selected={i === selectedSuggestionIdx}
                            id={`login-email-suggestion-${i}`}
                            onMouseDown={(e) => { e.preventDefault(); selectSuggestion(s); }}
                            className={cn(
                              'w-full px-4 py-2 text-left text-sm transition-colors',
                              i === selectedSuggestionIdx
                                ? 'bg-accent text-accent-foreground'
                                : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]'
                            )}
                          >
                            <span className="text-[var(--muted-foreground)] opacity-60">{email}</span>
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
                      {/* 人性化：不给一条死胡同文案——告诉用户「找谁、怎么找」。
                          企业部署管理员即「第一个注册用户」（后端首注册即管理员）。 */}
                      <span
                        className="text-xs text-[var(--muted-foreground)] cursor-help underline decoration-dotted underline-offset-2"
                        title="请联系平台管理员重置密码。管理员通常是贵团队第一个注册本平台的账号。"
                      >
                        忘记密码？
                      </span>
                    </div>
                    <PasswordField
                      id="login-password"
                      placeholder="••••••••"
                      autoComplete="current-password"
                      aria-invalid={!!errors.password}
                      {...register('password')}
                    />
                    {errors.password && (
                      <p className="text-xs font-medium text-red-600 dark:text-red-400" role="alert">{errors.password.message}</p>
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
                      <p className="text-xs font-medium text-red-600 dark:text-red-400" role="alert">{errors.code.message}</p>
                    )}
                    {codeSent && !errors.code && (
                      <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400">验证码已发送到您的邮箱，请查收</p>
                    )}
                  </div>
                )}

                {errors.root && (
                  <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300">
                    {errors.root.message}
                  </div>
                )}

                <Button type="submit" disabled={isSubmitting} className="w-full h-11 text-sm">
                  {isSubmitting ? '正在登录...' : '进入工作台'}
                </Button>
              </form>

              <div className="mt-8 text-center text-sm text-[var(--muted-foreground)]">
                还没有账号？{' '}
                {!isLdap && (<Link to="/signup" className="text-primary hover:text-primary/80 font-medium underline underline-offset-4">立即注册</Link>)}
              </div>
            </CardContent>
          </Card>
    </AuthShell>
  );
};
