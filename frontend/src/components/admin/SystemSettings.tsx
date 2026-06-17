import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Server } from 'lucide-react';
import { getLdapSetting, updateLdapSetting } from '../../services/settingsService';
import { cn } from '../../lib/utils';
import { useIsGlassTheme } from '../liquid-glass';
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';

export const SystemSettings = () => {
  const isGlass = useIsGlassTheme();
  const [ldapEnabled, setLdapEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getLdapSetting();
      setLdapEnabled(result.ldap_enabled);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载设置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleLdap = async () => {
    const newValue = !ldapEnabled;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await updateLdapSetting(newValue);
      setLdapEnabled(result.ldap_enabled);
      setSuccess(result.ldap_enabled ? 'LDAP 认证已开启，用户可使用工号登录' : 'LDAP 认证已关闭，仅本地用户可登录');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存设置失败');
    } finally {
      setSaving(false);
    }
  };

  const GlassCard: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => {
    if (isGlass) {
      return (
        <LiquidGlass {...glassPresets.card} tint="rgba(255,255,255,0.06)" radius={12} className={className}>
          {children}
        </LiquidGlass>
      );
    }
    return <section className={cn("border border-[var(--admin-card-border)] bg-[var(--admin-card-bg)]", className)}>{children}</section>;
  };

  if (loading) {
    return (
      <div className="admin-page-stage space-y-5">
        <GlassCard className="p-10">
          <div className="flex items-center justify-center gap-3">
            <Loader2 size={20} className="animate-spin text-slate-400" />
            <span className="text-sm text-slate-400">加载设置中...</span>
          </div>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="admin-page-stage space-y-5">
      <GlassCard className="p-5">
        <div>
          <p className={cn("admin-section-kicker", isGlass && "text-gray-400")}>系统设置</p>
          <h1 className={cn("mt-1.5 text-2xl font-semibold tracking-tight lg:text-3xl", isGlass ? "text-white" : "text-slate-950")}>系统配置</h1>
        </div>
      </GlassCard>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
          <CheckCircle2 size={18} />
          {success}
        </div>
      )}

      {/* LDAP 认证开关 */}
      <GlassCard className={cn("p-5")}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <div className={cn(
              "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl",
              isGlass ? "bg-white/10 text-sky-400" : "bg-sky-50 text-sky-600"
            )}>
              <Server size={20} />
            </div>
            <div>
              <h3 className={cn("text-base font-semibold", isGlass ? "text-white" : "text-slate-900")}>LDAP 认证</h3>
              <p className={cn("mt-1 text-sm font-medium leading-relaxed", isGlass ? "text-gray-400" : "text-slate-500")}>
                启用后用户可通过工号 + LDAP 密码登录，自动禁用本地密码登录和注册功能。
                开启 <span className={cn("font-semibold", isGlass ? "text-amber-400" : "text-amber-600")}>LDAP_AUTO_CREATE_USERS=true</span> 时首次登录将自动创建用户。
              </p>
              <div className={cn("mt-2 flex items-center gap-2 text-xs font-medium", isGlass ? "text-gray-500" : "text-slate-400")}>
                <span className={cn(
                  "inline-block h-1.5 w-1.5 rounded-full",
                  ldapEnabled ? "bg-emerald-500" : "bg-slate-400"
                )} />
                {ldapEnabled ? '已启用 — LDAP 网关控制身份验证' : '已禁用 — 仅使用本地密码登录'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={handleToggleLdap}
            disabled={saving}
            className={cn(
              "relative inline-flex h-7 w-11 flex-shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2",
              ldapEnabled ? "bg-sky-500" : "bg-slate-300",
              saving && "opacity-50 cursor-not-allowed"
            )}
            role="switch"
            aria-checked={ldapEnabled}
            aria-label="LDAP 认证开关"
          >
            <span
              className={cn(
                "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-md ring-0 transition-transform duration-200",
                ldapEnabled ? "translate-x-4" : "translate-x-0.5"
              )}
            />
            {saving && (
              <span className="absolute inset-0 flex items-center justify-center">
                <Loader2 size={12} className="animate-spin text-white" />
              </span>
            )}
          </button>
        </div>
      </GlassCard>

      {/* 提示信息 */}
      <GlassCard className="p-5">
        <div className={cn("rounded-lg border p-4 text-sm font-medium leading-relaxed", isGlass ? "border-white/10 text-gray-400" : "border-slate-200 text-slate-500")}>
          <p className="font-semibold">💡 注意：</p>
          <ul className={cn("mt-2 list-disc space-y-1 pl-5", isGlass ? "text-gray-400" : "text-slate-500")}>
            <li>切换 LDAP 状态后无需重启后端服务</li>
            <li>LDAP 网关地址、域名等高级配置仍需在 <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-sky-400">.env</code> 文件中设置</li>
            <li>首次启用时，系统会从 <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-sky-400">.env</code> 中的 <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-sky-400">LDAP_ENABLED</code> 值同步初始状态</li>
          </ul>
        </div>
      </GlassCard>
    </div>
  );
};
