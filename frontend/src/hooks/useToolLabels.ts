/**
 * 工具名 → 中文标签的共享缓存。
 *
 * 对话页此前直接渲染内部工具名（read_text_file / write_text_file /
 * render_chart …），技术用户看得懂，但对业务用户等于乱码。标签的唯一来源
 * 是后端 TOOL_CATALOG，前端不复制一份，避免两边漂移。
 */
import { useEffect, useState } from 'react';
import { loadToolLabels, type ToolLabelMap } from '@/services/toolConfigService';

export type { ToolLabelMap };

const EMPTY: ToolLabelMap = {};

export function useToolLabels(): ToolLabelMap {
  const [labels, setLabels] = useState<ToolLabelMap>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    void loadToolLabels()
      .then((next) => {
        if (!cancelled) setLabels(next);
      })
      .catch(() => {
        // 标签只是展示增强，取不到就退回原始工具名。
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return labels;
}

/** 查不到中文标签时退回原始工具名，永不显示空白。 */
export function toolLabel(name: string, labels: ToolLabelMap): string {
  return labels[name] || name;
}
