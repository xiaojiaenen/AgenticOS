import { createPortal } from 'react-dom';
import { motion } from 'motion/react';
import { AlertTriangle, X } from 'lucide-react';
import { Button } from './Button';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
  danger?: boolean;
}

export const ConfirmDialog = ({ open, title, message, onConfirm, onCancel, confirmLabel = '确认', danger = false }: ConfirmDialogProps) => {
  if (!open) return null;

  return createPortal(
    <div className="admin-modal-shell" onMouseDown={onCancel}>
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.96 }}
        transition={{ duration: 0.22 }}
        onMouseDown={e => e.stopPropagation()}
        className="admin-solid-panel admin-modal-panel w-full max-w-sm p-6"
      >
        <div className="flex items-start gap-3">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${danger ? 'bg-rose-50 text-rose-500' : 'bg-amber-50 text-amber-500'}`}>
            <AlertTriangle size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-black text-slate-900">{title}</h3>
            <p className="mt-1.5 text-sm text-slate-500">{message}</p>
          </div>
          <button type="button" onClick={onCancel} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600">
            <X size={16} />
          </button>
        </div>
        <div className="mt-5 flex justify-end gap-2.5">
          <Button variant="secondary" size="sm" onClick={onCancel}>取消</Button>
          <Button variant={danger ? 'primary' : 'primary'} size="sm" onClick={onConfirm} className={danger ? 'bg-rose-600 hover:bg-rose-700' : ''}>{confirmLabel}</Button>
        </div>
      </motion.div>
    </div>,
    document.body
  );
};
