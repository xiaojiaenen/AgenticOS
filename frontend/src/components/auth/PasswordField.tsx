import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { Input } from '@/components/shadcn/input';
import { cn } from '@/lib/utils';

/**
 * 认证表单专用密码输入框（shadcn Input + 显示/隐藏切换）。
 * 替代旧 components/ui/PasswordInput。
 */
export function PasswordField({
  className,
  ...props
}: Omit<React.ComponentProps<'input'>, 'type'>) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        type={show ? 'text' : 'password'}
        className={cn('pr-10', className)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-[var(--muted-foreground)] transition-colors hover:text-zinc-600"
        aria-label={show ? '隐藏密码' : '显示密码'}
        tabIndex={-1}
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}
