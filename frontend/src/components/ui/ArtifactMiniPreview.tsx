import React from 'react';

export type MiniPreviewKind = 'ppt' | 'website' | 'office' | 'sheet' | 'report' | 'document';

/**
 * 原版原型（agenticos.html）同款产物缩略矢量图：
 * - ppt：暖橙柱状+趋势折线（16:9 SVG）
 * - website：天蓝响应窗口卡片（红黄绿三点）
 * - office / sheet：翠绿数据表格与公式高亮（=SUM()）
 * - report / document：淡紫知识图谱动态节点（RAG）
 */
export const ArtifactMiniPreview: React.FC<{ kind: MiniPreviewKind }> = ({ kind }) => {
  if (kind === 'ppt') {
    return (
      <div
        className="flex h-full w-full flex-col justify-between p-3"
        style={{ background: 'linear-gradient(135deg, rgba(251,146,60,0.14), rgba(255,255,255,0.02))' }}
      >
        <div className="flex items-center justify-between">
          <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold text-white" style={{ background: '#EA580C' }}>
            PPT
          </span>
          <span className="font-mono text-[10px] text-[var(--muted-foreground)]">16:9 SVG</span>
        </div>
        <svg className="h-11 w-full" viewBox="0 0 140 44" fill="none" aria-hidden="true">
          <rect x="6" y="24" width="16" height="16" rx="3" fill="#EA580C" fillOpacity="0.28" />
          <rect x="28" y="16" width="16" height="24" rx="3" fill="#EA580C" fillOpacity="0.48" />
          <rect x="50" y="20" width="16" height="20" rx="3" fill="#EA580C" fillOpacity="0.38" />
          <rect x="72" y="6" width="16" height="34" rx="3" fill="#EA580C" />
          <path
            d="M14 20 L36 12 L58 16 L80 4 L126 10"
            stroke="#EA580C"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="aos-svg-sparkline"
          />
          <circle cx="80" cy="4" r="3" fill="#EA580C">
            <animate attributeName="r" values="2.5;4;2.5" dur="2.4s" repeatCount="indefinite" />
          </circle>
        </svg>
      </div>
    );
  }

  if (kind === 'website') {
    return (
      <div
        className="flex h-full w-full flex-col justify-between p-3"
        style={{ background: 'linear-gradient(135deg, rgba(56,189,248,0.15), rgba(255,255,255,0.02))' }}
      >
        <div className="flex items-center justify-between">
          <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold text-white" style={{ background: '#0284C7' }}>
            网站
          </span>
          <span className="flex gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
        </div>
        <svg className="h-11 w-full" viewBox="0 0 140 44" fill="none" aria-hidden="true">
          <rect x="4" y="4" width="84" height="34" rx="6" fill="#0284C7" fillOpacity="0.14" stroke="#0284C7" strokeOpacity="0.28" />
          <rect x="12" y="12" width="44" height="5" rx="2.5" fill="#0284C7" fillOpacity="0.6" />
          <rect x="12" y="21" width="62" height="3.5" rx="1.75" fill="#0284C7" fillOpacity="0.28" />
          <rect x="94" y="4" width="42" height="15" rx="5" fill="#0284C7" fillOpacity="0.22" />
          <rect x="94" y="23" width="42" height="15" rx="5" fill="#0284C7" fillOpacity="0.1" />
        </svg>
      </div>
    );
  }

  if (kind === 'office' || kind === 'sheet') {
    return (
      <div
        className="flex h-full w-full flex-col justify-between p-3"
        style={{ background: 'linear-gradient(135deg, rgba(52,211,153,0.15), rgba(255,255,255,0.02))' }}
      >
        <div className="flex items-center justify-between">
          <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold text-white" style={{ background: '#059669' }}>
            表格
          </span>
          <span className="font-mono text-[10px] text-[var(--muted-foreground)]">=SUM()</span>
        </div>
        <svg className="h-11 w-full" viewBox="0 0 140 44" fill="none" aria-hidden="true">
          <rect x="4" y="5" width="40" height="10" rx="3" fill="#059669" fillOpacity="0.28" />
          <rect x="48" y="5" width="42" height="10" rx="3" fill="#059669" fillOpacity="0.16" />
          <rect x="94" y="5" width="42" height="10" rx="3" fill="#059669" fillOpacity="0.16" />
          <rect x="4" y="19" width="40" height="10" rx="3" fill="#059669" fillOpacity="0.14" />
          <rect x="48" y="19" width="42" height="10" rx="3" fill="#059669" fillOpacity="0.22" />
          <rect x="94" y="19" width="42" height="10" rx="3" fill="#059669" fillOpacity="0.65">
            <animate attributeName="fill-opacity" values="0.45;0.9;0.45" dur="2.8s" repeatCount="indefinite" />
          </rect>
        </svg>
      </div>
    );
  }

  return (
    <div
      className="flex h-full w-full flex-col justify-between p-3"
      style={{ background: 'linear-gradient(135deg, rgba(167,139,250,0.15), rgba(255,255,255,0.02))' }}
    >
      <div className="flex items-center justify-between">
        <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold text-white" style={{ background: '#7C3AED' }}>
          图谱
        </span>
        <span className="font-mono text-[10px] text-[var(--muted-foreground)]">RAG</span>
      </div>
      <svg className="h-11 w-full" viewBox="0 0 140 44" fill="none" aria-hidden="true">
        <line x1="22" y1="24" x2="70" y2="12" stroke="#7C3AED" strokeOpacity="0.45" strokeWidth="1.5" className="aos-svg-flow" />
        <line x1="70" y1="12" x2="118" y2="26" stroke="#7C3AED" strokeOpacity="0.45" strokeWidth="1.5" className="aos-svg-flow" />
        <line x1="22" y1="24" x2="74" y2="34" stroke="#7C3AED" strokeOpacity="0.32" strokeWidth="1.5" />
        <circle cx="22" cy="24" r="4.5" fill="#7C3AED" fillOpacity="0.55" />
        <circle cx="70" cy="12" r="6.5" fill="#7C3AED">
          <animate attributeName="r" values="5.5;7.2;5.5" dur="3s" repeatCount="indefinite" />
        </circle>
        <circle cx="118" cy="26" r="4.5" fill="#7C3AED" fillOpacity="0.65" />
        <circle cx="74" cy="34" r="3.5" fill="#7C3AED" fillOpacity="0.45" />
      </svg>
    </div>
  );
};
