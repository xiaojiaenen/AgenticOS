/**
 * 拖拽画布的数据往返：node.position 是**展示字段**，不能影响校验/执行。
 *
 * 画布拖拽后会把位置写回 graph.nodes[].position。后端校验只认
 * id/type/params 与 edges —— 本测试对比「同一份图带/不带 position」下
 * 前端的纯函数行为是否完全一致，并通过 python 端校验器间接确认
 * （前端只保证结构不丢字段）。
 */
import { describe, expect, it } from 'vitest';
import {
  addEdgeToGraph,
  computeLayout,
  deleteNodeFromGraph,
  renameNodeInGraph,
  setNodeParam,
} from '../WorkflowGraphEditor';
import type { WorkflowGraph } from '@/services/workflowService';

type PositionedNode = WorkflowGraph['nodes'][number] & { position?: { x: number; y: number } };

const BASE: WorkflowGraph = {
  nodes: [
    { id: 'start', type: 'start' },
    { id: 't', type: 'template', params: { template: 'A' } },
    { id: 'end', type: 'end' },
  ],
  edges: [
    { from: 'start', to: 't' },
    { from: 't', to: 'end' },
  ],
};

const POSITIONED: WorkflowGraph = {
  nodes: BASE.nodes.map((n, i) => ({ ...n, position: { x: 100 + i * 200, y: 50 } }) as PositionedNode),
  edges: BASE.edges,
};

const stripPositions = (g: WorkflowGraph): WorkflowGraph => ({
  ...g,
  nodes: g.nodes.map(({ ...n }) => {
    const { position, ...rest } = n as PositionedNode;
    void position;
    return rest as WorkflowGraph['nodes'][number];
  }),
});

describe('画布位置字段不影响图操作语义', () => {
  it('改名/删除/加边/改参 在带位置与不带位置两种图上结果一致（除位置本身）', () => {
    const ops: Array<(g: WorkflowGraph) => WorkflowGraph> = [
      (g) => renameNodeInGraph(g, 't', 'draft'),
      (g) => deleteNodeFromGraph(g, 't'),
      (g) => addEdgeToGraph(g, 'start', 'end'),
      (g) => setNodeParam(g, 't', 'role', 'fast'),
    ];
    for (const op of ops) {
      expect(stripPositions(op(POSITIONED))).toEqual(op(BASE));
    }
  });

  it('带位置的图仍能被自动布局（列深度不受 position 影响）', () => {
    const a = computeLayout(BASE).columns;
    const b = computeLayout(POSITIONED).columns;
    expect([...a.entries()]).toEqual([...b.entries()]);
  });

  it('删除节点时位置字段一并删除（不留下孤儿位置）', () => {
    const next = deleteNodeFromGraph(POSITIONED, 't') as { nodes: PositionedNode[] };
    expect(next.nodes.map((n) => n.id)).toEqual(['start', 'end']);
    expect(next.nodes.every((n) => n.position != null)).toBe(true);
  });
});
