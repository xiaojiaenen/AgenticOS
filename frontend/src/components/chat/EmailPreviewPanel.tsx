/**
 * EmailPreviewPanel - 邮件发送预览面板
 * 在发送邮件前显示收件人、抄送人、主题、内容，让用户确认
 */

import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { sanitizeHtml } from '../../lib/safePreview';
import { Mail, Send, X, User, Users, FileText } from 'lucide-react';

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
  onDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
};

export const EmailPreviewPanel: React.FC<EmailPreviewPanelProps> = ({ emails, onDecision }) => {  if (emails.length === 0) return null;

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
          <EmailPreviewContent emails={emails} onDecision={onDecision} />
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

const EmailPreviewContent: React.FC<{
  emails: EmailPreview[];
  onDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
}> = ({ emails, onDecision }) => {
  return (
    <>
      <div className={cn("mb-3 flex items-center gap-2", "text-[var(--foreground)]")}>
        <Mail size={17} />
        <span className="text-xs font-semibold uppercase tracking-[0.16em]">邮件发送确认</span>
      </div>
      <div className="flex flex-col gap-3">
        {emails.map((email) => (
          <EmailCard
            key={email.approval_id}
            email={email}
            onDecision={onDecision}
          />
        ))}
      </div>
    </>
  );
};

const EmailCard: React.FC<{
  email: EmailPreview;
  onDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
}> = ({ email, onDecision }) => {
  return (
    <div className={cn(
      "rounded-xl p-4",
      "border border-[var(--border-subtle)] bg-[var(--surface-1)]"
    )}>
      {/* 收件人 */}
      <div className="mb-3 flex items-start gap-2">
        <User size={14} className={cn("mt-0.5 flex-shrink-0", "text-[var(--muted-foreground)]")} />
        <div>
          <div className={cn("text-[10px] font-semibold uppercase tracking-wider", "text-[var(--muted-foreground)]")}>
            收件人
          </div>
          <div className={cn("text-sm font-medium", "text-[var(--foreground)]")}>
            {email.to}
          </div>
        </div>
      </div>

      {/* 抄送 */}
      {email.cc && (
        <div className="mb-3 flex items-start gap-2">
          <Users size={14} className={cn("mt-0.5 flex-shrink-0", "text-[var(--muted-foreground)]")} />
          <div>
            <div className={cn("text-[10px] font-semibold uppercase tracking-wider", "text-[var(--muted-foreground)]")}>
              抄送
            </div>
            <div className={cn("text-sm font-medium", "text-[var(--foreground)]")}>
              {email.cc}
            </div>
          </div>
        </div>
      )}

      {/* 主题 */}
      <div className="mb-3 flex items-start gap-2">
        <FileText size={14} className={cn("mt-0.5 flex-shrink-0", "text-[var(--muted-foreground)]")} />
        <div>
          <div className={cn("text-[10px] font-semibold uppercase tracking-wider", "text-[var(--muted-foreground)]")}>
            主题
          </div>
          <div className={cn("text-sm font-semibold", "text-[var(--foreground)]")}>
            {email.subject}
          </div>
        </div>
      </div>

      {/* 邮件内容 */}
      <div className={cn("mb-4 rounded-lg p-3", "bg-[var(--surface-2)] border border-[var(--border-subtle)]")}>
        <div className={cn("text-[10px] font-semibold uppercase tracking-wider mb-2", "text-[var(--muted-foreground)]")}>
          邮件内容
        </div>
        <div className={cn(
          "max-h-48 overflow-y-auto text-sm leading-relaxed",
          "text-[var(--foreground)]"
        )}>
          {email.is_html ? (
            // 邮件 body 来自工具调用参数，必须消毒后再插入 DOM，防 XSS
            <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(email.body) }} />
          ) : (
            <pre className="whitespace-pre-wrap font-sans">{email.body}</pre>
          )}
        </div>
      </div>

      {/* 操作按钮 */}
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
          onClick={() => onDecision(email.approval_id, 'approved')}
          className="inline-flex items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 active:scale-95 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
        >
          <Send size={13} />
          确认发送
        </button>
      </div>
    </div>
  );
};
