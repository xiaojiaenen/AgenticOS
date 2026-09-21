import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
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
        <div className="flex flex-col items-center justify-center p-8 text-center">
          <div className="mb-4 text-4xl">⚠️</div>
          <h2 className="mb-2 text-lg font-medium text-slate-700">组件渲染出错</h2>
          <p className="mb-4 text-sm text-slate-500">
            {this.state.error?.message || '发生了未知错误'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 transition-colors"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Inline error fallback for chat messages
export function InlineErrorFallback({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      <span>渲染失败</span>
      {error && <span className="text-red-500 truncate max-w-[200px]">{error}</span>}
      {onRetry && (
        <button onClick={onRetry} className="ml-auto text-red-600 hover:text-red-800 underline text-xs">
          重试
        </button>
      )}
    </div>
  );
}
