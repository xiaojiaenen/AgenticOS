/**
 * EmailPreviewPanel - 邮件发送预览面板
 * 在发送邮件前显示收件人、抄送人、主题、内容，让用户确认
 */

import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
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
        <div className="rounded-2xl border border-blue-200/80 bg-blue-50/85 px-4 py-3 shadow-[0_18px_42px_rgba(59,130,246,0.14)]">
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
      <div className={cn("mb-3 flex items-center gap-2", "text-blue-700")}>
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
      "border border-white/70 bg-white/76"
    )}>
      {/* 收件人 */}
      <div className="mb-3 flex items-start gap-2">
        <User size={14} className={cn("mt-0.5 flex-shrink-0", "text-slate-400")} />
        <div>
          <div className={cn("text-[10px] font-semibold uppercase tracking-wider", "text-slate-400")}>
            收件人
          </div>
          <div className={cn("text-sm font-medium", "text-slate-800")}>
            {email.to}
          </div>
        </div>
      </div>

      {/* 抄送 */}
      {email.cc && (
        <div className="mb-3 flex items-start gap-2">
          <Users size={14} className={cn("mt-0.5 flex-shrink-0", "text-slate-400")} />
          <div>
            <div className={cn("text-[10px] font-semibold uppercase tracking-wider", "text-slate-400")}>
              抄送
            </div>
            <div className={cn("text-sm font-medium", "text-slate-800")}>
              {email.cc}
            </div>
          </div>
        </div>
      )}

      {/* 主题 */}
      <div className="mb-3 flex items-start gap-2">
        <FileText size={14} className={cn("mt-0.5 flex-shrink-0", "text-slate-400")} />
        <div>
          <div className={cn("text-[10px] font-semibold uppercase tracking-wider", "text-slate-400")}>
            主题
          </div>
          <div className={cn("text-sm font-semibold", "text-slate-900")}>
            {email.subject}
          </div>
        </div>
      </div>

      {/* 邮件内容 */}
      <div className={cn("mb-4 rounded-lg p-3", "bg-slate-50/80 border border-slate-200/60")}>
        <div className={cn("text-[10px] font-semibold uppercase tracking-wider mb-2", "text-slate-400")}>
          邮件内容
        </div>
        <div className={cn(
          "max-h-48 overflow-y-auto text-sm leading-relaxed",
          "text-slate-700"
        )}>
          {email.is_html ? (
            <div dangerouslySetInnerHTML={{ __html: email.body }} />
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
            "border border-rose-200 bg-white text-rose-600 hover:bg-rose-50"
          )}
        >
          <X size={13} />
          取消
        </button>
        <button
          type="button"
          onClick={() => onDecision(email.approval_id, 'approved')}
          className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700 active:scale-95"
        >
          <Send size={13} />
          确认发送
        </button>
      </div>
    </div>
  );
};
