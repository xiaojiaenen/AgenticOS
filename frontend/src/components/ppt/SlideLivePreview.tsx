import React, { useMemo } from 'react';
import { motion } from 'motion/react';
import { Presentation } from 'lucide-react';
import { Message } from '../../types';

function extractSvgPreviews(messages: Message[]): { slideNum: number; svg: string }[] {
  // 使用 Map 按 slideNum 去重，只保留每个页码最新的预览
  const previewMap = new Map<number, string>();

  for (const msg of messages) {
    if (!msg.toolCalls) continue;
    for (const tool of msg.toolCalls) {
      if (tool.name !== 'save_slide' || !tool.result) continue;
      const match = tool.result.match(/<svg_preview>([\s\S]*?)<\/svg_preview>/);
      if (match) {
        const svg = match[1];
        const slideMatch = tool.result.match(/第\s*(\d+)\s*页/);
        const slideNum = slideMatch ? parseInt(slideMatch[1], 10) : previewMap.size + 1;
        // 直接覆盖，保留最新的
        previewMap.set(slideNum, svg);
      }
    }
  }

  return Array.from(previewMap.entries())
    .map(([slideNum, svg]) => ({ slideNum, svg }))
    .sort((a, b) => a.slideNum - b.slideNum);
}

interface SlideLivePreviewProps {
  messages: Message[];
  isStreaming: boolean;
  hasArtifact: boolean;
}

export const SlideLivePreview: React.FC<SlideLivePreviewProps> = ({ messages, isStreaming, hasArtifact }) => {
  const previews = useMemo(() => extractSvgPreviews(messages), [messages]);

  // Only show during streaming when we have previews but no final artifact yet
  if (!isStreaming || previews.length === 0 || hasArtifact) return null;

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '35%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col overflow-hidden border-l border-slate-200/60 bg-white/60 backdrop-blur-xl"
    >
      <div className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-slate-200/80 bg-white/80 px-6 backdrop-blur-md">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-sky-500 text-white shadow-lg shadow-sky-500/20">
          <Presentation size={18} />
        </div>
        <div>
          <h2 className="text-sm font-bold leading-none text-slate-800">实时预览</h2>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">{previews.length} slides generating...</p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {previews.map(({ slideNum, svg }) => (
          <motion.div
            key={slideNum}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-md"
          >
            <div
              className="aspect-[16/9] overflow-hidden"
              dangerouslySetInnerHTML={{ __html: svg.replace(/<svg/, '<svg style="width:100%;height:100%"') }}
            />
            <div className="border-t border-slate-100 px-3 py-2 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-700">第 {slideNum} 页</span>
              <span className="text-[10px] font-medium text-emerald-600">已保存</span>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.aside>
  );
};
