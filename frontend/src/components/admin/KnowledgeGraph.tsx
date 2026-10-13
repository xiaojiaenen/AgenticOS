/**
 * 知识库管理：知识图谱面板。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { useQuery } from '@tanstack/react-query';
import { Database, Loader2 } from 'lucide-react';
import { ErrorBanner } from './shared';
import { Button } from '@/components/shadcn/button';
import { getKnowledgeGraph, type KnowledgeGraphData } from '@/services/knowledgeService';

export function KnowledgeGraph({ kbId }: { kbId: number }) {
  const graphQuery = useQuery({
    queryKey: ['admin', 'kb-graph', kbId],
    queryFn: () => getKnowledgeGraph(kbId),
    retry: 0,
  });

  if (graphQuery.isPending) {
    return (
      <div className="flex items-center justify-center py-16 text-[var(--muted-foreground)]">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (graphQuery.isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <ErrorBanner message={(graphQuery.error as Error).message || '知识图谱加载失败'} />
        <Button variant="outline" size="sm" onClick={() => void graphQuery.refetch()}>
          重试
        </Button>
      </div>
    );
  }

  const data: KnowledgeGraphData = graphQuery.data;
  const nodes = data.nodes || [];
  const edges = data.edges || [];

  if (nodes.length === 0) {
    return (
      <div className="py-12 text-center text-sm font-medium text-[var(--muted-foreground)]">
        <Database className="mx-auto mb-3 h-10 w-10 opacity-40" />
        暂无知识图谱数据
      </div>
    );
  }

  const width = 600;
  const height = 400;
  const positionedNodes = nodes.map((node, i) => ({
    ...node,
    x: width / 2 + Math.cos((i / nodes.length) * Math.PI * 2) * 150,
    y: height / 2 + Math.sin((i / nodes.length) * Math.PI * 2) * 150,
  }));
  const nodeMap = new Map(positionedNodes.map((n) => [n.id, n]));

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        {edges.map((edge, i) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return null;
          return (
            <line
              key={i}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={edge.type === 'contradicts' ? '#ef4444' : '#a1a1aa'}
              strokeWidth={edge.type === 'contradicts' ? 2 : 1}
              strokeDasharray={edge.type === 'reference' ? '4 4' : undefined}
              opacity={0.6}
            />
          );
        })}
        {positionedNodes.map((node) => (
          <g key={node.id}>
            <circle
              cx={node.x}
              cy={node.y}
              r={node.authority === 'L3' ? 20 : node.authority === 'L2' ? 16 : 12}
              fill={node.authority === 'L3' ? '#4f46e5' : node.authority === 'L2' ? '#8b5cf6' : '#a1a1aa'}
              opacity={0.85}
            />
            <text x={node.x} y={node.y + 30} textAnchor="middle" fill="#52525b" fontSize={10}>
              {node.label.length > 10 ? node.label.slice(0, 10) + '...' : node.label}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-4 flex gap-4 text-xs font-medium text-[var(--muted-foreground)]">
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-zinc-900" /> L3 锁定</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-violet-500" /> L2 已审核</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-zinc-400" /> L1 自动</span>
      </div>
    </div>
  );
}
