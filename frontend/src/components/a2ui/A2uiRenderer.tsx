/**
 * A2UI 渲染器 —— 把智能体生成的声明式 UI 渲染成原生 React 组件。
 *
 * 为什么引入 A2UI：现在智能体只能回文本或固定几种产物（PPT / 网站 / 表格）。
 * 用户问「给我一个筛选表单」「画个对比表」，只能靠模型输出 Markdown 或
 * HTML —— 前者没有交互，后者是执行代码，安全边界差。
 *
 * A2UI 的取舍正好补这一块：智能体发的是**声明式组件描述**（JSON），
 * 客户端用自己受控的组件库渲染。没有任意代码执行，组件集合由我们决定。
 *
 * 协议版本：v0.9（当前 stable）。v1.0 还是 candidate，等它稳定再迁。
 */
import { useEffect, useMemo, useState } from 'react';
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import { basicCatalog } from '@a2ui/web_core/v0_9/basic_catalog';
import { A2uiSurface } from '@a2ui/react/v0_9';
import { AlertCircle, Loader2 } from 'lucide-react';

/** 一条 A2UI 消息。结构由协议定义，这里只约束外层判别字段。 */
export type A2uiMessage = Record<string, unknown>;

export interface A2uiRendererProps {
  /** 智能体下发的消息序列（createSurface → updateComponents → updateDataModel） */
  messages: A2uiMessage[];
  /** 用户点击组件触发的动作，回传给智能体 */
  onAction?: (action: Record<string, unknown>) => void;
  className?: string;
}

/**
 * A2UI 消息渲染器。
 *
 * 设计要点：
 * - **消息是流式的**：智能体可能先 createSurface，再逐批 updateComponents。
 *   这里用 useMemo 按 messages 的引用重建 processor —— 消息数很少（通常
 *   < 20 条），重建成本远低于维护增量合并的复杂度。
 * - **动作回传**：用户点击 Button 等交互组件时，A2UI 会调 actionHandler。
 *   我们把动作交给上层，由上层决定是否发给智能体（通常是发一条新消息）。
 * - **渲染失败不炸整个对话**：A2UI 消息来自模型，格式可能不合规。捕获异常
 *   后降级成一条错误提示，而不是让整条消息流崩掉。
 */
export function A2uiRenderer({ messages, onAction, className }: A2uiRendererProps) {
  const [error, setError] = useState<string | null>(null);
  const [surfaces, setSurfaces] = useState<unknown[]>([]);

  // 用消息内容的 JSON 作为依赖：上层可能每次 render 都传新数组引用，
  // 直接依赖引用会导致无限重建。
  const messagesKey = useMemo(() => {
    try {
      return JSON.stringify(messages);
    } catch {
      return '';
    }
  }, [messages]);

  const processor = useMemo(() => {
    if (!messagesKey) return null;
    try {
      const parsed: A2uiMessage[] = JSON.parse(messagesKey);
      const p = new MessageProcessor([basicCatalog], (action) => {
        onAction?.(action as Record<string, unknown>);
      });
      p.processMessages(parsed as never);
      return p;
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      return null;
    }
    // onAction 变化不该重建 processor（会丢失已渲染的 surface）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messagesKey]);

  useEffect(() => {
    if (!processor) {
      setSurfaces([]);
      return;
    }
    const sync = () => {
      setSurfaces(Array.from(processor.model.surfacesMap.values()));
    };
    sync();
    const created = processor.onSurfaceCreated(sync);
    const deleted = processor.onSurfaceDeleted(sync);
    return () => {
      created.unsubscribe();
      deleted.unsubscribe();
    };
  }, [processor]);

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200"
      >
        <AlertCircle size={14} className="mt-0.5 shrink-0" />
        <span className="min-w-0 break-words">
          界面渲染失败：{error}
          <span className="mt-0.5 block opacity-75">
            这是智能体下发的界面描述格式不对，不影响对话本身。
          </span>
        </span>
      </div>
    );
  }

  if (!processor) {
    return (
      <div className="flex items-center gap-2 py-2 text-xs text-[var(--muted-foreground)]">
        <Loader2 size={13} className="animate-spin" />
        正在准备界面…
      </div>
    );
  }

  if (surfaces.length === 0) {
    return null;
  }

  return (
    <div className={className ?? 'a2ui-container space-y-3'}>
      {surfaces.map((surface) => (
        <A2uiSurface key={(surface as { id: string }).id} surface={surface as never} />
      ))}
    </div>
  );
}
