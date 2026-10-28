import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { localizeError } from '../../lib/errors';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  /** 标题，默认「页面出错了」 */
  title?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
          <div className="flex size-12 items-center justify-center rounded-2xl border border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300">
            <AlertTriangle size={22} className="shrink-0" />
          </div>
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--foreground)]">
            {this.props.title ?? '页面出错了'}
          </h2>
          {/* 错误消息走本地化：原始 message 可能是英文异常或技术堆栈，
              直接甩给终端用户既看不懂也暴露实现细节。 */}
          <p className="max-w-md text-sm leading-relaxed text-[var(--muted-foreground)]">
            {localizeError(this.state.error, '这个区域加载失败，可以重试或返回上一页')}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition-all hover:opacity-90 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
          >
            <RefreshCw size={14} className="shrink-0" />
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * 行内错误兜底（用于聊天消息等局部区域）。
 *
 * 之前只有亮色配色（`bg-red-50 text-red-700`），暗色主题下是刺眼白底红块。
 */
export function InlineErrorFallback({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300">
      <AlertTriangle size={14} className="shrink-0" />
      <span className="shrink-0">渲染失败</span>
      {error ? (
        <span className="max-w-[220px] truncate text-xs text-red-600 dark:text-red-300/80">
          {error}
        </span>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="ml-auto shrink-0 text-xs font-semibold text-red-700 underline underline-offset-2 hover:text-red-800 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)] dark:text-red-300"
        >
          重试
        </button>
      ) : null}
    </div>
  );
}
