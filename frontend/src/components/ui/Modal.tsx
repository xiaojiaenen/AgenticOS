import React, { useEffect, useId, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Button } from './Button';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  maxWidth?: string;
  title?: string;
}

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  children,
  className,
  maxWidth = 'max-w-lg',
  title,
}) => {
  const id = useId();
  const titleId = `${id}-title`;
  const panelRef = useRef<HTMLDivElement>(null);

  // Focus trap
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') { onClose(); return; }
    if (e.key !== 'Tab' || !panelRef.current) return;

    const focusable = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE);
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus(); }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    document.addEventListener('keydown', handleKeyDown);
    // Auto-focus first focusable element
    requestAnimationFrame(() => {
      if (panelRef.current) {
        const first = panelRef.current.querySelector<HTMLElement>(FOCUSABLE);
        first?.focus();
      }
    });
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, handleKeyDown]);

  // Lock body scroll
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="admin-modal-shell"
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? titleId : undefined}
          onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ duration: 0.22 }}
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
      <h3 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">{title}</h3>
    </div>
    <button
      type="button"
      onClick={onClose}
      className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600"
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
        <Button variant="secondary" type="button" onClick={onCancel} disabled={isSaving}>
          取消
        </Button>
        {onSubmit && (
          <Button variant="primary" type="button" onClick={onSubmit} disabled={isSaving} isLoading={isSaving}>
            {submitLabel}
          </Button>
        )}
      </>
    )}
  </div>
);
