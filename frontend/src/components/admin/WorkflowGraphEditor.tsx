/**
 * 工作流节点图结构化编辑器（P0-3 画布 v1 的无依赖替代形态）。
 *
 * 设计取舍：不引入 React Flow —— 节点图 DSL 已被 71 个后端测试钉住，
 * 编辑器只是同一份 JSON 的可视化外衣。本组件提供：
 *  - 分类型参数表单（llm/knowledge/http/template/condition/human_input/end），
 *    替代手写 JSON；后端保存时仍做一次全量校验兜底；
 *  - 边构建器 + 节点改名/删除的级联（改名同步所有引用边，删边先于删点）；
 *  - 自动布局只读 SVG 预览（按 start 起 BFS 深度分列），核对结构用。
 *
 * 受控组件：graphText(JSON) 进、onChange(graphText) 出 —— 父级保存逻辑
 * 与「JSON 直编模式」完全共享，两种模式可随时切换不丢数据。
 */
import * as React from 'react';
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

export const NODE_TYPES = ['start', 'llm', 'knowledge', 'http', 'template', 'condition', 'human_input', 'end'] as const;

export const CONDITION_OPS = [
  '==', '!=', '>', '<', '>=', '<=',
  'contains', 'not_contains', 'startswith', 'endswith', 'is_empty', 'not_empty',
];

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'];

// 工作流 LLM 节点可选的模型用途档。
//
// 只列**留空会回退主模型**的角色（chat / fast）—— 工作流节点走
// /chat/completions，绑 image / embedding 会必然失败。reasoner / vision
// 已从后端 MODEL_ROLES 移除（无运行时消费方），不再出现在这里。
const LLM_ROLES = ['fast', 'chat'];

export interface ParamFieldSpec {
  key: string;
  label: string;
  kind: 'text' | 'textarea' | 'number' | 'json' | 'select';
  options?: string[];
  required?: boolean;
  placeholder?: string;
  hint?: string;
}

/** 分类型参数表单定义。kind=json 的值是数组/对象，编辑态为 JSON 文本。 */
export const NODE_PARAM_FIELDS: Record<string, ParamFieldSpec[]> = {
  start: [],
  llm: [
    { key: 'system', label: 'System 提示词', kind: 'textarea' },
    { key: 'prompt', label: 'Prompt（支持 {{inputs.x}} / {{nodes.节点id.output}}）', kind: 'textarea', required: true },
    { key: 'role', label: '模型用途档', kind: 'select', options: LLM_ROLES, hint: 'fast=轻任务档，未绑定自动退回主模型' },
  ],
  knowledge: [
    { key: 'query', label: '检索词（支持 {{...}}）', kind: 'textarea', required: true },
    { key: 'kb_ids', label: '知识库 ID（逗号分隔，留空=全部有权限的）', kind: 'text' },
    { key: 'top_k', label: 'Top K（1-20）', kind: 'number' },
  ],
  http: [
    { key: 'method', label: 'Method', kind: 'select', options: HTTP_METHODS },
    { key: 'url', label: 'URL（走内网访问策略，未配置网段时全部拒绝）', kind: 'text', required: true },
    { key: 'headers', label: 'Headers（JSON；Authorization/Cookie 会被剥除）', kind: 'json' },
    { key: 'body', label: 'Body（文本，GET/HEAD 不发送）', kind: 'textarea' },
    { key: 'timeout_seconds', label: '超时秒数（1-60）', kind: 'number' },
  ],
  template: [
    { key: 'template', label: '模板文本（支持 {{...}}）', kind: 'textarea', required: true },
  ],
  condition: [
    { key: 'left', label: '左值（支持 {{...}}）', kind: 'text', required: true },
    { key: 'op', label: '比较符', kind: 'select', options: CONDITION_OPS, required: true },
    { key: 'right', label: '右值（支持 {{...}}）', kind: 'text' },
  ],
  human_input: [
    { key: 'prompt', label: '向用户提问', kind: 'text', required: true },
    {
      key: 'fields',
      label: '表单字段（JSON 数组；留空=单行「答复」）',
      kind: 'json',
      hint: '例：[{"key":"confirm","label":"确认","type":"text","required":true}]',
    },
  ],
  end: [
    { key: 'output', label: '输出（支持 {{...}}；留空=各上游节点输出聚合）', kind: 'textarea' },
  ],
};

export const TYPE_LABELS: Record<string, string> = {
  start: '开始',
  llm: 'LLM',
  knowledge: '知识检索',
  http: 'HTTP',
  template: '模板',
  condition: '条件',
  human_input: '人工输入',
  end: '结束',
};

export const TYPE_COLORS: Record<string, string> = {
  start: 'fill-emerald-500',
  llm: 'fill-sky-500',
  knowledge: 'fill-amber-500',
  http: 'fill-violet-500',
  template: 'fill-slate-400',
  condition: 'fill-rose-500',
  human_input: 'fill-fuchsia-500',
  end: 'fill-emerald-700',
};

/** BFS 深度分列布局：start 在第 0 列，节点深度 = max(前驱深度)+1。 */
export function computeLayout(graph: WorkflowGraph): { columns: Map<string, number>; maxDepth: number } {
  const preds = new Map<string, string[]>();
  for (const n of graph.nodes) preds.set(n.id, []);
  for (const e of graph.edges) preds.get(e.to)?.push(e.from);
  const depth = new Map<string, number>();
  const start = graph.nodes.find((n) => n.type === 'start');
  if (start) depth.set(start.id, 0);
  // 松弛（|V| 轮足够：有环时后端校验会拒绝，这里只求展示稳定）
  for (let round = 0; round < graph.nodes.length; round += 1) {
    let changed = false;
    for (const e of graph.edges) {
      const d = depth.get(e.from);
      if (d === undefined) continue;
      const next = d + 1;
      if ((depth.get(e.to) ?? -1) < next) {
        depth.set(e.to, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  let maxDepth = 0;
  for (const n of graph.nodes) {
    if (!depth.has(n.id)) depth.set(n.id, maxDepth + 1); // 孤立节点放最后
    maxDepth = Math.max(maxDepth, depth.get(n.id) ?? 0);
  }
  return { columns: depth, maxDepth };
}

/**
 * 纯图操作（导出供单元测试）：全部返回新对象，不原地改。
 */
export function renameNodeInGraph(
  graph: WorkflowGraph,
  oldId: string,
  nextId: string,
): WorkflowGraph {
  const trimmed = nextId.trim();
  if (!trimmed || trimmed === oldId) return graph;
  if (graph.nodes.some((n) => n.id === trimmed)) return graph; // 重名拒绝
  const nodes = graph.nodes.map((n) => (n.id === oldId ? { ...n, id: trimmed } : n));
  const edges = graph.edges.map((e) => ({
    ...e,
    from: e.from === oldId ? trimmed : e.from,
    to: e.to === oldId ? trimmed : e.to,
  }));
  return { nodes, edges };
}

export function deleteNodeFromGraph(graph: WorkflowGraph, nodeId: string): WorkflowGraph {
  if (graph.nodes.find((n) => n.id === nodeId)?.type === 'start') return graph; // start 不可删
  return {
    nodes: graph.nodes.filter((n) => n.id !== nodeId),
    edges: graph.edges.filter((e) => e.from !== nodeId && e.to !== nodeId),
  };
}

export function addEdgeToGraph(
  graph: WorkflowGraph,
  from: string,
  to: string,
  label?: string,
): WorkflowGraph {
  if (!from || !to || from === to) return graph;
  if (graph.edges.some((e) => e.from === from && e.to === to)) return graph;
  const edges = [...graph.edges, { from, to, ...(label ? { label } : {}) }];
  return { nodes: graph.nodes, edges };
}

export function setNodeParam(
  graph: WorkflowGraph,
  nodeId: string,
  key: string,
  value: unknown,
): WorkflowGraph {
  const nodes = graph.nodes.map((n) => {
    if (n.id !== nodeId) return n;
    const params = { ...(n.params ?? {}) };
    if (value === undefined || value === '') {
      delete params[key];
    } else {
      params[key] = value;
    }
    return { ...n, params };
  });
  return { nodes, edges: graph.edges };
}

function GraphPreview({ graph }: { graph: WorkflowGraph }) {
  const { columns, maxDepth } = computeLayout(graph);
  const byDepth = new Map<number, WorkflowGraphNode[]>();
  for (const n of graph.nodes) {
    const d = columns.get(n.id) ?? 0;
    const bucket = byDepth.get(d) ?? [];
    bucket.push(n);
    byDepth.set(d, bucket);
  }
  const pos = new Map<string, { x: number; y: number }>();
  for (const [d, bucket] of byDepth) {
    bucket.forEach((n, i) => pos.set(n.id, { x: 16 + d * 208, y: 16 + i * 64 }));
  }
  const width = 16 + (maxDepth + 1) * 208;
  const height = 16 + Math.max(1, ...[...byDepth.values()].map((b) => b.length)) * 64;

  return (
    <div className="overflow-auto rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-2">
      <svg width={Math.max(width, 240)} height={Math.max(height, 80)} role="img" aria-label="工作流结构预览">
        {graph.edges.map((e, i) => {
          const from = pos.get(e.from);
          const to = pos.get(e.to);
          if (!from || !to) return null;
          const x1 = from.x + 168;
          const y1 = from.y + 20;
          const x2 = to.x;
          const y2 = to.y + 20;
          return (
            <g key={`${e.from}-${e.to}-${i}`}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--muted-foreground)" strokeWidth="1.5" markerEnd="url(#wf-arrow)" />
              {e.label ? (
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4} fontSize="9" fill="var(--muted-foreground)" textAnchor="middle">
                  {e.label}
                </text>
              ) : null}
            </g>
          );
        })}
        {graph.nodes.map((n) => {
          const p = pos.get(n.id);
          if (!p) return null;
          return (
            <g key={n.id}>
              <rect x={p.x} y={p.y} width={168} height={40} rx="8" className={cn('fill-[var(--surface-1)] stroke-[var(--border-subtle)]')} strokeWidth="1" />
              <rect x={p.x + 6} y={p.y + 11} width={18} height={18} rx="4" className={cn(TYPE_COLORS[n.type] ?? 'fill-slate-400')} />
              <text x={p.x + 32} y={p.y + 18} fontSize="10" fill="var(--muted-foreground)">
                {TYPE_LABELS[n.type] ?? n.type}
              </text>
              <text x={p.x + 32} y={p.y + 31} fontSize="11" fontWeight="600" fill="var(--foreground)">
                {n.id.length > 18 ? `${n.id.slice(0, 17)}…` : n.id}
              </text>
            </g>
          );
        })}
        <defs>
          <marker id="wf-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--muted-foreground)" />
          </marker>
        </defs>
      </svg>
    </div>
  );
}

/** JSON 类参数：本地草稿态 —— 合法 JSON 即写入图，非法时只显示草稿与提示。 */
function JsonParamField({
  value,
  onChange,
  placeholder,
}: {
  value: unknown;
  onChange: (parsed: unknown) => void;
  placeholder?: string;
}) {
  const initialText = value == null ? '' : JSON.stringify(value, null, 0);
  const [draft, setDraft] = React.useState(initialText);
  const [error, setError] = React.useState<string | null>(null);
  // 外部值变化（切节点）时重置草稿
  React.useEffect(() => {
    setDraft(value == null ? '' : JSON.stringify(value, null, 0));
    setError(null);
  }, [initialText]);

  return (
    <div>
      <textarea
        value={draft}
        onChange={(e) => {
          const text = e.target.value;
          setDraft(text);
          if (!text.trim()) {
            setError(null);
            onChange(undefined);
            return;
          }
          try {
            const parsed = JSON.parse(text);
            setError(null);
            onChange(parsed);
          } catch {
            setError('JSON 不合法（保留草稿，修正后自动生效）');
          }
        }}
        rows={2}
        spellCheck={false}
        placeholder={placeholder}
        className={cn(
          'w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-2',
          'font-mono text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]',
        )}
      />
      {error ? <p className="mt-1 text-[11px] font-medium text-amber-600">{error}</p> : null}
    </div>
  );
}

export function WorkflowGraphEditor({
  graphText,
  onChange,
}: {
  graphText: string;
  onChange: (nextText: string) => void;
}) {
  const [newEdgeFrom, setNewEdgeFrom] = React.useState('');
  const [newEdgeTo, setNewEdgeTo] = React.useState('');
  const parsed = React.useMemo(() => {
    try {
      const graph = JSON.parse(graphText) as WorkflowGraph;
      if (Array.isArray(graph?.nodes) && Array.isArray(graph?.edges)) return graph;
      return null;
    } catch {
      return null;
    }
  }, [graphText]);

  if (parsed == null) {
    return (
      <p className="rounded-md border border-amber-200/80 bg-amber-50 p-3 text-xs font-medium text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300">
        节点图 JSON 不合法或缺少 nodes/edges，请切换「JSON 直编」修正。
      </p>
    );
  }

  const mutate = (next: WorkflowGraph) => onChange(JSON.stringify(next, null, 2));

  const setParams = (nodeId: string, key: string, value: unknown) => {
    mutate(setNodeParam(parsed, nodeId, key, value));
  };

  const addNode = (type: (typeof NODE_TYPES)[number]) => {
    let i = 1;
    while (parsed.nodes.some((n) => n.id === `${type}_${i}`)) i += 1;
    mutate({
      nodes: [...parsed.nodes, { id: `${type}_${i}`, type, params: {} }],
      edges: parsed.edges,
    });
  };

  const setEdge = (index: number, patch: Partial<WorkflowGraphEdge>) => {
    const edges = parsed.edges.map((e, i) => (i === index ? { ...e, ...patch } : e));
    mutate({ nodes: parsed.nodes, edges });
  };

  const addEdge = (from: string, to: string) => {
    mutate(addEdgeToGraph(parsed, from, to));
  };

  const deleteEdge = (index: number) => {
    const edges = parsed.edges.filter((_, i) => i !== index);
    mutate({ nodes: parsed.nodes, edges });
  };

  const nodeOptions = parsed.nodes.map((n) => (
    <SelectItem key={n.id} value={n.id}>
      {n.id}（{TYPE_LABELS[n.type] ?? n.type}）
    </SelectItem>
  ));

  return (
    <div className="space-y-3">
      <GraphPreview graph={parsed} />

      {/* 节点参数 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs">节点（{parsed.nodes.length}）</Label>
          <Select onValueChange={(v) => addNode(v as (typeof NODE_TYPES)[number])}>
            <SelectTrigger className="h-7 w-36 text-xs">
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
        </div>
        {parsed.nodes.map((node) => {
          const specs = NODE_PARAM_FIELDS[node.type] ?? [];
          return (
            <div key={node.id} className="rounded-md border border-[var(--border-subtle)] p-3">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold text-white',
                    TYPE_COLORS[node.type] ?? 'bg-slate-400',
                  )}
                >
                  {TYPE_LABELS[node.type] ?? node.type}
                </span>
                <Input
                  value={node.id}
                  onChange={(e) => mutate(renameNodeInGraph(parsed, node.id, e.target.value))}
                  className="h-7 w-44 font-mono text-xs"
                  aria-label={`节点 id：${node.id}`}
                  disabled={node.type === 'start'}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto text-destructive hover:text-destructive"
                  onClick={() => mutate(deleteNodeFromGraph(parsed, node.id))}
                  disabled={node.type === 'start'}
                  aria-label={`删除节点 ${node.id}`}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
              {specs.map((spec) => {
                const raw = (node.params ?? {})[spec.key];
                if (spec.kind === 'select') {
                  return (
                    <div key={spec.key} className="mt-2 grid gap-1">
                      <Label className="text-[11px] text-[var(--muted-foreground)]">{spec.label}</Label>
                      <Select
                        value={String(raw ?? spec.options?.[0] ?? '')}
                        onValueChange={(v) => setParams(node.id, spec.key, v)}
                      >
                        <SelectTrigger className="h-8 text-xs">
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
                if (spec.kind === 'json') {
                  return (
                    <div key={spec.key} className="mt-2 grid gap-1">
                      <Label className="text-[11px] text-[var(--muted-foreground)]">{spec.label}</Label>
                      <JsonParamField
                        value={raw}
                        placeholder={spec.hint}
                        onChange={(parsedValue) => setParams(node.id, spec.key, parsedValue)}
                      />
                    </div>
                  );
                }
                const textValue =
                  spec.key === 'kb_ids' && Array.isArray(raw)
                    ? (raw as unknown[]).join(',')
                    : raw == null
                      ? ''
                      : String(raw);
                return (
                  <div key={spec.key} className="mt-2 grid gap-1">
                    <Label className="text-[11px] text-[var(--muted-foreground)]">
                      {spec.label}
                      {spec.required ? <span className="ml-0.5 text-rose-500">*</span> : null}
                    </Label>
                    {spec.kind === 'textarea' ? (
                      <textarea
                        value={textValue}
                        rows={2}
                        onChange={(e) => {
                          if (spec.key === 'kb_ids') return;
                          setParams(node.id, spec.key, e.target.value);
                        }}
                        className={cn(
                          'w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-2',
                          'text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]',
                        )}
                      />
                    ) : (
                      <Input
                        value={textValue}
                        type={spec.kind === 'number' ? 'number' : 'text'}
                        onChange={(e) => {
                          if (spec.key === 'kb_ids') {
                            const ids = e.target.value
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean)
                              .map(Number)
                              .filter((n) => Number.isFinite(n));
                            setParams(node.id, 'kb_ids', ids.length ? ids : undefined);
                            return;
                          }
                          setParams(node.id, spec.key, e.target.value);
                        }}
                        className="h-8 text-xs"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      {/* 边 */}
      <div className="space-y-2">
        <Label className="text-xs">连线（{parsed.edges.length}）</Label>
        {parsed.edges.map((edge, index) => {
          const sourceIsCondition =
            parsed.nodes.find((n) => n.id === edge.from)?.type === 'condition';
          return (
            <div key={`${edge.from}-${edge.to}-${index}`} className="flex items-center gap-2">
              <Select value={edge.from} onValueChange={(v) => setEdge(index, { from: v })}>
                <SelectTrigger className="h-8 w-40 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>{nodeOptions}</SelectContent>
              </Select>
              <span className="text-xs text-[var(--muted-foreground)]">→</span>
              <Select value={edge.to} onValueChange={(v) => setEdge(index, { to: v })}>
                <SelectTrigger className="h-8 w-40 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>{nodeOptions}</SelectContent>
              </Select>
              {sourceIsCondition ? (
                <Select
                  value={String(edge.label ?? '')}
                  onValueChange={(v) => setEdge(index, { label: v })}
                >
                  <SelectTrigger className="h-8 w-24 text-xs">
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
                className="text-destructive hover:text-destructive"
                onClick={() => deleteEdge(index)}
                aria-label={`删除连线 ${edge.from}→${edge.to}`}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          );
        })}
        <div className="flex items-center gap-2">
          <Select value={newEdgeFrom} onValueChange={setNewEdgeFrom}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue placeholder="来源节点" />
            </SelectTrigger>
            <SelectContent>{nodeOptions}</SelectContent>
          </Select>
          <span className="text-xs text-[var(--muted-foreground)]">→</span>
          <Select value={newEdgeTo} onValueChange={setNewEdgeTo}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue placeholder="目标节点" />
            </SelectTrigger>
            <SelectContent>{nodeOptions}</SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            disabled={!newEdgeFrom || !newEdgeTo || newEdgeFrom === newEdgeTo}
            onClick={() => {
              addEdge(newEdgeFrom, newEdgeTo);
              setNewEdgeFrom('');
              setNewEdgeTo('');
            }}
          >
            添加连线
          </Button>
        </div>
      </div>
    </div>
  );
}
