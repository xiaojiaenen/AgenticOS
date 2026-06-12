import React, { useState } from 'react';
import { Sun, Droplets } from 'lucide-react';
import { useTheme, Theme } from '../../hooks/useTheme';
import { cn } from '../../lib/utils';
import { ThemeConfirmModal } from './ThemeConfirmModal';

interface ThemeToggleProps {
  variant?: 'icon' | 'full';
  className?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ variant = 'icon', className }) => {
  const { theme, setTheme } = useTheme();
  const [showConfirm, setShowConfirm] = useState(false);

  const handleToggle = () => {
    if (theme === 'liquid-glass') {
      setTheme('light');
    } else {
      setShowConfirm(true);
    }
  };

  const handleConfirm = () => {
    setShowConfirm(false);
    setTheme('liquid-glass');
  };

  const isGlass = theme === 'liquid-glass';
  const Icon = isGlass ? Droplets : Sun;
  const label = isGlass ? '液态玻璃' : '浅色模式';

  if (variant === 'icon') {
    return (
      <>
        <button
          type="button"
          onClick={handleToggle}
          className={cn(
            'flex items-center justify-center rounded-xl p-2 transition-all active:scale-90',
            isGlass
              ? 'text-sky-300 hover:text-sky-200 hover:bg-white/10'
              : 'text-slate-500 hover:bg-white/60 hover:text-slate-700 hover:shadow-sm',
            className,
          )}
          title={`当前：${label}，点击切换`}
          aria-label={`切换主题，当前：${label}`}
        >
          <Icon size={18} />
        </button>
        <ThemeConfirmModal
          open={showConfirm}
          onConfirm={handleConfirm}
          onCancel={() => setShowConfirm(false)}
        />
      </>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={handleToggle}
        className={cn(
          'flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-all active:scale-95',
          isGlass
            ? 'text-sky-300 hover:text-sky-200 hover:bg-white/10'
            : 'text-slate-500 hover:bg-white/60 hover:text-slate-700 hover:shadow-sm',
          className,
        )}
        aria-label={`切换主题，当前：${label}`}
      >
        <Icon size={14} />
        <span>{label}</span>
      </button>
      <ThemeConfirmModal
        open={showConfirm}
        onConfirm={handleConfirm}
        onCancel={() => setShowConfirm(false)}
      />
    </>
  );
};
