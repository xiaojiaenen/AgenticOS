/**
 * EmailPreviewPanel - 邮件发送预览面板
 *
 * 用户可以：
 *   1. 在下拉里**即时切换模板** —— 调后端纯函数预览端点，不经 AI 重写，毫秒级刷新；
 *   2. **只编辑内容**（收件人/抄送/主题/正文/按钮/署名），不接触 HTML 源码；
 *   3. 看只读的渲染结果预览；
 *   4. 确认发送时，把最终渲染好的 HTML 作为 modified_arguments 回传，
 *      后端用改后的参数真正执行 send_email。
 *
 * 「自定义」模板不在这里渲染（交给 AI 按 email-design skill 撰写），选中时
 * 保留纯文本并给出提示。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { sanitizeHtml } from '../../lib/safePreview';
import {
  Mail, Send, X, Palette, Edit3, Eye,
} from 'lucide-react';
import {
  listEmailTemplates,
  previewEmailTemplate,
  type EmailTemplateChoice,
} from '../../services/agentService';

export type EmailPreview = {
  approval_id: string;
  to: string;
  subject: string;
  body: string;
  cc?: string;
  is_html?: boolean;
};

type EmailPreviewPanelProps = {
  emails: EmailPreview[];
  /** 第 3 个参数是用户在预览里改过的工具参数（含渲染后的 body） */
  onDecision: (
    approvalId: string,
    status: 'approved' | 'rejected',
    modifiedArguments?: Record<string, unknown>,
  ) => void;
};

export const EmailPreviewPanel: React.FC<EmailPreviewPanelProps> = ({ emails, onDecision }) => {
  if (emails.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
        className="mb-3"
      >
        <div className="rounded-2xl border border-[var(--border-medium)] bg-[var(--surface-3)] px-4 py-3 shadow-[0_18px_42px_rgba(9,9,11,0.18)]">
          <div className={cn("mb-3 flex items-center gap-2", "text-[var(--foreground)]")}>
            <Mail size={17} />
            <span className="text-xs font-semibold uppercase tracking-[0.16em]">邮件发送确认</span>
          </div>
          <div className="flex flex-col gap-3">
            {emails.map((email) => (
              <EmailCard key={email.approval_id} email={email} onDecision={onDecision} />
            ))}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

/** 从工具参数里尽量还原可编辑内容（body 是纯文本；若是 HTML 则退化为去标签文本）。 */
function toPlainText(body: string, isHtml: boolean): string {
  if (!isHtml) return body;
  // 只做展示用的粗略去标签，用户编辑的是纯文本内容，不编辑源码
  const tmp = document.createElement('div');
  tmp.innerHTML = sanitizeHtml(body);
  return (tmp.textContent || '').trim();
}

const EmailCard: React.FC<{
  email: EmailPreview;
  onDecision: EmailPreviewPanelProps['onDecision'];
}> = ({ email, onDecision }) => {
  // ── 可编辑的「内容」字段（不含任何 HTML 源码） ──
  const [to, setTo] = useState(email.to);
  const [cc, setCc] = useState(email.cc || '');
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(() => toPlainText(email.body, Boolean(email.is_html)));
  const [buttonLabel, setButtonLabel] = useState('');
  const [buttonUrl, setButtonUrl] = useState('');
  const [signer, setSigner] = useState('');

  // ── 模板选择与预览 ──
  const [templates, setTemplates] = useState<EmailTemplateChoice[]>([]);
  const [template, setTemplate] = useState<string>(email.is_html ? 'swiss' : 'plain');
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewIsHtml, setPreviewIsHtml] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 加载模板列表
  useEffect(() => {
    let alive = true;
    listEmailTemplates()
      .then((list) => { if (alive) setTemplates(list); })
      .catch(() => { /* 拿不到模板列表时退化为纯文本，不阻断发送 */ });
    return () => { alive = false; };
  }, []);

  // 切换模板 / 编辑内容 → 即时重渲染预览（纯函数端点，不经 AI）
  const refreshPreview = useCallback(async (
    tpl: string,
    overrides?: Partial<{ subject: string; body: string; buttonLabel: string; buttonUrl: string; signer: string }>,
  ) => {
    const s = overrides?.subject ?? subject;
    const b = overrides?.body ?? body;
    const bl = overrides?.buttonLabel ?? buttonLabel;
    const bu = overrides?.buttonUrl ?? buttonUrl;
    const sg = overrides?.signer ?? signer;

    if (tpl === 'plain' || tpl === 'custom') {
      setPreviewHtml(b);
      setPreviewIsHtml(false);
      return;
    }
    setPreviewing(true);
    try {
      const res = await previewEmailTemplate({
        template: tpl, subject: s, body: b,
        button_label: bl, button_url: bu, signer: sg,
      });
      setPreviewHtml(res.html);
      setPreviewIsHtml(res.is_html);
    } catch {
      // 预览失败不影响发送：退回纯文本
      setPreviewHtml(b);
      setPreviewIsHtml(false);
    } finally {
      setPreviewing(false);
    }
  }, [subject, body, buttonLabel, buttonUrl, signer]);

  // 内容变化后防抖刷新
  const scheduleRefresh = useCallback((next: { subject?: string; body?: string; buttonLabel?: string; buttonUrl?: string; signer?: string }) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => refreshPreview(template, next), 260);
  }, [template, refreshPreview]);

  // 初始先渲染一次
  useEffect(() => {
    refreshPreview(template);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onTemplateChange = (next: string) => {
    setTemplate(next);
    refreshPreview(next);
  };

  const onApprove = () => {
    // 把用户改过的内容 + 当前渲染结果，作为工具参数回传。
    // 后端批准后按这份参数执行 send_email（body 是渲染好的 HTML，is_html=true）。
    const finalBody = previewHtml ?? body;
    const finalIsHtml = previewIsHtml;
    onDecision(email.approval_id, 'approved', {
      to,
      ...(cc ? { cc } : {}),
      subject,
      body: finalBody,
      is_html: finalIsHtml,
    });
  };

  const fieldCls = cn(
    "w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 py-1.5",
    "text-sm text-[var(--foreground)] outline-none",
    "focus-visible:border-[var(--ring)] focus-visible:ring-2 focus-visible:ring-[var(--ring-halo)]"
  );
  const labelCls = "text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1 block";

  return (
    <div className={cn("rounded-xl p-4", "border border-[var(--border-subtle)] bg-[var(--surface-1)]")}>

      {/* ── 模板选择：切换即重渲染，不经 AI ── */}
      <div className="mb-3 flex items-center gap-2">
        <Palette size={14} className="text-[var(--muted-foreground)]" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">模板</span>
        <select
          aria-label="选择邮件模板"
          value={template}
          onChange={(e) => onTemplateChange(e.target.value)}
          className={cn(
            "ml-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1.5",
            "text-xs font-medium text-[var(--foreground)] outline-none",
            "focus-visible:border-[var(--ring)]"
          )}
        >
          {(templates.length ? templates : [
            { id: 'plain', label: '纯文本' },
            { id: 'swiss', label: '瑞士网格 · 冷中性' },
            { id: 'notice', label: '系统通知（深底印刷）' },
            { id: 'custom', label: '自定义（让 AI 按 skill 撰写）' },
          ]).map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
        {previewing && <span className="text-[10px] text-[var(--muted-foreground)]">渲染中…</span>}
      </div>

      {template === 'custom' && (
        <div className="mb-3 rounded-lg border border-dashed border-[var(--border-subtle)] px-3 py-2 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
          自定义风格需要 AI 按 email-design skill 重新撰写。关闭本预览后，在对话里直接说明想要的风格即可；此处仍按纯文本发送。
        </div>
      )}

      {/* ── 内容编辑（只编辑字段，不编辑 HTML 源码） ── */}
      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors",
            editing
              ? "bg-[var(--surface-2)] text-[var(--foreground)]"
              : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          )}
        >
          {editing ? <Edit3 size={12} /> : <Eye size={12} />}
          {editing ? '编辑内容' : '编辑内容'}
        </button>
        <span className="text-[10px] text-[var(--muted-foreground)]">
          {editing ? '改完自动刷新右侧预览' : '点击展开可编辑字段'}
        </span>
      </div>

      {editing && (
        <div className="mb-3 grid gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelCls}>收件人</label>
              <input className={fieldCls} value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>抄送</label>
              <input className={fieldCls} value={cc} onChange={(e) => setCc(e.target.value)} placeholder="可选" />
            </div>
          </div>
          <div>
            <label className={labelCls}>主题</label>
            <input
              className={fieldCls} value={subject}
              onChange={(e) => { setSubject(e.target.value); scheduleRefresh({ subject: e.target.value }); }}
            />
          </div>
          <div>
            <label className={labelCls}>正文（纯文本，空行分段）</label>
            <textarea
              className={cn(fieldCls, "min-h-24 resize-y font-sans leading-relaxed")}
              value={body}
              onChange={(e) => { setBody(e.target.value); scheduleRefresh({ body: e.target.value }); }}
            />
          </div>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-left text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            {showAdvanced ? '收起按钮与署名' : '＋ 添加按钮 / 署名'}
          </button>
          {showAdvanced && (
            <div className="grid gap-2 pt-1">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={labelCls}>按钮文字</label>
                  <input className={fieldCls} value={buttonLabel}
                    onChange={(e) => { setButtonLabel(e.target.value); scheduleRefresh({ buttonLabel: e.target.value }); }} />
                </div>
                <div>
                  <label className={labelCls}>按钮链接</label>
                  <input className={fieldCls} value={buttonUrl} placeholder="https://…"
                    onChange={(e) => { setButtonUrl(e.target.value); scheduleRefresh({ buttonUrl: e.target.value }); }} />
                </div>
              </div>
              <div>
                <label className={labelCls}>署名</label>
                <input className={fieldCls} value={signer}
                  onChange={(e) => { setSigner(e.target.value); scheduleRefresh({ signer: e.target.value }); }} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 只读预览（渲染结果，绝不提供源码编辑） ── */}
      <div className={cn("mb-4 rounded-lg p-3", "bg-[var(--surface-2)] border border-[var(--border-subtle)]")}>
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            预览（只读）
          </span>
          <span className="ml-auto font-mono text-[10px] text-[var(--muted-foreground)]">
            收件人 {to || '—'}
          </span>
        </div>
        <div className={cn(
          "max-h-56 overflow-y-auto rounded-md bg-white p-3 text-sm leading-relaxed",
          "text-[#1a1a1a]"
        )}>
          {previewIsHtml && previewHtml ? (
            <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(previewHtml) }} />
          ) : (
            <pre className="whitespace-pre-wrap font-sans">{previewHtml ?? body}</pre>
          )}
        </div>
      </div>

      {/* ── 操作 ── */}
      <div className="flex items-center gap-2 justify-end">
        <button
          type="button"
          onClick={() => onDecision(email.approval_id, 'rejected')}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold transition-colors active:scale-95",
            "border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--border-strong)]"
          )}
        >
          <X size={13} />
          取消
        </button>
        <button
          type="button"
          onClick={onApprove}
          className="inline-flex items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 active:scale-95 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
        >
          <Send size={13} />
          确认发送
        </button>
      </div>
    </div>
  );
};
