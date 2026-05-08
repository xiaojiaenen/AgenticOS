import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  maxWidth?: string;
}

export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  children,
  className,
  maxWidth = 'max-w-lg',
}) => {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="admin-modal-shell"
          onMouseDown={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ duration: 0.22 }}
            onMouseDown={(e) => e.stopPropagation()}
            className={cn('admin-solid-panel admin-modal-panel w-full p-6', maxWidth, className)}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export const ModalHeader: React.FC<{
  title: string;
  subtitle?: string;
  onClose: () => void;
}> = ({ title, subtitle, onClose }) => (
  <div className="mb-6 flex items-center justify-between">
    <div>
      <p className="admin-section-kicker">{subtitle || ''}</p>
      <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">{title}</h3>
    </div>
    <button
      type="button"
      onClick={onClose}
      className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
      aria-label="关闭"
    >
      <X size={19} />
    </button>
  </div>
);

export const ModalFooter: React.FC<{
  onCancel: () => void;
  onSubmit?: () => void;
  submitLabel?: string;
  isSaving?: boolean;
  children?: React.ReactNode;
}> = ({ onCancel, onSubmit, submitLabel = '保存', isSaving, children }) => (
  <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
    {children || (
      <>
        <button
          type="button"
          onClick={onCancel}
          disabled={isSaving}
          className="inline-flex h-11 items-center justify-center rounded-[16px] border border-white/80 bg-white/68 px-5 text-sm font-black text-slate-700 shadow-sm ring-1 ring-white/40 transition-all hover:-translate-y-0.5 hover:bg-white/88 disabled:opacity-45"
        >
          取消
        </button>
        {onSubmit && (
          <button
            type="button"
            onClick={onSubmit}
            disabled={isSaving}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-[16px] border border-slate-900/80 bg-[linear-gradient(180deg,#1f2937_0%,#020617_100%)] px-5 text-sm font-black text-white shadow-button shadow-brand-500/10 transition-all hover:-translate-y-0.5 hover:shadow-lg disabled:opacity-45"
          >
            {submitLabel}
          </button>
        )}
      </>
    )}
  </div>
);
