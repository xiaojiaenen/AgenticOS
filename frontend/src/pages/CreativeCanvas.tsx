import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  MiniMap,
  Panel,
  Handle,
  Position,
  NodeToolbar,
  useNodesState,
  useEdgesState,
  useReactFlow,
  addEdge,
  type Node,
  type Edge,
  type NodeProps,
  type Connection,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowLeft,
  Bot,
  Brush,
  Check,
  Copy,
  Download,
  Eraser,
  Focus,
  GitBranch,
  Grid,
  Hand,
  Heart,
  Home as HomeIcon,
  Image as ImageIcon,
  Layers,
  LayoutGrid,
  Loader2,
  Maximize2,
  MessageSquare,
  Minus,
  MousePointer2,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  RotateCcw,
  Shield,
  Sparkles,
  StickyNote,
  Trash2,
  Upload,
  Wand2,
  X,
} from 'lucide-react';
import { Logo } from '../components/Logo';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { cn } from '../lib/utils';
import { canEnterAdmin, getStoredUser } from '@/services/authTokenStore';

type CanvasMode = 'focus' | 'infinite';
type InfiniteTool = 'select' | 'hand';
type ResolutionTier = '1K' | '2K' | '4K';
type QualityTier = 'fast' | 'balanced' | 'fine';

interface AspectOption {
  id: string;
  label: string;
  w: number;
  h: number;
  iconW: number;
  iconH: number;
}

interface ArtworkData extends Record<string, unknown> {
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

interface NoteData extends Record<string, unknown> {
  kind: 'note';
  title: string;
  text: string;
  noteColor: 'amber' | 'indigo';
  onChangeText?: (id: string, text: string) => void;
  onDuplicate?: (id: string) => void;
  onDelete?: (id: string) => void;
}

type StudioNode = Node<ArtworkData, 'artwork'> | Node<NoteData, 'note'>;

const ASPECT_OPTIONS: AspectOption[] = [
  { id: '1:1', label: '1:1', w: 1024, h: 1024, iconW: 12, iconH: 12 },
  { id: '3:4', label: '3:4', w: 768, h: 1024, iconW: 10, iconH: 13 },
  { id: '4:3', label: '4:3', w: 1024, h: 768, iconW: 13, iconH: 10 },
  { id: '9:16', label: '9:16', w: 720, h: 1280, iconW: 8, iconH: 14 },
  { id: '16:9', label: '16:9', w: 1280, h: 720, iconW: 14, iconH: 8 },
  { id: '3:2', label: '3:2', w: 1152, h: 768, iconW: 13, iconH: 9 },
  { id: '2:3', label: '2:3', w: 768, h: 1152, iconW: 9, iconH: 13 },
];

const MODEL_OPTIONS = [
  { id: 'gpt-image-2.5', label: 'GPT Image 2.5', badge: '旗舰精绘' },
  { id: 'flux-pro-ultra', label: 'Flux Pro Ultra', badge: '写实质感' },
  { id: 'seedream-3.0', label: 'Seedream 3.0', badge: '中文排版' },
  { id: 'qwen-image', label: 'Qwen-Image', badge: '企业内网' },
];

const CAMERA_PRESETS = [
  '电影级体积光，浅景深，居中对称构图',
  '极简棚拍质感，柔和漫反射，留白高级排版',
  '俯拍微距视角，细腻材质反射，8K 超清细节',
  '广角宏大城市天际线，黄金时刻暖冷对比光影',
];

const TIER_SCALE: Record<ResolutionTier, number> = {
  '1K': 1,
  '2K': 1.5,
  '4K': 2,
};

function buildStudioPosterSvg(opts: {
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

const PALETTES: [string, string, string][] = [
  ['#1d4ed8', '#3b82f6', '#0f172a'],
  ['#4f46e5', '#7c3aed', '#1e1b4b'],
  ['#0f766e', '#0ea5e9', '#0f172a'],
  ['#b45309', '#e11d48', '#1f1629'],
];

/* ============================================================================
   Custom @xyflow/react Nodes (Defined Outside Component for Stable Identity)
   ============================================================================ */

const ArtworkNode: React.FC<NodeProps<Node<ArtworkData, 'artwork'>>> = ({ id, data, selected }) => {
  return (
    <>
      <NodeToolbar isVisible={Boolean(selected)} position={Position.Top} offset={10}>
        <div className="aos-glass-rail flex items-center gap-1 whitespace-nowrap rounded-xl px-1.5 py-1 shadow-xl">
          <button
            type="button"
            onClick={() => data.onDerive?.(id)}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--primary)]/12 px-2 py-1 text-[11px] font-semibold text-[var(--primary)] hover:bg-[var(--primary)]/20"
          >
            <GitBranch size={12} />
            衍生
          </button>
          <button
            type="button"
            onClick={() => data.onOpenEdit?.(id)}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-[var(--foreground)] hover:bg-[var(--surface-2)]"
          >
            <Wand2 size={12} />
            改图
          </button>
          <button
            type="button"
            onClick={() => data.onFocus?.(id)}
            className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            title="专注检视"
          >
            <Focus size={13} />
          </button>
          <button
            type="button"
            onClick={() => data.onDownload?.(id)}
            className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            title="下载原图"
          >
            <Download size={13} />
          </button>
          <button
            type="button"
            onClick={() => data.onDuplicate?.(id)}
            className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            title="复制"
          >
            <Copy size={13} />
          </button>
          <button
            type="button"
            onClick={() => data.onDelete?.(id)}
            className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-rose-500/15 hover:text-rose-500"
            title="删除"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </NodeToolbar>

      <div
        onDoubleClick={() => data.onFocus?.(id)}
        style={{ width: data.nodeW }}
        className={cn(
          'aos-glass-surface relative overflow-hidden rounded-2xl p-2 transition-shadow',
          selected
            ? 'ring-2 ring-[var(--primary)] shadow-[0_20px_45px_-12px_rgba(79,70,229,0.35)]'
            : 'hover:shadow-xl',
        )}
      >
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !border-2 !border-[var(--surface-1)] !bg-[var(--primary)]"
        />
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !border-2 !border-[var(--surface-1)] !bg-[var(--primary)]"
        />
        <div className="mb-1.5 flex items-center justify-between gap-2 px-1 text-[11px]">
          <span className="truncate font-semibold text-[var(--foreground)]">{data.title}</span>
          <span className="shrink-0 rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-[var(--muted-foreground)]">
            {data.aspectId}
          </span>
        </div>
        <div className="overflow-hidden rounded-xl bg-[var(--surface-2)]">
          <img
            src={data.dataUrl}
            alt={data.title}
            draggable={false}
            style={{ height: data.nodeH - 48 }}
            className="w-full object-cover"
          />
        </div>
      </div>
    </>
  );
};

const StickyNoteNode: React.FC<NodeProps<Node<NoteData, 'note'>>> = ({ id, data, selected }) => {
  return (
    <>
      <NodeToolbar isVisible={Boolean(selected)} position={Position.Top} offset={10}>
        <div className="aos-glass-rail flex items-center gap-1 rounded-xl px-1.5 py-1 shadow-xl">
          <button
            type="button"
            onClick={() => data.onDuplicate?.(id)}
            className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            title="复制便签"
          >
            <Copy size={13} />
          </button>
          <button
            type="button"
            onClick={() => data.onDelete?.(id)}
            className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-rose-500/15 hover:text-rose-500"
            title="删除便签"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </NodeToolbar>
      <div
        className={cn(
          'w-[248px] rounded-2xl border p-3.5 shadow-lg backdrop-blur-xl',
          data.noteColor === 'amber'
            ? 'border-amber-300/60 bg-amber-50/90 text-amber-950 dark:border-amber-500/35 dark:bg-amber-950/75 dark:text-amber-100'
            : 'border-indigo-300/60 bg-indigo-50/90 text-indigo-950 dark:border-indigo-500/35 dark:bg-indigo-950/75 dark:text-indigo-100',
          selected && 'ring-2 ring-[var(--primary)]',
        )}
      >
        <div className="mb-2 flex items-center gap-1.5 text-xs font-bold">
          <StickyNote size={13} />
          <span>{data.title}</span>
        </div>
        <textarea
          value={data.text}
          onChange={(e) => data.onChangeText?.(id, e.target.value)}
          rows={4}
          className="nodrag nowheel w-full resize-none bg-transparent text-xs leading-relaxed outline-none select-text"
        />
      </div>
    </>
  );
};

const NODE_TYPES: NodeTypes = {
  artwork: ArtworkNode,
  note: StickyNoteNode,
};

const INITIAL_NODES: StudioNode[] = [
  {
    id: 'art-1',
    type: 'artwork',
    position: { x: 64, y: 80 },
    data: {
      kind: 'artwork',
      title: '品牌周年庆典主视觉海报',
      prompt: '设计一张高端大气的企业品牌周年庆典主视觉海报，蓝金渐变天空与现代城市天际线，居中立体数字与极简中文排版，电影级体积光',
      model: 'gpt-image-2.5',
      aspectId: '3:4',
      resolution: '2K',
      quality: 'balanced',
      width: 1152,
      height: 1536,
      durationSec: 18.4,
      createdAt: '今天 16:40',
      liked: true,
      dataUrl: buildStudioPosterSvg({
        title: '品牌周年庆典',
        subtitle: '十五载同行 · 再启新程 · STUDIO EDITION',
        palette: PALETTES[0],
        aspectW: 768,
        aspectH: 1024,
        badge: 'AGENTICOS STUDIO',
      }),
      nodeW: 256,
      nodeH: 360,
    },
  },
  {
    id: 'art-2',
    type: 'artwork',
    position: { x: 432, y: 32 },
    data: {
      kind: 'artwork',
      title: '周年庆典 · 紫金光晕变体',
      prompt: '在原周年庆典海报基础上改为深紫与靛蓝玻璃折射质感，增强主标题金属光泽，保留极简构图',
      model: 'flux-pro-ultra',
      aspectId: '3:4',
      resolution: '2K',
      quality: 'fine',
      width: 1152,
      height: 1536,
      durationSec: 21.3,
      createdAt: '今天 16:45',
      liked: false,
      dataUrl: buildStudioPosterSvg({
        title: '周年庆典 · 精修版',
        subtitle: '紫金流光玻璃折射视觉变体',
        palette: PALETTES[1],
        aspectW: 768,
        aspectH: 1024,
        badge: 'FLUX PRO ULTRA',
      }),
      nodeW: 256,
      nodeH: 360,
    },
  },
  {
    id: 'art-3',
    type: 'artwork',
    position: { x: 432, y: 432 },
    data: {
      kind: 'artwork',
      title: '周年庆典 · 横版大屏 KV',
      prompt: '将品牌周年主视觉延展为 16:9 发布会大屏横版主视觉，清透青蓝科技光晕，左侧留白放演讲信息',
      model: 'seedream-3.0',
      aspectId: '16:9',
      resolution: '2K',
      quality: 'balanced',
      width: 1920,
      height: 1080,
      durationSec: 14.8,
      createdAt: '今天 16:49',
      liked: false,
      dataUrl: buildStudioPosterSvg({
        title: 'KEYNOTE STAGE KV',
        subtitle: '16:9 发布会主屏延展视觉方案',
        palette: PALETTES[2],
        aspectW: 1280,
        aspectH: 720,
        badge: 'SEEDREAM 3.0',
      }),
      nodeW: 304,
      nodeH: 214,
    },
  },
  {
    id: 'note-1',
    type: 'note',
    position: { x: 64, y: 480 },
    data: {
      kind: 'note',
      title: '视觉风格备忘',
      text: '1. 主视觉保持冷暖对比光影\n2. 底部产品列阵留足呼吸感\n3. 导出前确认 2K 清晰度文字边缘',
      noteColor: 'amber',
    },
  },
];

const INITIAL_EDGES: Edge[] = [
  {
    id: 'e-art1-art2',
    source: 'art-1',
    target: 'art-2',
    label: '指令改图',
    animated: true,
    style: { stroke: '#6366f1', strokeWidth: 2 },
    labelStyle: { fill: '#ffffff', fontSize: 10, fontWeight: 600 },
    labelBgStyle: { fill: '#4f46e5', fillOpacity: 0.92 },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 10,
  },
  {
    id: 'e-art1-art3',
    source: 'art-1',
    target: 'art-3',
    label: '画幅延展',
    animated: true,
    style: { stroke: '#0ea5e9', strokeWidth: 2 },
    labelStyle: { fill: '#ffffff', fontSize: 10, fontWeight: 600 },
    labelBgStyle: { fill: '#0284c7', fillOpacity: 0.92 },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 10,
  },
];

const CreativeCanvasInner: React.FC = () => {
  const navigate = useNavigate();
  const [user] = useState(() => getStoredUser());
  const isAdmin = canEnterAdmin();
  const { fitView, zoomIn, zoomOut, getZoom, screenToFlowPosition } = useReactFlow();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [canvasMode, setCanvasMode] = useState<CanvasMode>('infinite');
  const [tool, setTool] = useState<InfiniteTool>('select');
  const [nodes, setNodes, onNodesChange] = useNodesState<StudioNode>(INITIAL_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(INITIAL_EDGES);
  const [activeId, setActiveId] = useState<string>('art-1');
  const [zoomPct, setZoomPct] = useState<number>(100);
  const [focusZoom, setFocusZoom] = useState<number>(100);
  const [isDraggingFile, setIsDraggingFile] = useState(false);

  // Right inspector state
  const [prompt, setPrompt] = useState((INITIAL_NODES[0].data as ArtworkData).prompt);
  const [model, setModel] = useState(MODEL_OPTIONS[0].id);
  const [aspectId, setAspectId] = useState<string>('3:4');
  const [resolution, setResolution] = useState<ResolutionTier>('2K');
  const [quality, setQuality] = useState<QualityTier>('balanced');
  const [batchCount, setBatchCount] = useState<number>(1);
  const [refImages, setRefImages] = useState<{ name: string; url: string }[]>([]);
  const [showCameraMenu, setShowCameraMenu] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // Focus mode inpainting & quick edit
  const [inpaintMode, setInpaintMode] = useState(false);
  const [brushSize, setBrushSize] = useState(28);
  const [editBarOpen, setEditBarOpen] = useState(false);
  const [editInstruction, setEditInstruction] = useState('');
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const refFileInputRef = useRef<HTMLInputElement | null>(null);

  const activeNode = useMemo(
    () =>
      nodes.find((n) => n.id === activeId) ??
      nodes.find((n) => n.data.kind === 'artwork') ??
      nodes[0],
    [nodes, activeId],
  );

  const activeArtworkData = activeNode?.data.kind === 'artwork' ? (activeNode.data as ArtworkData) : null;

  const selectedAspect = useMemo(
    () => ASPECT_OPTIONS.find((o) => o.id === aspectId) ?? ASPECT_OPTIONS[1],
    [aspectId],
  );

  const outputPixels = useMemo(() => {
    const scale = TIER_SCALE[resolution];
    return {
      w: Math.round(selectedAspect.w * scale),
      h: Math.round(selectedAspect.h * scale),
    };
  }, [selectedAspect, resolution]);

  const clearMask = useCallback(() => {
    const cvs = maskCanvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, cvs.width, cvs.height);
  }, []);

  useEffect(() => {
    clearMask();
  }, [activeId, inpaintMode, clearMask]);

  // Sync keyboard shortcuts V (select) / H (hand)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }
      if (e.key.toLowerCase() === 'v') setTool('select');
      else if (e.key.toLowerCase() === 'h') setTool('hand');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const syncInspectorFromNode = useCallback((node: StudioNode) => {
    setActiveId(node.id);
    if (node.data.kind === 'artwork') {
      const d = node.data as ArtworkData;
      setPrompt(d.prompt);
      setAspectId(d.aspectId);
      setResolution(d.resolution);
      setQuality(d.quality);
      setModel(d.model);
    }
  }, []);

  const handleDownloadById = useCallback(
    (id: string) => {
      const target = nodes.find((n) => n.id === id);
      if (!target || target.data.kind !== 'artwork') return;
      const d = target.data as ArtworkData;
      const link = document.createElement('a');
      link.href = d.dataUrl;
      link.download = `${d.title.replace(/\s+/g, '_')}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      toast.success('已开始下载原图');
    },
    [nodes],
  );

  const handleDeleteById = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id));
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
      toast.success('已删除画布元素');
    },
    [setNodes, setEdges],
  );

  const handleDuplicateById = useCallback(
    (id: string) => {
      const orig = nodes.find((n) => n.id === id);
      if (!orig) return;
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
      setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), cloned]);
      setActiveId(newId);
      toast.success('已复制节点');
    },
    [nodes, setNodes],
  );

  const handleGenerate = useCallback(
    async (opts?: { overridePrompt?: string; parentId?: string; edgeLabel?: string }) => {
      const finalPrompt = (opts?.overridePrompt ?? prompt).trim();
      if (!finalPrompt) {
        toast.error('请先输入画面描述提示词');
        return;
      }
      setIsGenerating(true);
      const startTs = performance.now();
      await new Promise((r) => setTimeout(r, 800));

      const parentNode = opts?.parentId ? nodes.find((n) => n.id === opts.parentId) : undefined;
      const isLandscape = selectedAspect.w > selectedAspect.h;
      const nodeW = isLandscape ? 304 : 256;
      const nodeH = isLandscape ? 214 : 360;

      const createdNodes: StudioNode[] = [];
      const createdEdges: Edge[] = [];

      for (let idx = 0; idx < batchCount; idx++) {
        const palette = PALETTES[(nodes.length + idx) % PALETTES.length];
        const shortTitle = finalPrompt.replace(/[，。,.!?！？].*$/, '').slice(0, 14) || '新建视觉作品';
        const newId = `art-${Date.now()}-${idx}`;
        const parentW =
          parentNode && parentNode.data.kind === 'artwork' ? (parentNode.data as ArtworkData).nodeW : 256;
        const posX = parentNode
          ? parentNode.position.x + parentW + 112
          : 64 + ((nodes.length + idx) % 3) * 352;
        const posY = parentNode
          ? parentNode.position.y + idx * (nodeH + 36)
          : 64 + Math.floor((nodes.length + idx) / 3) * 400;

        createdNodes.push({
          id: newId,
          type: 'artwork',
          selected: idx === 0,
          position: { x: posX, y: posY },
          data: {
            kind: 'artwork',
            title: batchCount > 1 ? `${shortTitle} #${idx + 1}` : shortTitle,
            prompt: finalPrompt,
            model,
            aspectId,
            resolution,
            quality,
            width: outputPixels.w,
            height: outputPixels.h,
            durationSec: Number((((performance.now() - startTs) / 1000) + 1.0 + idx * 0.3).toFixed(1)),
            createdAt: '刚刚',
            liked: false,
            dataUrl: buildStudioPosterSvg({
              title: shortTitle,
              subtitle: finalPrompt.slice(0, 28),
              palette,
              aspectW: selectedAspect.w,
              aspectH: selectedAspect.h,
              badge: MODEL_OPTIONS.find((m) => m.id === model)?.label.toUpperCase() || 'STUDIO',
            }),
            nodeW,
            nodeH,
          },
        });

        if (parentNode) {
          createdEdges.push({
            id: `e-${parentNode.id}-${newId}`,
            source: parentNode.id,
            target: newId,
            label: opts?.edgeLabel ?? '衍生变体',
            animated: true,
            style: { stroke: '#6366f1', strokeWidth: 2 },
            labelStyle: { fill: '#ffffff', fontSize: 10, fontWeight: 600 },
            labelBgStyle: { fill: '#4f46e5', fillOpacity: 0.92 },
            labelBgPadding: [6, 3],
            labelBgBorderRadius: 10,
          });
        }
      }

      setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...createdNodes]);
      if (createdEdges.length > 0) {
        setEdges((eds) => [...eds, ...createdEdges]);
      }
      setActiveId(createdNodes[0].id);
      setEditBarOpen(false);
      setEditInstruction('');
      setInpaintMode(false);
      setIsGenerating(false);
      toast.success(`已生成 ${createdNodes.length} 张作品${parentNode ? '并建立衍生连线' : ''}`);
    },
    [prompt, nodes, selectedAspect, batchCount, model, aspectId, resolution, quality, outputPixels, setNodes, setEdges],
  );

  // Inject interactive callbacks into nodes cleanly
  const decoratedNodes = useMemo<StudioNode[]>(
    () =>
      nodes.map((node) => {
        if (node.type === 'artwork') {
          return {
            ...node,
            data: {
              ...(node.data as ArtworkData),
              onDerive: (id: string) => {
                const src = nodes.find((n) => n.id === id);
                if (src && src.data.kind === 'artwork') {
                  handleGenerate({
                    overridePrompt: (src.data as ArtworkData).prompt,
                    parentId: id,
                    edgeLabel: '衍生变体',
                  });
                }
              },
              onOpenEdit: (id: string) => {
                const src = nodes.find((n) => n.id === id);
                if (src) syncInspectorFromNode(src);
                setEditBarOpen(true);
              },
              onFocus: (id: string) => {
                const src = nodes.find((n) => n.id === id);
                if (src) syncInspectorFromNode(src);
                setCanvasMode('focus');
                setFocusZoom(100);
              },
              onDownload: handleDownloadById,
              onDuplicate: handleDuplicateById,
              onDelete: handleDeleteById,
            },
          };
        }
        return {
          ...node,
          data: {
            ...(node.data as NoteData),
            onChangeText: (id: string, text: string) => {
              setNodes((nds) =>
                nds.map((n) =>
                  n.id === id && n.type === 'note'
                    ? { ...n, data: { ...(n.data as NoteData), text } }
                    : n,
                ),
              );
            },
            onDuplicate: handleDuplicateById,
            onDelete: handleDeleteById,
          },
        };
      }),
    [nodes, handleGenerate, syncInspectorFromNode, handleDownloadById, handleDuplicateById, handleDeleteById, setNodes],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
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
          eds,
        ),
      );
    },
    [setEdges],
  );

  const handleAddNote = () => {
    const newId = `note-${Date.now()}`;
    const noteNode: StudioNode = {
      id: newId,
      type: 'note',
      selected: true,
      position: { x: 160 + (nodes.length % 4) * 48, y: 160 + (nodes.length % 4) * 32 },
      data: {
        kind: 'note',
        title: '创意便签',
        text: '记录配色方案、主体构图或修改备注...',
        noteColor: 'indigo',
      },
    };
    setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), noteNode]);
    setActiveId(newId);
    setCanvasMode('infinite');
    toast.success('已在画布添加便签卡片');
  };

  const handleTidyUp = () => {
    const cols = 3;
    const colW = 352;
    const rowH = 416;
    setNodes((nds) =>
      nds.map((n, idx) => ({
        ...n,
        position: { x: 64 + (idx % cols) * colW, y: 64 + Math.floor(idx / cols) * rowH },
      })),
    );
    setTimeout(() => fitView({ padding: 0.16, duration: 350 }), 40);
    toast.success('已按网格自动整理画布');
  };

  const handleStageDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingFile(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith('image/'));
    if (files.length === 0) return;
    const pos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const added: StudioNode[] = files.slice(0, 6).map((file, idx) => ({
      id: `upload-${Date.now()}-${idx}`,
      type: 'artwork',
      selected: idx === 0,
      position: { x: pos.x + idx * 40, y: pos.y + idx * 40 },
      data: {
        kind: 'artwork',
        title: file.name.replace(/\.[^.]+$/, ''),
        prompt: `导入参考图：${file.name}`,
        model,
        aspectId: '3:4',
        resolution: '2K',
        quality: 'balanced',
        width: 1024,
        height: 1024,
        durationSec: 0,
        createdAt: '刚刚导入',
        liked: false,
        dataUrl: URL.createObjectURL(file),
        nodeW: 256,
        nodeH: 320,
      },
    }));
    setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...added]);
    setActiveId(added[0].id);
    setCanvasMode('infinite');
    toast.success(`已将 ${added.length} 张本地图片置入无限画布`);
  };

  const handleRefFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const added = Array.from(files)
      .slice(0, 4)
      .map((f) => ({ name: f.name, url: URL.createObjectURL(f) }));
    setRefImages((prev) => [...prev, ...added].slice(0, 4));
    toast.success(`已添加 ${added.length} 张参考图`);
    e.target.value = '';
  };

  const handlePolishPrompt = () => {
    const base = prompt.trim() || '高端现代科技产品视觉海报';
    if (base.includes('8K 超清细节')) {
      toast.info('当前提示词已包含高清修饰词');
      return;
    }
    setPrompt(`${base}，电影级柔和体积光，通透玻璃材质反射，精致中文视觉排版，8K 超清细节`);
    toast.success('已智能润色画面提示词');
  };

  const handleCopyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedPrompt(true);
      toast.success('提示词已复制');
      setTimeout(() => setCopiedPrompt(false), 1600);
    } catch {
      toast.error('复制失败，请手动复制');
    }
  };

  const handleToggleLike = () => {
    if (!activeNode || activeNode.type !== 'artwork') return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === activeNode.id && n.type === 'artwork'
          ? { ...n, data: { ...(n.data as ArtworkData), liked: !(n.data as ArtworkData).liked } }
          : n,
      ),
    );
  };

  const paintAt = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const cvs = maskCanvasRef.current;
    if (!cvs) return;
    const rect = cvs.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * cvs.width;
    const y = ((e.clientY - rect.top) / rect.height) * cvs.height;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = 'rgba(99, 102, 241, 0.48)';
    ctx.beginPath();
    ctx.arc(x, y, brushSize, 0, Math.PI * 2);
    ctx.fill();
  };

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)] font-sans select-none">
      <div className="aos-ambient-bg" aria-hidden="true" />

      {/* 1) Left Floating Collapsible Sidebar */}
      <aside
        className={cn(
          'aos-glass-rail relative z-20 m-3 mr-0 hidden flex-col justify-between rounded-3xl p-3 transition-all duration-300 lg:flex',
          sidebarCollapsed ? 'w-[72px]' : 'w-[228px]',
        )}
      >
        <div className="flex flex-col gap-5">
          <div className="flex items-center justify-between px-1.5 pt-1">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="flex items-center gap-2 focus-visible:outline-none"
              aria-label="返回首页"
            >
              <Logo iconSize={30} showText={!sidebarCollapsed} />
            </button>
            <button
              type="button"
              onClick={() => setSidebarCollapsed((v) => !v)}
              className="flex h-8 w-8 items-center justify-center rounded-xl text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
              title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
            </button>
          </div>

          <nav className="flex flex-col gap-1" aria-label="创作画布导航">
            {[
              { label: '创作首页', icon: HomeIcon, path: '/', active: false },
              { label: 'AI 智能体', icon: Bot, path: '/agents', active: false },
              { label: '创作画布', icon: Palette, path: '/canvas', active: true },
              { label: '作品库', icon: LayoutGrid, path: '/gallery', active: false },
              { label: '对话工作台', icon: MessageSquare, path: '/chat', active: false },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.path}
                  type="button"
                  onClick={() => navigate(item.path)}
                  className={cn(
                    'flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition-all',
                    item.active
                      ? 'bg-[var(--foreground)] text-[var(--background)] shadow-md'
                      : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]/80 hover:text-[var(--foreground)]',
                    sidebarCollapsed && 'justify-center px-0',
                  )}
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <Icon size={17} className="shrink-0" />
                  {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
                </button>
              );
            })}
            {isAdmin && (
              <button
                type="button"
                onClick={() => navigate('/admin')}
                className={cn(
                  'mt-1 flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium text-[var(--muted-foreground)] transition-all hover:bg-[var(--surface-2)]/80 hover:text-[var(--foreground)]',
                  sidebarCollapsed && 'justify-center px-0',
                )}
                title={sidebarCollapsed ? '管理后台' : undefined}
              >
                <Shield size={17} className="shrink-0" />
                {!sidebarCollapsed && <span className="truncate">管理后台</span>}
              </button>
            )}
          </nav>

          {/* Canvas Elements List */}
          {!sidebarCollapsed && (
            <div className="mt-2 border-t border-[var(--border-subtle)] pt-4">
              <div className="mb-2.5 flex items-center justify-between px-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                  画布元素
                </span>
                <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-semibold tabular-nums text-[var(--muted-foreground)]">
                  {nodes.length}
                </span>
              </div>
              <div className="flex max-h-[240px] flex-col gap-1.5 overflow-y-auto pr-0.5">
                {nodes.map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => {
                      syncInspectorFromNode(node);
                      setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === node.id })));
                    }}
                    className={cn(
                      'flex items-center gap-2.5 rounded-xl p-1.5 text-left transition-all',
                      activeId === node.id
                        ? 'bg-[var(--primary)]/10 ring-1 ring-[var(--primary)]/30'
                        : 'hover:bg-[var(--surface-2)]/70',
                    )}
                  >
                    {node.data.kind === 'artwork' ? (
                      <img
                        src={(node.data as ArtworkData).dataUrl}
                        alt={(node.data as ArtworkData).title}
                        className="h-9 w-9 shrink-0 rounded-lg object-cover ring-1 ring-[var(--border-subtle)]"
                      />
                    ) : (
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-300">
                        <StickyNote size={15} />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-[var(--foreground)]">
                        {node.data.title}
                      </p>
                      <p className="text-[10px] tabular-nums text-[var(--muted-foreground)]">
                        {node.data.kind === 'artwork'
                          ? `${(node.data as ArtworkData).aspectId} · ${(node.data as ArtworkData).resolution}`
                          : '便签卡片'}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-1 pt-3">
          {!sidebarCollapsed && (
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)]/15 text-xs font-bold text-[var(--primary)]">
                {(user?.name || user?.email || 'U').slice(0, 1).toUpperCase()}
              </div>
              <span className="truncate text-xs font-semibold text-[var(--foreground)]">
                {user?.name || user?.email || '设计师'}
              </span>
            </div>
          )}
          <ThemeToggle />
        </div>
      </aside>

      {/* 2) Center Canvas Area */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col p-3">
        {/* Top Canvas Toolbar */}
        <header className="aos-glass-surface mb-3 flex h-[52px] shrink-0 items-center justify-between gap-3 rounded-2xl px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            >
              <ArrowLeft size={14} />
              返回
            </button>

            <div className="h-4 w-px bg-[var(--border-subtle)]" />

            <div className="flex items-center gap-1 rounded-xl bg-[var(--surface-2)]/80 p-1">
              <button
                type="button"
                onClick={() => setCanvasMode('infinite')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold transition-all',
                  canvasMode === 'infinite'
                    ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                    : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                )}
              >
                <Grid size={13} />
                无限画布
              </button>
              <button
                type="button"
                onClick={() => {
                  setCanvasMode('focus');
                  setFocusZoom(100);
                }}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold transition-all',
                  canvasMode === 'focus'
                    ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                    : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                )}
              >
                <Focus size={13} />
                专注检视
              </button>
            </div>

            {activeArtworkData && (
              <div className="hidden min-w-0 items-center gap-2 xl:flex">
                <span className="truncate text-xs font-semibold text-[var(--foreground)]">
                  {activeArtworkData.title}
                </span>
                <span className="rounded-md bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-[var(--muted-foreground)]">
                  {activeArtworkData.width} × {activeArtworkData.height}
                </span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {canvasMode === 'infinite' && (
              <button
                type="button"
                onClick={handleTidyUp}
                className="hidden h-8 items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 px-2.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] sm:inline-flex"
                title="一键网格整理"
              >
                <LayoutGrid size={13} />
                整理
              </button>
            )}

            <div className="flex items-center gap-0.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 px-1 py-0.5">
              <button
                type="button"
                onClick={() => {
                  if (canvasMode === 'infinite') {
                    zoomOut({ duration: 180 });
                    setTimeout(() => setZoomPct(Math.round(getZoom() * 100)), 200);
                  } else {
                    setFocusZoom((z) => Math.max(40, z - 10));
                  }
                }}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                aria-label="缩小"
              >
                <Minus size={13} />
              </button>
              <button
                type="button"
                onClick={() => {
                  if (canvasMode === 'infinite') {
                    fitView({ padding: 0.16, duration: 300 });
                    setTimeout(() => setZoomPct(Math.round(getZoom() * 100)), 320);
                  } else {
                    setFocusZoom(100);
                  }
                }}
                className="min-w-[46px] text-center text-xs font-semibold tabular-nums text-[var(--foreground)]"
                title={canvasMode === 'infinite' ? '点击适配全部画板' : '重置 100%'}
              >
                {canvasMode === 'infinite' ? zoomPct : focusZoom}%
              </button>
              <button
                type="button"
                onClick={() => {
                  if (canvasMode === 'infinite') {
                    zoomIn({ duration: 180 });
                    setTimeout(() => setZoomPct(Math.round(getZoom() * 100)), 200);
                  } else {
                    setFocusZoom((z) => Math.min(200, z + 10));
                  }
                }}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                aria-label="放大"
              >
                <Plus size={13} />
              </button>
            </div>
            <button
              type="button"
              onClick={() => fitView({ padding: 0.16, duration: 300 })}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
              title="居中全部画板 (Fit View)"
            >
              <Maximize2 size={14} />
            </button>
          </div>
        </header>

        {/* Main Interactive Stage */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDraggingFile(true);
          }}
          onDragLeave={() => setIsDraggingFile(false)}
          onDrop={handleStageDrop}
          className={cn(
            'relative flex flex-1 flex-col overflow-hidden rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/45 backdrop-blur-md transition-colors',
            isDraggingFile && 'ring-2 ring-[var(--primary)] bg-[var(--primary)]/5',
          )}
        >
          {canvasMode === 'infinite' ? (
            <ReactFlow
              nodes={decoratedNodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => syncInspectorFromNode(node as StudioNode)}
              onMoveEnd={(_, viewport) => setZoomPct(Math.round(viewport.zoom * 100))}
              fitView
              fitViewOptions={{ padding: 0.16 }}
              snapToGrid
              snapGrid={[16, 16]}
              minZoom={0.2}
              maxZoom={2.5}
              panOnScroll
              zoomOnPinch
              selectionOnDrag={tool === 'select'}
              panOnDrag={tool === 'hand' ? true : [1, 2]}
              deleteKeyCode={['Delete', 'Backspace']}
              proOptions={{ hideAttribution: true }}
              className="aos-xyflow-canvas h-full w-full"
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={24}
                size={1.4}
                color="rgba(99, 102, 241, 0.28)"
              />

              <MiniMap
                pannable
                zoomable
                nodeBorderRadius={6}
                nodeColor={(n) => (n.type === 'note' ? '#f59e0b' : '#6366f1')}
                maskColor="rgba(15, 23, 42, 0.14)"
                className="!rounded-2xl !border !border-[var(--border-subtle)] !bg-[var(--surface-1)]/85 !shadow-lg !backdrop-blur-xl"
              />

              {/* Bottom-Center Floating Tool Dock */}
              <Panel position="bottom-center" className="!mb-4">
                <div className="aos-glass-rail flex items-center gap-1 rounded-2xl p-1.5 shadow-xl">
                  <button
                    type="button"
                    onClick={() => setTool('select')}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all',
                      tool === 'select'
                        ? 'bg-[var(--foreground)] text-[var(--background)] shadow-sm'
                        : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
                    )}
                    title="选择与框选 (V)"
                  >
                    <MousePointer2 size={14} />
                    选择
                  </button>
                  <button
                    type="button"
                    onClick={() => setTool('hand')}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all',
                      tool === 'hand'
                        ? 'bg-[var(--foreground)] text-[var(--background)] shadow-sm'
                        : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
                    )}
                    title="抓手平移 (H)"
                  >
                    <Hand size={14} />
                    抓手
                  </button>
                  <div className="mx-0.5 h-5 w-px bg-[var(--border-subtle)]" />
                  <button
                    type="button"
                    onClick={handleAddNote}
                    className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
                    title="添加创意便签"
                  >
                    <StickyNote size={14} />
                    便签
                  </button>
                  <button
                    type="button"
                    onClick={() => refFileInputRef.current?.click()}
                    className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
                    title="上传参考图"
                  >
                    <Upload size={14} />
                    置图
                  </button>
                </div>
              </Panel>

              <Panel position="bottom-left" className="!mb-4 !ml-3 hidden xl:block">
                <div className="rounded-xl bg-[var(--surface-1)]/75 px-3 py-1.5 text-[11px] text-[var(--muted-foreground)] backdrop-blur-md">
                  由 @xyflow/react 驱动 · 滚轮平移 / 双指缩放 · 拖入本地图片直达画布
                </div>
              </Panel>
            </ReactFlow>
          ) : (
            /* Focus View with Inpainting Mask */
            <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-6 pb-24 pt-6">
              <AnimatePresence>
                {inpaintMode && (
                  <motion.div
                    initial={{ opacity: 0, y: -12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    className="aos-glass-rail absolute top-4 z-30 flex items-center gap-3 rounded-2xl px-4 py-2 text-xs"
                  >
                    <span className="flex items-center gap-1.5 font-semibold text-[var(--primary)]">
                      <Brush size={14} />
                      局部精修涂抹模式
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-[var(--muted-foreground)]">画笔</span>
                      <input
                        type="range"
                        min={10}
                        max={64}
                        value={brushSize}
                        onChange={(e) => setBrushSize(Number(e.target.value))}
                        className="w-20 accent-[var(--primary)]"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={clearMask}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-medium text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                    >
                      <Eraser size={13} />
                      清空选区
                    </button>
                    <button
                      type="button"
                      onClick={() => setInpaintMode(false)}
                      className="rounded-lg bg-[var(--surface-2)] px-2 py-1 font-medium text-[var(--foreground)] hover:opacity-80"
                    >
                      完成
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>

              {activeArtworkData && (
                <motion.div
                  key={activeNode?.id}
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: focusZoom / 100 }}
                  transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                  className="relative max-h-[66vh] max-w-[78%] overflow-hidden rounded-2xl shadow-[0_28px_70px_-16px_rgba(15,23,42,0.35)] ring-1 ring-white/25"
                >
                  <img
                    src={activeArtworkData.dataUrl}
                    alt={activeArtworkData.title}
                    draggable={false}
                    className="block max-h-[66vh] w-auto object-contain"
                  />

                  {inpaintMode && (
                    <canvas
                      ref={maskCanvasRef}
                      width={800}
                      height={1000}
                      onPointerDown={(e) => {
                        drawingRef.current = true;
                        paintAt(e);
                      }}
                      onPointerMove={(e) => {
                        if (drawingRef.current) paintAt(e);
                      }}
                      onPointerUp={() => {
                        drawingRef.current = false;
                      }}
                      onPointerLeave={() => {
                        drawingRef.current = false;
                      }}
                      className="absolute inset-0 h-full w-full cursor-crosshair"
                    />
                  )}

                  <AnimatePresence>
                    {isGenerating && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950/55 text-white backdrop-blur-md"
                      >
                        <Loader2 size={28} className="animate-spin text-indigo-300" />
                        <span className="text-xs font-semibold tracking-wide">正在渲染高精画面...</span>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )}

              {/* Focus Bottom Floating Action Dock */}
              {activeArtworkData && activeNode && (
                <div className="aos-glass-rail absolute bottom-5 z-20 flex flex-wrap items-center gap-1.5 rounded-2xl p-1.5 shadow-xl">
                  <button
                    type="button"
                    onClick={() => handleDownloadById(activeNode.id)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--foreground)] px-3.5 py-2 text-xs font-semibold text-[var(--background)] transition-transform hover:opacity-90 active:scale-95"
                  >
                    <Download size={14} />
                    下载原图
                  </button>
                  <button
                    type="button"
                    onClick={() => setInpaintMode((v) => !v)}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition-all active:scale-95',
                      inpaintMode
                        ? 'bg-[var(--primary)]/15 text-[var(--primary)] ring-1 ring-[var(--primary)]/35'
                        : 'text-[var(--foreground)] hover:bg-[var(--surface-2)]',
                    )}
                  >
                    <Brush size={14} />
                    局部精修
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditBarOpen((v) => !v)}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition-all active:scale-95',
                      editBarOpen
                        ? 'bg-[var(--primary)]/15 text-[var(--primary)] ring-1 ring-[var(--primary)]/35'
                        : 'text-[var(--foreground)] hover:bg-[var(--surface-2)]',
                    )}
                  >
                    <Wand2 size={14} />
                    指令改图
                  </button>
                  <button
                    type="button"
                    onClick={() => handleGenerate({ parentId: activeNode.id, edgeLabel: '重新生成' })}
                    disabled={isGenerating}
                    className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition-all hover:bg-[var(--surface-2)] active:scale-95 disabled:opacity-50"
                  >
                    <RotateCcw size={14} />
                    重新生成
                  </button>
                  <div className="mx-0.5 h-5 w-px bg-[var(--border-subtle)]" />
                  <button
                    type="button"
                    onClick={handleToggleLike}
                    className={cn(
                      'flex h-8 w-8 items-center justify-center rounded-xl transition-all hover:bg-[var(--surface-2)]',
                      activeArtworkData.liked ? 'text-rose-500' : 'text-[var(--muted-foreground)]',
                    )}
                    aria-label="收藏作品"
                  >
                    <Heart size={15} className={activeArtworkData.liked ? 'fill-rose-500' : ''} />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Inline Instruction Edit Bar */}
          <AnimatePresence>
            {editBarOpen && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 12 }}
                className="aos-composer-glass absolute bottom-20 left-1/2 z-30 flex w-full max-w-lg -translate-x-1/2 items-center gap-2 rounded-2xl p-2"
              >
                <Wand2 size={16} className="ml-2 shrink-0 text-[var(--primary)]" />
                <input
                  type="text"
                  value={editInstruction}
                  onChange={(e) => setEditInstruction(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && editInstruction.trim()) {
                      handleGenerate({
                        overridePrompt: `${prompt}；调整要求：${editInstruction.trim()}`,
                        parentId: activeNode?.type === 'artwork' ? activeNode.id : undefined,
                        edgeLabel: '指令改图',
                      });
                    }
                  }}
                  placeholder="输入改图指令，例如：把色调改成暖金色，增强前景光晕..."
                  className="flex-1 bg-transparent text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] select-text"
                />
                <button
                  type="button"
                  onClick={() =>
                    handleGenerate({
                      overridePrompt: `${prompt}；调整要求：${editInstruction.trim()}`,
                      parentId: activeNode?.type === 'artwork' ? activeNode.id : undefined,
                      edgeLabel: '指令改图',
                    })
                  }
                  disabled={!editInstruction.trim() || isGenerating}
                  className="rounded-xl bg-[var(--primary)] px-3 py-1.5 text-xs font-semibold text-[var(--primary-foreground)] transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  执行改图
                </button>
                <button
                  type="button"
                  onClick={() => setEditBarOpen(false)}
                  className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]"
                >
                  <X size={14} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 3) Right Inspector Control Panel */}
      <aside className="aos-glass-rail relative z-20 m-3 ml-0 flex w-[332px] shrink-0 flex-col overflow-hidden rounded-3xl">
        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          {/* Prompt Box */}
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/55 p-3">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              placeholder="描述你想设计的画面、主体、材质光影与版式风格..."
              className="w-full resize-none bg-transparent text-xs leading-relaxed text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] select-text"
            />

            {refImages.length > 0 && (
              <div className="mb-2.5 mt-1 flex flex-wrap gap-1.5">
                {refImages.map((img, i) => (
                  <div
                    key={`${img.name}-${i}`}
                    className="group relative h-11 w-11 overflow-hidden rounded-lg ring-1 ring-[var(--border-subtle)]"
                  >
                    <img src={img.url} alt={img.name} className="h-full w-full object-cover" />
                    <button
                      type="button"
                      onClick={() => setRefImages((prev) => prev.filter((_, idx) => idx !== i))}
                      className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-black/65 text-white opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <input
              ref={refFileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleRefFileUpload}
              className="hidden"
            />

            <div className="relative mt-2 flex flex-wrap items-center justify-between gap-1.5 border-t border-[var(--border-subtle)] pt-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => refFileInputRef.current?.click()}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1 text-[11px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--primary)]/40"
                >
                  <Upload size={11} />
                  参考图
                </button>
                <button
                  type="button"
                  onClick={() => setShowCameraMenu((v) => !v)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1 text-[11px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--primary)]/40"
                >
                  <Layers size={11} />
                  镜头与构图
                </button>
                <button
                  type="button"
                  onClick={handlePolishPrompt}
                  className="inline-flex items-center gap-1 rounded-lg bg-[var(--primary)]/12 px-2 py-1 text-[11px] font-semibold text-[var(--primary)] transition-colors hover:bg-[var(--primary)]/20"
                >
                  <Sparkles size={11} />
                  润色
                </button>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleCopyPrompt}
                  className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-1)] hover:text-[var(--foreground)]"
                  title="复制提示词"
                >
                  {copiedPrompt ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                </button>
                <button
                  type="button"
                  onClick={() => setPrompt('')}
                  className="rounded-lg p-1 text-[var(--muted-foreground)] hover:bg-[var(--surface-1)] hover:text-rose-500"
                  title="清空"
                >
                  <Trash2 size={12} />
                </button>
              </div>

              <AnimatePresence>
                {showCameraMenu && (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 6 }}
                    className="aos-glass-rail absolute left-0 top-full z-30 mt-2 w-full rounded-2xl p-2 shadow-xl"
                  >
                    <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                      点击追加镜头与光影预设
                    </p>
                    {CAMERA_PRESETS.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => {
                          setPrompt((prev) => (prev.trim() ? `${prev.trim()}，${preset}` : preset));
                          setShowCameraMenu(false);
                        }}
                        className="block w-full rounded-xl px-2.5 py-1.5 text-left text-[11px] text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                      >
                        {preset}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </section>

          {/* Model Selection */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-[var(--foreground)]">模型</span>
              <button
                type="button"
                onClick={() => toast.info('模型列表已是最新')}
                className="inline-flex items-center gap-1 text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <RefreshCw size={11} />
                刷新列表
              </button>
            </div>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              aria-label="选择图像模型"
              className="h-10 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/85 px-3 text-xs font-semibold text-[var(--foreground)] outline-none transition-colors focus:border-[var(--primary)]"
            >
              {MODEL_OPTIONS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} · {m.badge}
                </option>
              ))}
            </select>
          </section>

          {/* Aspect Ratio */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-[var(--foreground)]">画幅比例</span>
              <span className="text-[11px] tabular-nums text-[var(--muted-foreground)]">
                {outputPixels.w} × {outputPixels.h} px
              </span>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {ASPECT_OPTIONS.map((opt) => {
                const active = aspectId === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setAspectId(opt.id)}
                    className={cn(
                      'flex items-center justify-center gap-1.5 rounded-xl border py-2 text-[11px] font-semibold transition-all',
                      active
                        ? 'border-transparent bg-[var(--foreground)] text-[var(--background)] shadow-sm'
                        : 'border-[var(--border-subtle)] bg-[var(--surface-1)]/70 text-[var(--foreground)] hover:bg-[var(--surface-2)]',
                    )}
                  >
                    <span
                      style={{ width: opt.iconW, height: opt.iconH }}
                      className={cn(
                        'inline-block rounded-[2px] border',
                        active ? 'border-[var(--background)]/80' : 'border-[var(--muted-foreground)]/70',
                      )}
                    />
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Resolution Tier */}
          <section>
            <span className="mb-2 block text-xs font-semibold text-[var(--foreground)]">清晰度档位</span>
            <div className="grid grid-cols-3 gap-1 rounded-xl bg-[var(--surface-2)]/80 p-1">
              {(['1K', '2K', '4K'] as ResolutionTier[]).map((tier) => (
                <button
                  key={tier}
                  type="button"
                  onClick={() => setResolution(tier)}
                  className={cn(
                    'rounded-lg py-1.5 text-xs font-semibold transition-all',
                    resolution === tier
                      ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                      : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                  )}
                >
                  {tier}
                </button>
              ))}
            </div>
          </section>

          {/* Detail Quality + Batch Count */}
          <section className="grid grid-cols-2 gap-3">
            <div>
              <span className="mb-2 block text-xs font-semibold text-[var(--foreground)]">细节档次</span>
              <div className="grid grid-cols-3 gap-0.5 rounded-xl bg-[var(--surface-2)]/80 p-1">
                {(
                  [
                    ['fast', '快速'],
                    ['balanced', '均衡'],
                    ['fine', '精细'],
                  ] as [QualityTier, string][]
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setQuality(key)}
                    className={cn(
                      'rounded-lg py-1 text-[11px] font-semibold transition-all',
                      quality === key
                        ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                        : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <span className="mb-2 block text-xs font-semibold text-[var(--foreground)]">生成数量</span>
              <div className="grid grid-cols-4 gap-0.5 rounded-xl bg-[var(--surface-2)]/80 p-1">
                {[1, 2, 3, 4].map((num) => (
                  <button
                    key={num}
                    type="button"
                    onClick={() => setBatchCount(num)}
                    className={cn(
                      'rounded-lg py-1 text-[11px] font-semibold tabular-nums transition-all',
                      batchCount === num
                        ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                        : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                    )}
                  >
                    {num}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Current Artwork Specs */}
          {activeArtworkData && (
            <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/45 p-3">
              <div className="mb-2.5 flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[var(--muted-foreground)]">当前作品参数</span>
                <span className="inline-flex items-center gap-1 text-[10px] text-[var(--muted-foreground)]">
                  <ImageIcon size={11} />
                  {activeArtworkData.createdAt}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-y-2.5 text-xs">
                <div>
                  <p className="text-[10px] text-[var(--muted-foreground)]">模型</p>
                  <p className="mt-0.5 font-semibold text-[var(--foreground)]">
                    {MODEL_OPTIONS.find((m) => m.id === activeArtworkData.model)?.label ?? activeArtworkData.model}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[var(--muted-foreground)]">输出尺寸</p>
                  <p className="mt-0.5 font-semibold tabular-nums text-[var(--foreground)]">
                    {activeArtworkData.width} × {activeArtworkData.height}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[var(--muted-foreground)]">比例 / 档位</p>
                  <p className="mt-0.5 font-semibold tabular-nums text-[var(--foreground)]">
                    {activeArtworkData.aspectId} · {activeArtworkData.resolution}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[var(--muted-foreground)]">耗时</p>
                  <p className="mt-0.5 font-semibold tabular-nums text-[var(--foreground)]">
                    {activeArtworkData.durationSec}s
                  </p>
                </div>
              </div>
            </section>
          )}
        </div>

        {/* Sticky Primary Generate CTA */}
        <div className="border-t border-[var(--border-subtle)] bg-[var(--surface-1)]/60 p-3.5 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => handleGenerate()}
            disabled={isGenerating}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-2xl bg-[var(--foreground)] text-sm font-semibold text-[var(--background)] shadow-lg transition-all hover:opacity-90 active:scale-[0.985] disabled:opacity-55"
          >
            {isGenerating ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                正在生成画面...
              </>
            ) : (
              <>
                <Sparkles size={16} />
                生成画面{batchCount > 1 ? ` · ${batchCount} 张` : ''}
              </>
            )}
          </button>
        </div>
      </aside>
    </div>
  );
};

export const CreativeCanvas: React.FC = () => (
  <ReactFlowProvider>
    <CreativeCanvasInner />
  </ReactFlowProvider>
);
