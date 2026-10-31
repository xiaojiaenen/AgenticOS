/**
 * 图表消息渲染器。
 *
 * render_chart 工具现在把图表作为独立消息推给前端（不再是"让模型
 * 复述一段标记文本"）。这里把它渲染成卡片 + ECharts 图表，
 * 复用已有的 EChartsBlock（与 Markdown 里的 ```echarts 代码块同一套实现）。
 *
 * 为什么要单独成组件：图表不是 A2UI 组件树的一部分，
 * 把它塞进 MessageProcessor 会被当成非法组件丢掉。
 */
import { useMemo } from 'react';
import { EChartsBlock } from '../chat/ChatMessageSubComponents';

export interface ChartMessagePayload {
  title?: string;
  option: unknown;
}

export function ChartMessage({ chart }: { chart: ChartMessagePayload }) {
  const optionJson = useMemo(() => {
    try {
      return JSON.stringify(chart.option ?? {});
    } catch {
      return '{}';
    }
  }, [chart.option]);

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3">
      {chart.title ? (
        <div className="mb-2 text-xs font-medium text-[var(--muted-foreground)]">
          {chart.title}
        </div>
      ) : null}
      <EChartsBlock optionJson={optionJson} />
    </div>
  );
}
