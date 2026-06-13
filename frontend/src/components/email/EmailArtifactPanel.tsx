/**
 * EmailArtifactPanel - 邮件预览 Artifact 面板
 * 在右侧边栏显示邮件预览，类似 PPT artifact 面板
 */

import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Mail, Send, X, User, Users, FileText, Check, XCircle } from 'lucide-react';
import { cn } from '../../lib/utils';

interface EmailArtifact {
  language: 'email';
  approvalId: string;
  to: string;
  subject: string;
  body: string;
  cc?: string;
  isHtml?: boolean;
}

interface EmailArtifactPanelProps {
  artifact: EmailArtifact;
  onClose: () => void;
  onConfirm: (approvalId: string) => void;
  onCancel: (approvalId: string) => void;
}

export const EmailArtifactPanel: React.FC<EmailArtifactPanelProps> = ({
  artifact,
  onClose,
  onConfirm,
  onCancel,
}) => {
  const [isSending, setIsSending] = useState(false);

  const handleConfirm = async () => {
    setIsSending(true);
    try {
      await onConfirm(artifact.approvalId);
    } finally {
      setIsSending(false);
    }
  };

  const handleCancel = () => {
    onCancel(artifact.approvalId);
    onClose();
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20, width: '60%' }}
      animate={{ opacity: 1, x: 0, width: '60%' }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col overflow-hidden border-l bg-white"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100">
            <Mail size={16} className="text-blue-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">邮件预览</h3>
            <p className="text-[10px] text-slate-500">确认后发送</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <X size={16} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* 收件人 */}
        <div className="mb-4">
          <div className="mb-1.5 flex items-center gap-1.5">
            <User size={14} className="text-slate-400" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              收件人
            </span>
          </div>
          <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
            {artifact.to}
          </div>
        </div>

        {/* 抄送 */}
        {artifact.cc && (
          <div className="mb-4">
            <div className="mb-1.5 flex items-center gap-1.5">
              <Users size={14} className="text-slate-400" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                抄送
              </span>
            </div>
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
              {artifact.cc}
            </div>
          </div>
        )}

        {/* 主题 */}
        <div className="mb-4">
          <div className="mb-1.5 flex items-center gap-1.5">
            <FileText size={14} className="text-slate-400" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              主题
            </span>
          </div>
          <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">
            {artifact.subject}
          </div>
        </div>

        {/* 邮件内容 */}
        <div>
          <div className="mb-1.5 flex items-center gap-1.5">
            <Mail size={14} className="text-slate-400" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              邮件内容
            </span>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            {artifact.isHtml ? (
              <iframe
                srcDoc={artifact.body}
                className="h-80 w-full rounded border-0"
                sandbox=""
                title="邮件预览"
              />
            ) : (
              <div className="max-h-80 overflow-y-auto text-sm leading-relaxed text-slate-700">
                <pre className="whitespace-pre-wrap font-sans">{artifact.body}</pre>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer Actions */}
      <div className="border-t border-slate-200 p-4">
        <div className="flex gap-2">
          <button
            onClick={handleCancel}
            disabled={isSending}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 active:scale-[0.98] disabled:opacity-50"
          >
            <XCircle size={16} />
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={isSending}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 active:scale-[0.98] disabled:opacity-50"
          >
            {isSending ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              >
                <Send size={16} />
              </motion.div>
            ) : (
              <Send size={16} />
            )}
            确认发送
          </button>
        </div>
      </div>
    </motion.div>
  );
};
