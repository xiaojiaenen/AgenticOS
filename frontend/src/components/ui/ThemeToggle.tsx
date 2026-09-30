import React from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme, Theme } from '../../hooks/useTheme';
import { cn } from '../../lib/utils';

interface ThemeToggleProps {
  variant?: 'icon' | 'full';
  className?: string;
}

const THEME_META: Record<Theme, { icon: React.ComponentType<{ size?: number }>; label: string }> = {
  light: { icon: Sun, label: '浅色模式' },
  dark: { icon: Moon, label: '深色模式' },
  system: { icon: Monitor, label: '跟随系统' },
};

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ variant = 'icon', className }) => {
  const { theme, toggleTheme } = useTheme();
  const meta = THEME_META[theme];
  const Icon = meta.icon;
  const label = meta.label;

  if (variant === 'icon') {
    return (
      <button
        type="button"
        onClick={toggleTheme}
        className={cn(
          'flex items-center justify-center rounded-xl p-2 transition-all active:scale-90',
          'text-slate-500 hover:bg-white/60 hover:text-slate-700 hover:shadow-sm',
          className,
        )}
        title={`当前：${label}，点击切换`}
        aria-label={`切换主题，当前：${label}`}
      >
        <Icon size={18} />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={cn(
        'flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-all active:scale-95',
        'text-slate-500 hover:bg-white/60 hover:text-slate-700 hover:shadow-sm',
        className,
      )}
      aria-label={`切换主题，当前：${label}`}
    >
      <Icon size={14} />
      <span>{label}</span>
    </button>
  );
};
