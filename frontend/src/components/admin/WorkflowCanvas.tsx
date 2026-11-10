/**
 * 工作流拖拽画布（基于 @xyflow/react / React Flow v12）。
 *
 * 与 `WorkflowGraphEditor.tsx` 的分工：
 * - 本文件是**画布渲染 + 交互层**：拖拽节点（位置只影响展示，落库为
 *   graph.nodes[].position）、连边拖拽、缩放平移、小地图、节点侧栏编辑；
 * - 数据操作仍然复用 `WorkflowGraphEditor.tsx` 里被单测钉住的纯函数
 *   （renameNodeInGraph / deleteNodeFromGraph / addEdgeToGraph / setNodeParam /
 *   computeLayout），保证画布与结构化表单**行为完全一致**。
 *
 * 布局持久化：node.position 是可选的展示字段 —— 后端校验只认 id/type/params
 * 与 edges，多一个 position 不影响校验与执行；没有 position 时按 BFS 自动
 * 布局（老图打开即整齐）。
 */
import * as React from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { cn } from '@/lib/utils';
import type { WorkflowGraph, WorkflowGraphEdge, WorkflowGraphNode } from '@/services/workflowService';
import {
  NODE_PARAM_FIELDS,
  NODE_TYPES,
  TYPE_COLORS,
  TYPE_LABELS,
  addEdgeToGraph,
  computeLayout,
  deleteNodeFromGraph,
  renameNodeInGraph,
  setNodeParam,
} from './WorkflowGraphEditor';

/* ------------------------------------------------------------------ */
/* 节点外观                                                             */
/* ------------------------------------------------------------------ */

const NODE_WIDTH = 176;
const NODE_HEIGHT = 46;

type WfNodeData = {
  nodeId: string;
  nodeType: string;
  summary: string;
};

function paramSummary(node: WorkflowGraphNode): string {
  const p = node.params ?? {};
  const first = ['prompt', 'query', 'url', 'template', 'left', 'output'] as const;
  for (const key of first) {
    const v = p[key];
    if (typeof v === 'string' && v.trim()) {
      const one = v.replace(/\s+/g, ' ').trim();
      return one.length > 30 ? `${one.slice(0, 29)}…` : one;
    }
  }
  return '';
}

function WorkflowNodeView({ data, selected }: NodeProps<Node<WfNodeData>>) {
  const isStart = data.nodeType === 'start';
  const isEnd = data.nodeType === 'end';
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg border bg-[var(--surface-1)] px-2.5 py-1.5',
        'border-[var(--border-subtle)] shadow-sm transition-shadow',
        selected && 'border-[var(--brand,#2b87c2)] shadow-md',
      )}
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
    >
      {!isStart ? (
        <Handle
          type="target"
          position={Position.Left}
          aria-label={`${data.nodeId} 的输入连接点`}
          className="!size-2 !bg-[var(--muted-foreground)]"
        />
      ) : null}
      <span
        className={cn(
          'inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[10px] font-semibold text-white',
          TYPE_COLORS[data.nodeType] ?? 'bg-slate-400',
        )}
      >
        {TYPE_LABELS[data.nodeType] ?? data.nodeType}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[11px] font-semibold text-[var(--foreground)]">
          {data.nodeId}
        </span>
        {data.summary ? (
          <span className="block truncate text-[10px] text-[var(--muted-foreground)]">
            {data.summary}
          </span>
        ) : null}
      </span>
      {!isEnd ? (
        <Handle
          type="source"
          position={Position.Right}
          aria-label={`${data.nodeId} 的输出连接点`}
          className="!size-2 !bg-[var(--muted-foreground)]"
        />
      ) : null}
    </div>
  );
}

const nodeTypes = { workflowNode: WorkflowNodeView };

/* ------------------------------------------------------------------ */
/* 图 ⇄ React Flow 转换                                                 */
/* ------------------------------------------------------------------ */

const EDGE_COLOR_DEFAULT = '#94a3b8';
const EDGE_COLOR_TRUE = '#10b981';
const EDGE_COLOR_FALSE = '#f43f5e';

function edgeStyle(label?: string) {
  const color =
    label === 'true' ? EDGE_COLOR_TRUE : label === 'false' ? EDGE_COLOR_FALSE : EDGE_COLOR_DEFAULT;
  return { stroke: color, strokeWidth: 1.6 };
}

/** 节点位置：优先用已存的 position，否则按 BFS 列自动排。 */
function resolvePositions(graph: WorkflowGraph): Map<string, { x: number; y: number }> {
  const { columns } = computeLayout(graph);
  const byCol = new Map<number, string[]>();
  for (const n of graph.nodes) {
    const c = columns.get(n.id) ?? 0;
    byCol.set(c, [...(byCol.get(c) ?? []), n.id]);
  }
  const out = new Map<string, { x: number; y: number }>();
  for (const [col, ids] of byCol) {
    ids.forEach((id, row) => {
      out.set(id, { x: 40 + col * 236, y: 40 + row * 84 });
    });
  }
  const stored = new Map(
    (graph.nodes as Array<WorkflowGraphNode & { position?: { x: number; y: number } }>)
      .filter((n) => n.position && Number.isFinite(n.position.x) && Number.isFinite(n.position.y))
      .map((n) => [n.id, n.position!] as const),
  );
  // 已存储的位置优先（用户手动摆过的图不被自动布局覆盖）
  for (const [id, pos] of stored) out.set(id, pos);
  return out;
}

function toFlowNodes(graph: WorkflowGraph, positions: Map<string, { x: number; y: number }>): Node<WfNodeData>[] {
  return graph.nodes.map((n) => ({
    id: n.id,
    type: 'workflowNode',
    position: positions.get(n.id) ?? { x: 40, y: 40 },
    data: { nodeId: n.id, nodeType: n.type, summary: paramSummary(n) },
    draggable: n.type !== 'start', // start 是锚点，不允许拖动以免误挪整图
  }));
}

function toFlowEdges(graph: WorkflowGraph): Edge[] {
  return graph.edges.map((e, i) => ({
    id: `e-${i}-${e.from}-${e.to}`,
    source: e.from,
    target: e.to,
    label: e.label,
    style: edgeStyle(e.label),
    labelStyle: { fontSize: 10, fill: 'var(--muted-foreground)' },
    // condition 的两条分支线用不同颜色，一眼区分 true/false
    animated: false,
    markerEnd: { type: 'arrowclosed' as never, width: 14, height: 14 },
  }));
}

/** 把画布上的位置写回 graph.nodes[].position（执行语义不受影响）。 */
function attachPositions(graph: WorkflowGraph, nodes: Node<WfNodeData>[]): WorkflowGraph {
  const posById = new Map(nodes.map((n) => [n.id, n.position]));
  return {
    nodes: graph.nodes.map((n) => {
      const pos = posById.get(n.id);
      return pos
        ? ({ ...n, position: { x: Math.round(pos.x), y: Math.round(pos.y) } } as WorkflowGraphNode)
        : n;
    }),
    edges: graph.edges,
  };
}

/* ------------------------------------------------------------------ */
/* 主组件                                                              */
/* ------------------------------------------------------------------ */

export function WorkflowCanvas({
  graphText,
  onChange,
}: {
  graphText: string;
  onChange: (nextText: string) => void;
}) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner graphText={graphText} onChange={onChange} />
    </ReactFlowProvider>
  );
}

function WorkflowCanvasInner({
  graphText,
  onChange,
}: {
  graphText: string;
  onChange: (nextText: string) => void;
}) {
  const parsed = React.useMemo(() => {
    try {
      const g = JSON.parse(graphText) as WorkflowGraph;
      if (Array.isArray(g?.nodes) && Array.isArray(g?.edges)) return g;
      return null;
    } catch {
      return null;
    }
  }, [graphText]);

  const initial = React.useMemo(
    () => (parsed ? toFlowNodes(parsed, resolvePositions(parsed)) : []),
    // 只在图结构（节点 id）变化时重建，拖拽引起的 graphText 变化不重建
    [parsed?.nodes.map((n) => n.id).join('|')],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<WfNodeData>>(initial);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    React.useMemo(() => (parsed ? toFlowEdges(parsed) : []), [parsed?.edges.map((e) => `${e.from}>${e.to}`).join('|')]),
  );
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [newEdgeFrom, setNewEdgeFrom] = React.useState('');
  const [newEdgeTo, setNewEdgeTo] = React.useState('');

  // 外部 graphText 变化（结构化表单那边改了）→ 同步节点数据
  React.useEffect(() => {
    if (!parsed) return;
    const positions = resolvePositions(parsed);
    setNodes((prev) => {
      const byId = new Map(prev.map((n) => [n.id, n.position]));
      return toFlowNodes(parsed, positions).map((n) => ({
        ...n,
        position: byId.get(n.id) ?? n.position,
      }));
    });
    setEdges(toFlowEdges(parsed));
  }, [graphText]);

  const emit = React.useCallback(
    (next: WorkflowGraph) => onChange(JSON.stringify(next, null, 2)),
    [onChange],
  );

  // 拖拽过程中 useNodesState 的更新是异步的：onNodeDragStop 的闭包里的
  // `nodes` 可能还是拖拽开始前的值（位置写得回去才有鬼）。用 ref 读最新值。
  const nodesRef = React.useRef(nodes);
  nodesRef.current = nodes;

  const onNodeDragStop = React.useCallback(() => {
    if (!parsed) return;
    // 拖完把位置持久化（位置只是展示字段，后端不校验）
    emit(attachPositions(parsed, nodesRef.current));
  }, [parsed, emit]);

  const onConnect = React.useCallback(
    (conn: Connection) => {
      if (!parsed || !conn.source || !conn.target) return;
      const sourceNode = parsed.nodes.find((n) => n.id === conn.source);
      // condition 的出口必须带 true/false：新建连线默认 true，用户可在边列表改
      const label = sourceNode?.type === 'condition' ? 'true' : undefined;
      emit(addEdgeToGraph(parsed, conn.source, conn.target, label));
    },
    [parsed, emit],
  );

  const onEdgesDelete = React.useCallback(
    (deleted: Edge[]) => {
      if (!parsed) return;
      const keys = new Set(deleted.map((e) => `${e.source}>${e.target}`));
      emit({
        nodes: parsed.nodes,
        edges: parsed.edges.filter((e) => !keys.has(`${e.from}>${e.to}`)),
      });
    },
    [parsed, emit],
  );

  const onNodesDelete = React.useCallback(
    (deleted: Node<WfNodeData>[]) => {
      if (!parsed) return;
      let next = parsed;
      for (const n of deleted) next = deleteNodeFromGraph(next, n.id);
      emit(next);
      setSelectedId(null);
    },
    [parsed, emit],
  );

  const selectedNode = parsed?.nodes.find((n) => n.id === selectedId) ?? null;

  const setParams = (key: string, value: unknown) => {
    if (!parsed || !selectedId) return;
    emit(setNodeParam(parsed, selectedId, key, value));
  };

  if (parsed == null) {
    return (
      <p className="rounded-md border border-amber-200/80 bg-amber-50 p-3 text-xs font-medium text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300">
        节点图 JSON 不合法或缺少 nodes/edges，请切换「JSON 直编」修正。
      </p>
    );
  }

  const nodeOptions = parsed.nodes.map((n) => (
    <SelectItem key={n.id} value={n.id}>
      {n.id}（{TYPE_LABELS[n.type] ?? n.type}）
    </SelectItem>
  ));

  return (
    <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_260px]">
      {/* 画布 */}
      <div className="relative h-[420px] overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeDragStop={onNodeDragStop}
          onEdgesDelete={onEdgesDelete}
          onNodesDelete={onNodesDelete}
          onNodeClick={(_, n) => setSelectedId(n.id)}
          onPaneClick={() => setSelectedId(null)}
          fitView
          fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--border-subtle)" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={(n) => {
              const type = (n.data as WfNodeData).nodeType;
              const map: Record<string, string> = {
                start: '#10b981', llm: '#0ea5e9', knowledge: '#f59e0b', http: '#8b5cf6',
                template: '#94a3b8', condition: '#f43f5e', human_input: '#d946ef', end: '#047857',
              };
              return map[type] ?? '#94a3b8';
            }}
            style={{ height: 80, width: 120 }}
          />
        </ReactFlow>

        {/* 画布工具条 */}
        <div className="pointer-events-auto absolute left-2 top-2 flex flex-wrap items-center gap-1">
          <Select
            onValueChange={(t) => {
              let i = 1;
              while (parsed.nodes.some((n) => n.id === `${t}_${i}`)) i += 1;
              emit({
                nodes: [...parsed.nodes, { id: `${t}_${i}`, type: t, params: {} }],
                edges: parsed.edges,
              });
            }}
          >
            <SelectTrigger className="h-7 w-28 bg-[var(--surface-1)] text-[11px]">
              <SelectValue placeholder="+ 添加节点" />
            </SelectTrigger>
            <SelectContent>
              {NODE_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {TYPE_LABELS[t] ?? t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedNode ? (
            <Button
              variant="outline"
              size="sm"
              className="h-7 bg-[var(--surface-1)] px-2 text-[11px] text-destructive hover:text-destructive"
              disabled={selectedNode.type === 'start'}
              onClick={() => emit(deleteNodeFromGraph(parsed, selectedNode.id))}
            >
              <Trash2 className="mr-1 size-3" /> 删除
            </Button>
          ) : null}
        </div>
        <p className="pointer-events-none absolute bottom-2 right-2 rounded bg-[var(--surface-1)]/85 px-1.5 py-0.5 text-[10px] text-[var(--muted-foreground)]">
          拖节点移动 · 拖圆点连线 · 选中后 Del 删除
        </p>
      </div>

      {/* 右侧：选中节点的参数 + 连线管理 */}
      <div className="space-y-2 overflow-auto">
        {selectedNode ? (
          <div className="rounded-md border border-[var(--border-subtle)] p-2.5">
            <div className="mb-2 flex items-center gap-1.5">
              <span
                className={cn(
                  'rounded px-1.5 py-0.5 text-[10px] font-semibold text-white',
                  TYPE_COLORS[selectedNode.type] ?? 'bg-slate-400',
                )}
              >
                {TYPE_LABELS[selectedNode.type] ?? selectedNode.type}
              </span>
              <Input
                value={selectedNode.id}
                onChange={(e) => {
                  const next = renameNodeInGraph(parsed, selectedNode.id, e.target.value);
                  emit(next);
                  setSelectedId(e.target.value.trim() || selectedNode.id);
                }}
                disabled={selectedNode.type === 'start'}
                className="h-6 flex-1 font-mono text-[11px]"
                aria-label="节点 id"
              />
            </div>
            {(NODE_PARAM_FIELDS[selectedNode.type] ?? []).map((spec) => {
              const raw = (selectedNode.params ?? {})[spec.key];
              if (spec.kind === 'select') {
                return (
                  <div key={spec.key} className="mt-1.5 grid gap-0.5">
                    <Label className="text-[10px] text-[var(--muted-foreground)]">{spec.label}</Label>
                    <Select value={String(raw ?? spec.options?.[0] ?? '')} onValueChange={(v) => setParams(spec.key, v)}>
                      <SelectTrigger className="h-7 text-[11px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(spec.options ?? []).map((o) => (
                          <SelectItem key={o} value={o}>
                            {o}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                );
              }
              const text = raw == null ? '' : typeof raw === 'string' ? raw : JSON.stringify(raw);
              return (
                <div key={spec.key} className="mt-1.5 grid gap-0.5">
                  <Label className="text-[10px] text-[var(--muted-foreground)]">
                    {spec.label}
                    {spec.required ? <span className="ml-0.5 text-rose-500">*</span> : null}
                  </Label>
                  {spec.kind === 'textarea' || spec.kind === 'json' ? (
                    <textarea
                      value={text}
                      rows={spec.kind === 'json' ? 2 : 3}
                      onChange={(e) => {
                        if (spec.kind === 'json') {
                          try {
                            setParams(spec.key, e.target.value.trim() ? JSON.parse(e.target.value) : undefined);
                          } catch {
                            /* 非法 JSON 时不写回，等用户改对 */
                          }
                          return;
                        }
                        setParams(spec.key, e.target.value);
                      }}
                      className="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-1.5 text-[11px] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
                    />
                  ) : (
                    <Input
                      value={text}
                      type={spec.kind === 'number' ? 'number' : 'text'}
                      onChange={(e) => setParams(spec.key, e.target.value)}
                      className="h-7 text-[11px]"
                    />
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-[var(--border-subtle)] p-3 text-[11px] text-[var(--muted-foreground)]">
            点选画布中的节点即可在此编辑参数；拖动节点右侧圆点到目标节点可建立连线。
          </p>
        )}

        {/* 连线列表：改 condition 分支标签 / 删线 */}
        <div className="rounded-md border border-[var(--border-subtle)] p-2.5">
          <Label className="text-[10px] text-[var(--muted-foreground)]">连线（{parsed.edges.length}）</Label>
          <div className="mt-1 space-y-1">
            {parsed.edges.map((edge, index) => {
              const srcIsCondition = parsed.nodes.find((n) => n.id === edge.from)?.type === 'condition';
              return (
                <div key={`${edge.from}-${edge.to}-${index}`} className="flex items-center gap-1">
                  <span className="min-w-0 flex-1 truncate font-mono text-[10px]">
                    {edge.from} → {edge.to}
                  </span>
                  {srcIsCondition ? (
                    <Select
                      value={String(edge.label ?? '')}
                      onValueChange={(v) => {
                        const nextEdges: WorkflowGraphEdge[] = parsed.edges.map((e, i) =>
                          i === index ? { ...e, label: v } : e,
                        );
                        emit({ nodes: parsed.nodes, edges: nextEdges });
                      }}
                    >
                      <SelectTrigger className="h-6 w-16 text-[10px]">
                        <SelectValue placeholder="分支" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="true">true</SelectItem>
                        <SelectItem value="false">false</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 px-1.5 text-destructive hover:text-destructive"
                    onClick={() =>
                      emit({ nodes: parsed.nodes, edges: parsed.edges.filter((_, i) => i !== index) })
                    }
                    aria-label={`删除连线 ${edge.from}->${edge.to}`}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              );
            })}
          </div>
          <div className="mt-1.5 flex items-center gap-1">
            <Select value={newEdgeFrom} onValueChange={setNewEdgeFrom}>
              <SelectTrigger className="h-6 min-w-0 flex-1 text-[10px]">
                <SelectValue placeholder="来源" />
              </SelectTrigger>
              <SelectContent>{nodeOptions}</SelectContent>
            </Select>
            <span className="text-[10px] text-[var(--muted-foreground)]">→</span>
            <Select value={newEdgeTo} onValueChange={setNewEdgeTo}>
              <SelectTrigger className="h-6 min-w-0 flex-1 text-[10px]">
                <SelectValue placeholder="目标" />
              </SelectTrigger>
              <SelectContent>{nodeOptions}</SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              className="h-6 px-1.5 text-[10px]"
              disabled={!newEdgeFrom || !newEdgeTo || newEdgeFrom === newEdgeTo}
              onClick={() => {
                emit(addEdgeToGraph(parsed, newEdgeFrom, newEdgeTo));
                setNewEdgeFrom('');
                setNewEdgeTo('');
              }}
            >
              添加
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
