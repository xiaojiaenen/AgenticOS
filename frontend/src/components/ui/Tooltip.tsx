import React, { useId } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { cn } from '../../lib/utils';

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  side?: 'top' | 'bottom' | 'left' | 'right';
  className?: string;
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  side = 'top',
  className,
}) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const timeoutRef = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const tooltipId = useId();
  const prefersReduced = useReducedMotion();

  const show = () => {
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setIsOpen(true), 400);
  };

  const hide = () => {
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setIsOpen(false), 200);
  };

  const sideStyles: Record<string, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  const child = React.Children.only(children) as React.ReactElement;
  const trigger = React.cloneElement(child, {
    'aria-describedby': isOpen ? tooltipId : undefined,
    onMouseEnter: (e: React.MouseEvent) => { show(); child.props.onMouseEnter?.(e); },
    onMouseLeave: (e: React.MouseEvent) => { hide(); child.props.onMouseLeave?.(e); },
    onFocus: (e: React.FocusEvent) => { show(); child.props.onFocus?.(e); },
    onBlur: (e: React.FocusEvent) => { hide(); child.props.onBlur?.(e); },
    tabIndex: child.props.tabIndex ?? 0,
  } as React.HTMLAttributes<HTMLElement>);

  return (
    <div className="relative inline-flex">
      {trigger}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            id={tooltipId}
            role="tooltip"
            initial={prefersReduced ? { opacity: 1 } : { opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={prefersReduced ? { opacity: 0 } : { opacity: 0, scale: 0.92 }}
            transition={{ duration: prefersReduced ? 0 : 0.15 }}
            className={cn(
              'absolute z-50 px-3 py-1.5 rounded-xl bg-zinc-900 text-white text-xs font-bold shadow-lg pointer-events-none whitespace-nowrap',
              sideStyles[side],
              className,
            )}
          >
            {content}
            <div className={cn(
              'absolute w-2 h-2 bg-zinc-900 rotate-45',
              side === 'top' && 'bottom-[-4px] left-1/2 -translate-x-1/2',
              side === 'bottom' && 'top-[-4px] left-1/2 -translate-x-1/2',
              side === 'left' && 'right-[-4px] top-1/2 -translate-y-1/2',
              side === 'right' && 'left-[-4px] top-1/2 -translate-y-1/2',
            )} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
