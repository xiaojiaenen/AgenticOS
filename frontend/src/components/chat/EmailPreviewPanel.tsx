/**
 * EmailPreviewPanel - 邮件发送预览面板
 * 在发送邮件前显示收件人、抄送人、主题、内容，让用户确认
 */

import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Mail, Send, X, User, Users, FileText } from 'lucide-react';
import { useIsGlassTheme } from '../liquid-glass';
import { LiquidGlass, glassPresets } from '@xiaojiaenen/liquid-glass';
import { cn } from '../../lib/utils';

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

export const EmailPreviewPanel: React.FC<EmailPreviewPanelProps> = ({ emails, onDecision }) => {
  const isGlass = useIsGlassTheme();

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
        {isGlass ? (
          <LiquidGlass {...glassPresets.card} tint="rgba(59,130,246,0.08)" radius={16} style={{ width: '100%', padding: '16px' }}>
            <EmailPreviewContent emails={emails} onDecision={onDecision} isGlass={isGlass} />
          </LiquidGlass>
        ) : (
          <div className="rounded-2xl border border-blue-200/80 bg-blue-50/85 px-4 py-3 shadow-[0_18px_42px_rgba(59,130,246,0.14)] backdrop-blur-xl">
            <EmailPreviewContent emails={emails} onDecision={onDecision} isGlass={isGlass} />
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
};

const EmailPreviewContent: React.FC<{
  emails: EmailPreview[];
  onDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
  isGlass: boolean;
}> = ({ emails, onDecision, isGlass }) => {
  return (
    <>
      <div className={cn("mb-3 flex items-center gap-2", isGlass ? "text-white/70" : "text-blue-700")}>
        <Mail size={17} />
        <span className="text-xs font-black uppercase tracking-[0.16em]">邮件发送确认</span>
      </div>
      <div className="flex flex-col gap-3">
        {emails.map((email) => (
          <EmailCard
            key={email.approval_id}
            email={email}
            onDecision={onDecision}
            isGlass={isGlass}
          />
        ))}
      </div>
    </>
  );
};

const EmailCard: React.FC<{
  email: EmailPreview;
  onDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
  isGlass: boolean;
}> = ({ email, onDecision, isGlass }) => {
  return (
    <div className={cn(
      "rounded-xl p-4",
      isGlass ? "bg-white/8" : "border border-white/70 bg-white/76"
    )}>
      {/* 收件人 */}
      <div className="mb-3 flex items-start gap-2">
        <User size={14} className={cn("mt-0.5 flex-shrink-0", isGlass ? "text-white/50" : "text-slate-400")} />
        <div>
          <div className={cn("text-[10px] font-semibold uppercase tracking-wider", isGlass ? "text-white/40" : "text-slate-400")}>
            收件人
          </div>
          <div className={cn("text-sm font-medium", isGlass ? "text-white" : "text-slate-800")}>
            {email.to}
          </div>
        </div>
      </div>

      {/* 抄送 */}
      {email.cc && (
        <div className="mb-3 flex items-start gap-2">
          <Users size={14} className={cn("mt-0.5 flex-shrink-0", isGlass ? "text-white/50" : "text-slate-400")} />
          <div>
            <div className={cn("text-[10px] font-semibold uppercase tracking-wider", isGlass ? "text-white/40" : "text-slate-400")}>
              抄送
            </div>
            <div className={cn("text-sm font-medium", isGlass ? "text-white" : "text-slate-800")}>
              {email.cc}
            </div>
          </div>
        </div>
      )}

      {/* 主题 */}
      <div className="mb-3 flex items-start gap-2">
        <FileText size={14} className={cn("mt-0.5 flex-shrink-0", isGlass ? "text-white/50" : "text-slate-400")} />
        <div>
          <div className={cn("text-[10px] font-semibold uppercase tracking-wider", isGlass ? "text-white/40" : "text-slate-400")}>
            主题
          </div>
          <div className={cn("text-sm font-semibold", isGlass ? "text-white" : "text-slate-900")}>
            {email.subject}
          </div>
        </div>
      </div>

      {/* 邮件内容 */}
      <div className={cn("mb-4 rounded-lg p-3", isGlass ? "bg-white/5" : "bg-slate-50/80 border border-slate-200/60")}>
        <div className={cn("text-[10px] font-semibold uppercase tracking-wider mb-2", isGlass ? "text-white/40" : "text-slate-400")}>
          邮件内容
        </div>
        <div className={cn(
          "max-h-48 overflow-y-auto text-sm leading-relaxed",
          isGlass ? "text-white/80" : "text-slate-700"
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
            "inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-bold transition-colors active:scale-95",
            isGlass
              ? "bg-white/10 text-white/70 hover:bg-white/20"
              : "border border-rose-200 bg-white text-rose-600 hover:bg-rose-50"
          )}
        >
          <X size={13} />
          取消
        </button>
        <button
          type="button"
          onClick={() => onDecision(email.approval_id, 'approved')}
          className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-blue-700 active:scale-95"
        >
          <Send size={13} />
          确认发送
        </button>
      </div>
    </div>
  );
};
