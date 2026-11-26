import dagre from '@dagrejs/dagre';
import type { Edge } from '@xyflow/react';
import type { StudioNode, ArtworkData } from '../stores/canvasStore';

/**
 * 使用 @dagrejs/dagre 对画布节点与衍生连线执行有向图自动布局。
 * - direction = 'LR': 从左到右展开 AI 衍生演进树（推荐）
 * - direction = 'TB': 从上到下展开
 */
export function layoutCanvasGraph(
  nodes: StudioNode[],
  edges: Edge[],
  direction: 'LR' | 'TB' = 'LR',
): StudioNode[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: direction,
    nodesep: 56,
    ranksep: 120,
    marginx: 48,
    marginy: 48,
  });

  nodes.forEach((node) => {
    const w = node.data.kind === 'artwork' ? (node.data as ArtworkData).nodeW : 248;
    const h = node.data.kind === 'artwork' ? (node.data as ArtworkData).nodeH : 168;
    g.setNode(node.id, { width: w, height: h });
  });

  edges.forEach((edge) => {
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  });

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    if (!pos) return node;
    const w = node.data.kind === 'artwork' ? (node.data as ArtworkData).nodeW : 248;
    const h = node.data.kind === 'artwork' ? (node.data as ArtworkData).nodeH : 168;
    return {
      ...node,
      position: {
        x: Math.round(pos.x - w / 2),
        y: Math.round(pos.y - h / 2),
      },
    };
  });
}
