import { create } from 'zustand';
import { temporal } from 'zundo';
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react';

export type ResolutionTier = '1K' | '2K' | '4K';
export type QualityTier = 'fast' | 'balanced' | 'fine';

export interface ArtworkData extends Record<string, unknown> {
  kind: 'artwork';
  title: string;
  prompt: string;
  model: string;
  aspectId: string;
  resolution: ResolutionTier;
  quality: QualityTier;
  width: number;
  height: number;
  durationSec: number;
  createdAt: string;
  liked: boolean;
  dataUrl: string;
  nodeW: number;
  nodeH: number;
  onDerive?: (id: string) => void;
  onOpenEdit?: (id: string) => void;
  onFocus?: (id: string) => void;
  onDownload?: (id: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
}

export interface NoteData extends Record<string, unknown> {
  kind: 'note';
  title: string;
  text: string;
  noteColor: 'amber' | 'indigo';
  onChangeText?: (id: string, text: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
}

export type StudioNode = Node<ArtworkData, 'artwork'> | Node<NoteData, 'note'>;

export function buildStudioPosterSvg(opts: {
  title: string;
  subtitle: string;
  palette: [string, string, string];
  aspectW: number;
  aspectH: number;
  badge: string;
}): string {
  const { title, subtitle, palette, aspectW, aspectH, badge } = opts;
  const [c1, c2, c3] = palette;
  const safeTitle = title.replace(/[<>&"']/g, '').slice(0, 18) || '创意视觉设计';
  const safeSub = subtitle.replace(/[<>&"']/g, '').slice(0, 32) || 'AgenticOS Creative Studio';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${aspectW} ${aspectH}" width="${aspectW}" height="${aspectH}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${c1}"/>
      <stop offset="55%" stop-color="${c2}"/>
      <stop offset="100%" stop-color="${c3}"/>
    </linearGradient>
    <radialGradient id="glow1" cx="72%" cy="24%" r="48%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow2" cx="22%" cy="82%" r="52%">
      <stop offset="0%" stop-color="#fef08a" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#fef08a" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="glass" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.24"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.06"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#glow1)"/>
  <rect width="100%" height="100%" fill="url(#glow2)"/>
  <g opacity="0.16" stroke="#ffffff" fill="none">
    <circle cx="${aspectW * 0.5}" cy="${aspectH * 0.44}" r="${Math.min(aspectW, aspectH) * 0.34}" stroke-width="1.5" stroke-dasharray="6 8"/>
    <circle cx="${aspectW * 0.5}" cy="${aspectH * 0.44}" r="${Math.min(aspectW, aspectH) * 0.24}" stroke-width="1.2"/>
    <circle cx="${aspectW * 0.5}" cy="${aspectH * 0.44}" r="${Math.min(aspectW, aspectH) * 0.14}" stroke-width="1"/>
  </g>
  <rect x="${aspectW * 0.08}" y="${aspectH * 0.06}" width="176" height="36" rx="18" fill="url(#glass)" stroke="rgba(255,255,255,0.35)"/>
  <text x="${aspectW * 0.08 + 88}" y="${aspectH * 0.06 + 23}" text-anchor="middle" fill="#ffffff" font-family="system-ui, sans-serif" font-size="14" font-weight="600" letter-spacing="1.5">${badge}</text>
  <g transform="translate(${aspectW * 0.5}, ${aspectH * 0.44})">
    <polygon points="0,-110 95,55 -95,55" fill="url(#glass)" stroke="rgba(255,255,255,0.45)" stroke-width="1.5"/>
    <circle cx="0" cy="-10" r="46" fill="rgba(255,255,255,0.18)" stroke="rgba(255,255,255,0.65)" stroke-width="1.5"/>
  </g>
  <rect x="${aspectW * 0.08}" y="${aspectH * 0.68}" width="${aspectW * 0.84}" height="${aspectH * 0.24}" rx="28" fill="rgba(15,23,42,0.28)" stroke="rgba(255,255,255,0.26)"/>
  <text x="${aspectW * 0.5}" y="${aspectH * 0.78}" text-anchor="middle" fill="#ffffff" font-family="system-ui, sans-serif" font-size="${Math.round(Math.min(aspectW, aspectH) * 0.062)}" font-weight="800" letter-spacing="2">${safeTitle}</text>
  <text x="${aspectW * 0.5}" y="${aspectH * 0.855}" text-anchor="middle" fill="rgba(255,255,255,0.84)" font-family="system-ui, sans-serif" font-size="${Math.round(Math.min(aspectW, aspectH) * 0.024)}" font-weight="500">${safeSub}</text>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export const STUDIO_PALETTES: [string, string, string][] = [
  ['#1d4ed8', '#3b82f6', '#0f172a'],
  ['#4f46e5', '#7c3aed', '#1e1b4b'],
  ['#0f766e', '#0ea5e9', '#0f172a'],
  ['#b45309', '#e11d48', '#1f1629'],
];

// 画布初始为空：作品由 AI 生成或从工作区加载，不再内置演示海报。
const INITIAL_NODES: StudioNode[] = [];
const INITIAL_EDGES: Edge[] = [];

interface CanvasState {
  nodes: StudioNode[];
  edges: Edge[];
  onNodesChange: (changes: NodeChange<StudioNode>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  setNodes: (nodes: StudioNode[]) => void;
  addNodesAndEdges: (newNodes: StudioNode[], newEdges?: Edge[]) => void;
  deleteNode: (id: string) => void;
  duplicateNode: (id: string) => string | null;
  updateNoteText: (id: string, text: string) => void;
  toggleLike: (id: string) => void;
  selectOnly: (id: string) => void;
}

/**
 * Zustand + zundo (`temporal`) 画布状态仓库：
 * 自动记录 nodes / edges 的历史快照，支持 Ctrl+Z / Ctrl+Shift+Z 撤销与重做。
 */
export const useCanvasStore = create<CanvasState>()(
  temporal(
    (set, get) => ({
      nodes: INITIAL_NODES,
      edges: INITIAL_EDGES,

      onNodesChange: (changes) => {
        set({ nodes: applyNodeChanges(changes, get().nodes) });
      },

      onEdgesChange: (changes) => {
        set({ edges: applyEdgeChanges(changes, get().edges) });
      },

      onConnect: (connection) => {
        set({
          edges: addEdge(
            {
              ...connection,
              animated: true,
              label: '参考关联',
              style: { stroke: '#6366f1', strokeWidth: 2 },
              labelStyle: { fill: '#ffffff', fontSize: 10, fontWeight: 600 },
              labelBgStyle: { fill: '#4f46e5', fillOpacity: 0.92 },
              labelBgPadding: [6, 3],
              labelBgBorderRadius: 10,
            },
            get().edges,
          ),
        });
      },

      setNodes: (nodes) => set({ nodes }),

      addNodesAndEdges: (newNodes, newEdges = []) => {
        set({
          nodes: [
            ...get().nodes.map((n) => ({ ...n, selected: false })),
            ...newNodes,
          ],
          edges: newEdges.length > 0 ? [...get().edges, ...newEdges] : get().edges,
        });
      },

      deleteNode: (id) => {
        set({
          nodes: get().nodes.filter((n) => n.id !== id),
          edges: get().edges.filter((e) => e.source !== id && e.target !== id),
        });
      },

      duplicateNode: (id) => {
        const orig = get().nodes.find((n) => n.id === id);
        if (!orig) return null;
        const newId = `${orig.data.kind}-${Date.now()}`;
        const cloned: StudioNode =
          orig.type === 'artwork'
            ? {
                ...orig,
                id: newId,
                selected: true,
                position: { x: orig.position.x + 48, y: orig.position.y + 48 },
                data: { ...(orig.data as ArtworkData), title: `${(orig.data as ArtworkData).title} 副本` },
              }
            : {
                ...orig,
                id: newId,
                selected: true,
                position: { x: orig.position.x + 48, y: orig.position.y + 48 },
                data: { ...(orig.data as NoteData), title: `${(orig.data as NoteData).title} 副本` },
              };
        set({
          nodes: [...get().nodes.map((n) => ({ ...n, selected: false })), cloned],
        });
        return newId;
      },

      updateNoteText: (id, text) => {
        set({
          nodes: get().nodes.map((n) =>
            n.id === id && n.type === 'note'
              ? { ...n, data: { ...(n.data as NoteData), text } }
              : n,
          ),
        });
      },

      toggleLike: (id) => {
        set({
          nodes: get().nodes.map((n) =>
            n.id === id && n.type === 'artwork'
              ? { ...n, data: { ...(n.data as ArtworkData), liked: !(n.data as ArtworkData).liked } }
              : n,
          ),
        });
      },

      selectOnly: (id) => {
        set({
          nodes: get().nodes.map((n) => ({ ...n, selected: n.id === id })),
        });
      },
    }),
    {
      limit: 40,
      partialize: (state) => ({
        nodes: state.nodes,
        edges: state.edges,
      }),
    },
  ),
);
