import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Mail, CheckCircle, AlertCircle, Loader2, X, Eye, EyeOff, Trash2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { getEmailStatus, saveEmailCredentials, deleteEmailCredentials, EmailStatus } from '../../services/emailService';

const EMAIL_PRESETS = [
  { label: '腾讯企业邮箱', value: 'exmail_qq', imap_host: 'imap.exmail.qq.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.exmail.qq.com', smtp_port: 465, smtp_ssl: true },
  { label: 'QQ 邮箱', value: 'qq', imap_host: 'imap.qq.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.qq.com', smtp_port: 465, smtp_ssl: true },
  { label: '163 邮箱', value: '163', imap_host: 'imap.163.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.163.com', smtp_port: 465, smtp_ssl: true },
  { label: '126 邮箱', value: '126', imap_host: 'imap.126.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.126.com', smtp_port: 465, smtp_ssl: true },
  { label: 'Gmail', value: 'gmail', imap_host: 'imap.gmail.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.gmail.com', smtp_port: 587, smtp_ssl: false },
  { label: 'Outlook / Hotmail', value: 'outlook', imap_host: 'outlook.office365.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.office365.com', smtp_port: 587, smtp_ssl: false },
  { label: '阿里企业邮箱', value: 'aliyun', imap_host: 'imap.qiye.aliyun.com', imap_port: 993, imap_ssl: true, smtp_host: 'smtp.qiye.aliyun.com', smtp_port: 465, smtp_ssl: true },
  { label: '自定义', value: 'custom', imap_host: '', imap_port: 993, imap_ssl: true, smtp_host: '', smtp_port: 465, smtp_ssl: true },
];

interface EmailSettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

export const EmailSettingsPanel: React.FC<EmailSettingsPanelProps> = ({ open, onClose }) => {
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [preset, setPreset] = useState('exmail_qq');

  const [form, setForm] = useState({
    email_address: '',
    password: '',
    imap_host: 'imap.exmail.qq.com',
    imap_port: 993,
    imap_ssl: true,
    smtp_host: 'smtp.exmail.qq.com',
    smtp_port: 465,
    smtp_ssl: true,
  });

  const handlePresetChange = (value: string) => {
    setPreset(value);
    const p = EMAIL_PRESETS.find((x) => x.value === value);
    if (p && value !== 'custom') {
      setForm((f) => ({
        ...f,
        imap_host: p.imap_host,
        imap_port: p.imap_port,
        imap_ssl: p.imap_ssl,
        smtp_host: p.smtp_host,
        smtp_port: p.smtp_port,
        smtp_ssl: p.smtp_ssl,
      }));
    }
    setShowAdvanced(value === 'custom');
  };

  useEffect(() => {
    if (!open) return;
    setIsLoading(true);
    setError(null);
    getEmailStatus()
      .then((s) => {
        setStatus(s);
        if (s.email_address) setForm((f) => ({ ...f, email_address: s.email_address || '' }));
        if (s.imap_host) setForm((f) => ({ ...f, imap_host: s.imap_host || 'imap.exmail.qq.com' }));
      })
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false));
  }, [open]);

  const handleSave = async () => {
    if (!form.email_address.trim() || !form.password.trim()) {
      setError('请填写邮箱地址和密码');
      return;
    }
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await saveEmailCredentials(form);
      if (result.error) {
        setError(result.error);
      } else {
        setSuccess(result.message || '邮箱配置已保存');
        setStatus({ configured: true, email_address: form.email_address, imap_host: form.imap_host, smtp_host: form.smtp_host });
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('确定删除邮箱配置？')) return;
    setIsSaving(true);
    setError(null);
    try {
      await deleteEmailCredentials();
      setStatus({ configured: false, email_address: null, imap_host: null, smtp_host: null });
      setForm((f) => ({ ...f, email_address: '', password: '' }));
      setSuccess('邮箱配置已删除');
      setTimeout(() => setSuccess(null), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败');
    } finally {
      setIsSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="admin-modal-shell" onMouseDown={onClose}>
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.96 }}
        transition={{ duration: 0.22 }}
        onMouseDown={(e) => e.stopPropagation()}
        className="admin-solid-panel admin-modal-panel w-full max-w-md overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sky-50 text-sky-600">
              <Mail size={20} />
            </div>
            <div>
              <p className="admin-section-kicker">邮件配置</p>
              <h3 className="mt-1 text-lg font-black text-slate-900">邮箱设置</h3>
            </div>
          </div>
          <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600">
            <X size={16} />
          </button>
        </div>

        {/* Status bar */}
        {status?.configured && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
            <CheckCircle size={14} />
            <span>已连接 {status.email_address}</span>
          </div>
        )}

        {/* Content */}
        <div className="px-6 pt-4 pb-6 space-y-4">
          {isLoading ? (
            <div className="flex h-32 items-center justify-center gap-2 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" /> 加载中
            </div>
          ) : (
            <>
              <div>
                <label className="mb-1.5 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">邮箱服务商</label>
                <select
                  className="admin-input"
                  value={preset}
                  onChange={(e) => handlePresetChange(e.target.value)}
                >
                  {EMAIL_PRESETS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">邮箱地址</label>
                <input
                  type="email"
                  className="admin-input"
                  value={form.email_address}
                  onChange={(e) => setForm({ ...form, email_address: e.target.value })}
                  placeholder="your@email.com"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                  应用专用密码
                  <span className="ml-2 normal-case tracking-normal font-medium text-slate-400">（非登录密码，在邮箱设置中生成）</span>
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="admin-input pr-10"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    placeholder="输入应用专用密码"
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {/* Advanced settings */}
              <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className="text-xs font-bold text-slate-400 hover:text-slate-600 transition-colors">
                {showAdvanced ? '▾ 收起高级设置' : '▸ 高级设置（服务器地址）'}
              </button>

              <AnimatePresence>
                {showAdvanced && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="mb-1 block text-[11px] font-bold text-slate-500">IMAP 服务器</label>
                        <input className="admin-input font-mono text-xs" value={form.imap_host} onChange={(e) => setForm({ ...form, imap_host: e.target.value })} />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] font-bold text-slate-500">IMAP 端口</label>
                        <input className="admin-input font-mono text-xs" type="number" value={form.imap_port} onChange={(e) => setForm({ ...form, imap_port: Number(e.target.value) })} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="mb-1 block text-[11px] font-bold text-slate-500">SMTP 服务器</label>
                        <input className="admin-input font-mono text-xs" value={form.smtp_host} onChange={(e) => setForm({ ...form, smtp_host: e.target.value })} />
                      </div>
                      <div>
                        <label className="mb-1 block text-[11px] font-bold text-slate-500">SMTP 端口</label>
                        <input className="admin-input font-mono text-xs" type="number" value={form.smtp_port} onChange={(e) => setForm({ ...form, smtp_port: Number(e.target.value) })} />
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Messages */}
              {error && (
                <div className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700">
                  <AlertCircle size={14} /> {error}
                </div>
              )}
              {success && (
                <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
                  <CheckCircle size={14} /> {success}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-2">
                <Button variant="primary" onClick={handleSave} disabled={isSaving} className="flex-1 gap-2">
                  {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
                  {status?.configured ? '更新配置' : '保存并测试连接'}
                </Button>
                {status?.configured && (
                  <Button variant="secondary" onClick={handleDelete} disabled={isSaving} className="gap-1.5">
                    <Trash2 size={14} className="text-rose-500" />
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
};
