import React, { useState } from 'react';
import { Sun, Moon, Monitor, Droplets } from 'lucide-react';
import { useTheme, Theme } from '../../hooks/useTheme';
import { cn } from '../../lib/utils';
import { ThemeConfirmModal } from './ThemeConfirmModal';

const themeConfig: Record<Theme, { icon: React.ElementType; label: string }> = {
  light: { icon: Sun, label: '浅色模式' },
  dark: { icon: Moon, label: '深色模式' },
  'liquid-glass': { icon: Droplets, label: '液态玻璃' },
  system: { icon: Monitor, label: '跟随系统' },
};

interface ThemeToggleProps {
  variant?: 'icon' | 'full';
  className?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ variant = 'icon', className }) => {
  const { theme, setTheme, toggleTheme } = useTheme();
  const [showConfirm, setShowConfirm] = useState(false);

  // Override toggleTheme to intercept liquid-glass transition
  const handleToggle = () => {
    const order: Theme[] = ['light', 'dark', 'liquid-glass', 'system'];
    const idx = order.indexOf(theme);
    const nextTheme = order[(idx + 1) % order.length];

    if (nextTheme === 'liquid-glass') {
      setShowConfirm(true);
      return;
    }
    toggleTheme();
  };

  const handleConfirm = () => {
    setShowConfirm(false);
    setTheme('liquid-glass');
  };

  const { icon: Icon, label } = themeConfig[theme] ?? themeConfig.system;

  if (variant === 'icon') {
    return (
      <>
        <button
          type="button"
          onClick={handleToggle}
          className={cn(
            'flex items-center justify-center rounded-xl p-2 text-slate-500 transition-all hover:bg-white/60 hover:text-slate-700 hover:shadow-sm active:scale-90',
            theme === 'liquid-glass' && 'text-brand-600 hover:text-brand-700 hover:bg-white/10',
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
          'flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold text-slate-500 transition-all hover:bg-white/60 hover:text-slate-700 hover:shadow-sm active:scale-95',
          theme === 'liquid-glass' && 'text-sky-300 hover:text-sky-200 hover:bg-white/10',
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
