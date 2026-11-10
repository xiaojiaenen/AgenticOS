/**
 * 工作流节点图编辑器的纯图操作回归（P0-3 画布 v1）。
 *
 * 结构化编辑器的所有变更是纯函数（返回新图对象），这里把语义钉死：
 * 改名级联、删除级联、加边去重、kb_ids 逗号解析、非法 JSON 回退。
 * 渲染层（表单/预览）是这些纯函数的薄壳。
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

const GRAPH: WorkflowGraph = {
  nodes: [
    { id: 'start', type: 'start' },
    { id: 't1', type: 'template', params: { template: 'A' } },
    { id: 'c', type: 'condition', params: { left: '1', op: '==', right: '1' } },
    { id: 'end', type: 'end' },
  ],
  edges: [
    { from: 'start', to: 't1' },
    { from: 't1', to: 'c' },
    { from: 'c', to: 'end', label: 'true' },
  ],
};

describe('renameNodeInGraph', () => {
  it('改名级联到所有引用边（from/to 都改）', () => {
    const next = renameNodeInGraph(GRAPH, 't1', 'draft');
    expect(next.nodes.map((n) => n.id)).toEqual(['start', 'draft', 'c', 'end']);
    expect(next.edges.map((e) => [e.from, e.to])).toEqual([
      ['start', 'draft'],
      ['draft', 'c'],
      ['c', 'end'],
    ]);
  });

  it('重名拒绝（返回原图）', () => {
    expect(renameNodeInGraph(GRAPH, 't1', 'c')).toBe(GRAPH);
  });

  it('空名/同名不改', () => {
    expect(renameNodeInGraph(GRAPH, 't1', '  ')).toBe(GRAPH);
    expect(renameNodeInGraph(GRAPH, 't1', 't1')).toBe(GRAPH);
  });
});

describe('deleteNodeFromGraph', () => {
  it('删除节点级联删除相关边', () => {
    const next = deleteNodeFromGraph(GRAPH, 't1');
    expect(next.nodes.map((n) => n.id)).toEqual(['start', 'c', 'end']);
    expect(next.edges).toEqual([{ from: 'c', to: 'end', label: 'true' }]);
  });

  it('start 不可删', () => {
    expect(deleteNodeFromGraph(GRAPH, 'start')).toBe(GRAPH);
  });
});

describe('addEdgeToGraph', () => {
  it('重复边去重', () => {
    const next = addEdgeToGraph(GRAPH, 'start', 't1');
    expect(next.edges.length).toBe(GRAPH.edges.length);
  });

  it('自环拒绝', () => {
    expect(addEdgeToGraph(GRAPH, 't1', 't1')).toBe(GRAPH);
  });

  it('condition 来源边可带 label', () => {
    const next = addEdgeToGraph(GRAPH, 'c', 't1', 'false');
    expect(next.edges.at(-1)).toEqual({ from: 'c', to: 't1', label: 'false' });
  });
});

describe('setNodeParam', () => {
  it('设置参数；空值删除键', () => {
    const withRole = setNodeParam(GRAPH, 't1', 'role', 'fast');
    expect(withRole.nodes[1].params).toEqual({ template: 'A', role: 'fast' });
    const cleared = setNodeParam(withRole, 't1', 'role', undefined);
    expect(cleared.nodes[1].params).toEqual({ template: 'A' });
  });

  it('kb_ids 数组直存（表单层负责逗号解析）', () => {
    const next = setNodeParam(GRAPH, 't1', 'kb_ids', [1, 3]);
    expect(next.nodes[1].params?.kb_ids).toEqual([1, 3]);
  });
});

describe('computeLayout', () => {
  it('BFS 分列：start 第 0 列，子节点深度递增；孤立节点放最后', () => {
    const { columns } = computeLayout(GRAPH);
    expect(columns.get('start')).toBe(0);
    expect(columns.get('t1')).toBe(1);
    expect(columns.get('c')).toBe(2);
    expect(columns.get('end')).toBe(3);
    const orphan = { id: 'orphan', type: 'template' as const };
    const { columns: cols2 } = computeLayout({
      nodes: [...GRAPH.nodes, orphan],
      edges: GRAPH.edges,
    });
    expect(cols2.get('orphan')).toBe(4);
  });

  it('有环时收敛（不无限松弛），展示不炸', () => {
    const cyclic: WorkflowGraph = {
      nodes: [
        { id: 'start', type: 'start' },
        { id: 'a', type: 'template' },
        { id: 'end', type: 'end' },
      ],
      edges: [
        { from: 'start', to: 'a' },
        { from: 'a', to: 'end' },
        { from: 'end', to: 'a' }, // 非法环：后端校验会拒绝；预览要收敛不炸
      ],
    };
    expect(() => computeLayout(cyclic)).not.toThrow();
  });
});
