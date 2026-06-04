import { motion } from 'motion/react';

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
}

export const Toggle = ({ checked, onChange, label, disabled }: ToggleProps) => {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2.5 text-sm font-bold text-slate-700 disabled:opacity-50"
    >
      {label && <span>{label}</span>}
      <span className="relative inline-flex h-6 w-11 items-center rounded-full bg-slate-200 transition-colors duration-200 data-[checked=true]:bg-emerald-500" data-checked={checked}>
        <motion.span
          animate={{ x: checked ? 20 : 2 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          className="inline-block h-4.5 w-4.5 rounded-full bg-white shadow-sm"
          style={{ width: 18, height: 18 }}
        />
      </span>
    </button>
  );
};
