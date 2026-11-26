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
  useReactFlow,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowLeft,
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
  Image as ImageIcon,
  Layers,
  Loader2,
  Maximize2,
  Minus,
  MousePointer2,
  Plus,
  Redo2,
  RefreshCw,
  RotateCcw,
  Sparkles,
  StickyNote,
  Trash2,
  Undo2,
  Upload,
  Wand2,
  X,
} from 'lucide-react';
import { InpaintMaskStage, type MaskTool } from '../components/canvas/InpaintMaskStage';
import { layoutCanvasGraph } from '../lib/canvasAutoLayout';
import { canvasGenerate, canvasImageBlobUrl, listCanvasArtifacts, type CanvasArtifact } from '../services/canvasService';
import { useChatStore } from '../stores/chatStore';
import {
  buildStudioPosterSvg,
  STUDIO_PALETTES,
  useCanvasStore,
  type ArtworkData,
  type NoteData,
  type QualityTier,
  type ResolutionTier,
  type StudioNode,
} from '../stores/canvasStore';
import { cn } from '../lib/utils';

type CanvasMode = 'focus' | 'infinite';
type InfiniteTool = 'select' | 'hand';

interface AspectOption {
  id: string;
  label: string;
  w: number;
  h: number;
  iconW: number;
  iconH: number;
}

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

/* ============================================================================
   Custom @xyflow/react Nodes (Stable Module-Level References)
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

const CreativeCanvasInner: React.FC = () => {
  const navigate = useNavigate();
  const { fitView, zoomIn, zoomOut, getZoom, screenToFlowPosition } = useReactFlow();

  // Zustand + zundo temporal store
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const onNodesChange = useCanvasStore((s) => s.onNodesChange);
  const onEdgesChange = useCanvasStore((s) => s.onEdgesChange);
  const onConnect = useCanvasStore((s) => s.onConnect);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const addNodesAndEdges = useCanvasStore((s) => s.addNodesAndEdges);
  const deleteNode = useCanvasStore((s) => s.deleteNode);
  const duplicateNode = useCanvasStore((s) => s.duplicateNode);
  const updateNoteText = useCanvasStore((s) => s.updateNoteText);
  const toggleLike = useCanvasStore((s) => s.toggleLike);

  const [canvasMode, setCanvasMode] = useState<CanvasMode>('infinite');
  const [tool, setTool] = useState<InfiniteTool>('select');
  const [activeId, setActiveId] = useState<string>('');
  const [zoomPct, setZoomPct] = useState<number>(100);
  const [focusZoom, setFocusZoom] = useState<number>(100);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [historyTick, setHistoryTick] = useState(0);

  // Right inspector state
  const [prompt, setPrompt] = useState(() => {
    const first = nodes.find((n) => n.data.kind === 'artwork');
    return first ? (first.data as ArtworkData).prompt : '';
  });
  const [model, setModel] = useState(MODEL_OPTIONS[0].id);
  const [aspectId, setAspectId] = useState<string>('3:4');
  const [resolution, setResolution] = useState<ResolutionTier>('2K');
  const [quality, setQuality] = useState<QualityTier>('balanced');
  const [batchCount, setBatchCount] = useState<number>(1);
  // 画布产物落到当前会话工作区；没有会话时生成一个客户端 ID（与 sendMessageStream 一致）
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const canvasSessionIdRef = useRef<string>(
    currentSessionId || `canvas-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
  );
  const [refImages, setRefImages] = useState<{ name: string; url: string; file?: File }[]>([]);
  const [showCameraMenu, setShowCameraMenu] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [loadingArtifacts, setLoadingArtifacts] = useState(true);

  // 启动时加载用户真实生成的图片产物作为画布节点（不再用假海报演示数据）
  useEffect(() => {
    let cancelled = false;
    const objectUrls: string[] = [];
    setLoadingArtifacts(true);
    listCanvasArtifacts()
      .then(async (items: CanvasArtifact[]) => {
        if (cancelled) return;
        const loaded: StudioNode[] = [];
        for (let i = 0; i < items.length; i++) {
          const it = items[i];
          try {
            const dataUrl = await canvasImageBlobUrl(it.url);
            objectUrls.push(dataUrl);
            const col = i % 4;
            const row = Math.floor(i / 4);
            loaded.push({
              id: `art-${it.session_id}-${it.filename}`,
              type: 'artwork',
              position: { x: 64 + col * 368, y: 64 + row * 420 },
              data: {
                kind: 'artwork',
                title: it.filename.replace(/\.[^.]+$/, '').slice(0, 40),
                prompt: `工作区产物：${it.filename}`,
                model: 'workspace',
                aspectId: 'auto',
                resolution: '2K',
                quality: 'balanced',
                width: 1024,
                height: 1024,
                durationSec: 0,
                createdAt: new Date(it.created_at * 1000).toLocaleString('zh-CN', { hour12: false }),
                liked: false,
                dataUrl,
                nodeW: 256,
                nodeH: 320,
              },
            });
          } catch {
            // 单个产物加载失败不影响其它
          }
        }
        if (cancelled) return;
        // 无论有无产物都重置节点：无产物时清空旧节点，展示空态
        setNodes(loaded);
        setActiveId(loaded[0]?.id ?? '');
      })
      .catch(() => { /* 未登录/接口失败：保持空画布 */ })
      .finally(() => { if (!cancelled) setLoadingArtifacts(false); });
    return () => {
      cancelled = true;
      objectUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [setNodes]);

  // Konva inpainting mask state (Focus Mode)
  const [inpaintMode, setInpaintMode] = useState(false);
  const [maskTool, setMaskTool] = useState<MaskTool>('brush');
  const [brushSize, setBrushSize] = useState(28);
  const [clearMaskSignal, setClearMaskSignal] = useState(0);
  const [undoMaskSignal, setUndoMaskSignal] = useState(0);
  const [focusImgSize, setFocusImgSize] = useState<{ w: number; h: number }>({ w: 480, h: 640 });
  const focusImgRef = useRef<HTMLImageElement | null>(null);
  const maskExporterRef = useRef<(() => string | null) | null>(null);

  // Instruction edit bar
  const [editBarOpen, setEditBarOpen] = useState(false);
  const [editInstruction, setEditInstruction] = useState('');
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const refFileInputRef = useRef<HTMLInputElement | null>(null);

  const canUndo = useMemo(() => {
    void historyTick;
    return useCanvasStore.temporal.getState().pastStates.length > 0;
  }, [nodes, edges, historyTick]);

  const canRedo = useMemo(() => {
    void historyTick;
    return useCanvasStore.temporal.getState().futureStates.length > 0;
  }, [nodes, edges, historyTick]);

  const handleUndo = useCallback(() => {
    const temporal = useCanvasStore.temporal.getState();
    if (temporal.pastStates.length === 0) return;
    temporal.undo();
    setHistoryTick((t) => t + 1);
    toast.info('已撤销上一步操作');
  }, []);

  const handleRedo = useCallback(() => {
    const temporal = useCanvasStore.temporal.getState();
    if (temporal.futureStates.length === 0) return;
    temporal.redo();
    setHistoryTick((t) => t + 1);
    toast.info('已重做操作');
  }, []);

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

  // Keyboard shortcuts: Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y / V / H
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inEditable =
        target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !inEditable) {
        e.preventDefault();
        if (e.shiftKey) handleRedo();
        else handleUndo();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y' && !inEditable) {
        e.preventDefault();
        handleRedo();
        return;
      }
      if (inEditable) return;

      if (e.key.toLowerCase() === 'v') setTool('select');
      else if (e.key.toLowerCase() === 'h') setTool('hand');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleUndo, handleRedo]);

  // Measure rendered Focus image dimensions for Konva Stage alignment
  useEffect(() => {
    if (canvasMode !== 'focus') return;
    const img = focusImgRef.current;
    if (!img) return;
    const syncSize = () => {
      if (img.clientWidth > 0 && img.clientHeight > 0) {
        setFocusImgSize({ w: img.clientWidth, h: img.clientHeight });
      }
    };
    syncSize();
    const ro = new ResizeObserver(syncSize);
    ro.observe(img);
    return () => ro.disconnect();
  }, [canvasMode, activeId, focusZoom]);

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

  const handleExportMask = () => {
    const dataUrl = maskExporterRef.current?.();
    if (!dataUrl) {
      toast.info('请先在画面上涂抹选区');
      return;
    }
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = `inpaint_mask_${activeId}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('已导出 Konva 局部精修 PNG 蒙版');
  };

  const handleDeleteById = useCallback(
    (id: string) => {
      deleteNode(id);
      toast.success('已删除画布元素');
    },
    [deleteNode],
  );

  const handleDuplicateById = useCallback(
    (id: string) => {
      const newId = duplicateNode(id);
      if (newId) {
        setActiveId(newId);
        toast.success('已复制节点');
      }
    },
    [duplicateNode],
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

      const parentNode = opts?.parentId ? nodes.find((n) => n.id === opts.parentId) : undefined;
      const isLandscape = selectedAspect.w > selectedAspect.h;
      const nodeW = isLandscape ? 304 : 256;
      const nodeH = isLandscape ? 214 : 360;

      // 真实生图：调后端画布 API（带鉴权），产物落会话工作区；
      // 未配置生图模型 / 网络失败时降级为本地预览 SVG，保证画布始终可用。
      type Generated = { dataUrl: string; real: boolean; duration: number };
      const generated: Generated[] = [];
      const reference = refImages.find((r) => r.file)?.file ?? null;
      for (let idx = 0; idx < batchCount; idx++) {
        try {
          const result = await canvasGenerate({
            prompt: finalPrompt,
            sessionId: canvasSessionIdRef.current,
            size: isLandscape ? 'landscape' : selectedAspect.w < selectedAspect.h ? 'portrait' : 'square',
            reference: reference && idx === 0 ? reference : null,
          });
          const blobUrl = await canvasImageBlobUrl(result.url);
          generated.push({ dataUrl: blobUrl, real: true, duration: Number(((performance.now() - startTs) / 1000).toFixed(1)) });
        } catch (err) {
          generated.push({
            dataUrl: buildStudioPosterSvg({
              title: finalPrompt.slice(0, 14) || '新建视觉作品',
              subtitle: finalPrompt.slice(0, 28),
              palette: STUDIO_PALETTES[(nodes.length + idx) % STUDIO_PALETTES.length],
              aspectW: selectedAspect.w,
              aspectH: selectedAspect.h,
              badge: 'PREVIEW',
            }),
            real: false,
            duration: 0,
          });
          if (idx === 0) {
            const msg = err instanceof Error ? err.message : String(err);
            toast.warning(`生图服务不可用，已显示预览占位：${msg}`, { duration: 5000 });
          }
        }
      }

      const createdNodes: StudioNode[] = [];
      const createdEdges: Edge[] = [];

      for (let idx = 0; idx < batchCount; idx++) {
        const palette = STUDIO_PALETTES[(nodes.length + idx) % STUDIO_PALETTES.length];
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
            durationSec: generated[idx]?.duration || Number((((performance.now() - startTs) / 1000) + 1.0 + idx * 0.3).toFixed(1)),
            createdAt: '刚刚',
            liked: false,
            dataUrl: generated[idx]?.dataUrl || buildStudioPosterSvg({
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

      addNodesAndEdges(createdNodes, createdEdges);
      setActiveId(createdNodes[0].id);
      setEditBarOpen(false);
      setEditInstruction('');
      setInpaintMode(false);
      setIsGenerating(false);
      toast.success(`已生成 ${createdNodes.length} 张作品${parentNode ? '并建立衍生连线' : ''}`);
    },
    [prompt, nodes, selectedAspect, batchCount, model, aspectId, resolution, quality, outputPixels, addNodesAndEdges, refImages],
  );

  /** 非 AI 图片处理：对当前作品做裁剪/压缩/缩放/水印等，结果作为新节点。 */
  const handleProcessImage = useCallback(
    async (
      operation: 'crop' | 'resize' | 'compress' | 'rotate' | 'watermark' | 'thumbnail',
      opts?: { resize?: { width: number; height: number }; degrees?: number },
    ) => {
      if (!activeArtworkData) {
        toast.error('请先选中一张图片');
        return;
      }
      // dataUrl 可能是 blob: / data: —— 都 fetch 成 blob 再构造上传 File
      let file: File;
      try {
        const resp = await fetch(activeArtworkData.dataUrl);
        const blob = await resp.blob();
        file = new File([blob], `artwork-${Date.now()}.png`, { type: blob.type || 'image/png' });
      } catch {
        toast.error('无法读取当前图片');
        return;
      }
      setIsGenerating(true);
      try {
        const { canvasProcess, canvasImageBlobUrl } = await import('../services/canvasService');
        const result = await canvasProcess({
          image: file,
          sessionId: canvasSessionIdRef.current,
          operation,
          outputFormat: operation === 'compress' ? 'WEBP' : 'PNG',
          quality: 85,
          resize: opts?.resize,
          degrees: opts?.degrees,
          watermark: operation === 'watermark' ? 'AgenticOS' : undefined,
        });
        const dataUrl = await canvasImageBlobUrl(result.url);
        const newId = `processed-${Date.now()}`;
        addNodesAndEdges(
          [{
            id: newId,
            type: 'artwork',
            selected: true,
            position: { x: (activeNode?.position.x ?? 64) + 320, y: activeNode?.position.y ?? 64 },
            data: {
              kind: 'artwork',
              title: `${activeArtworkData.title} · ${operation}`,
              prompt: activeArtworkData.prompt,
              model: activeArtworkData.model,
              aspectId: activeArtworkData.aspectId,
              resolution: activeArtworkData.resolution,
              quality: activeArtworkData.quality,
              width: result.width,
              height: result.height,
              durationSec: 0,
              createdAt: '刚刚处理',
              liked: false,
              dataUrl,
              nodeW: 256,
              nodeH: 320,
            },
          }],
          [],
        );
        setActiveId(newId);
        toast.success(`图片处理完成：${result.width}×${result.height}`);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '图片处理失败');
      } finally {
        setIsGenerating(false);
      }
    },
    [activeArtworkData, activeNode, addNodesAndEdges],
  );

  // Inject interactive callbacks into nodes
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
            onChangeText: updateNoteText,
            onDuplicate: handleDuplicateById,
            onDelete: handleDeleteById,
          },
        };
      }),
    [nodes, handleGenerate, syncInspectorFromNode, handleDownloadById, handleDuplicateById, handleDeleteById, updateNoteText],
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
    addNodesAndEdges([noteNode]);
    setActiveId(newId);
    setCanvasMode('infinite');
    toast.success('已在画布添加便签卡片');
  };

  // Auto-layout using @dagrejs/dagre
  const handleDagreAutoLayout = (direction: 'LR' | 'TB' = 'LR') => {
    const laidOut = layoutCanvasGraph(nodes, edges, direction);
    setNodes(laidOut);
    setTimeout(() => fitView({ padding: 0.16, duration: 360 }), 40);
    toast.success(direction === 'LR' ? '已按 Dagre 横向衍生树自动排版' : '已按 Dagre 纵向树自动排版');
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
    addNodesAndEdges(added);
    setActiveId(added[0].id);
    setCanvasMode('infinite');
    toast.success(`已将 ${added.length} 张本地图片置入无限画布`);
  };

  const handleRefFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const added = Array.from(files)
      .slice(0, 4)
      .map((f) => ({ name: f.name, url: URL.createObjectURL(f), file: f }));
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

  return (
    <div className="relative flex h-full w-full overflow-hidden text-[var(--foreground)] font-sans select-none">
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
              <>
                <button
                  type="button"
                  onClick={handleUndo}
                  disabled={!canUndo}
                  className="flex h-8 w-8 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] disabled:opacity-35"
                  title="撤销 (Ctrl+Z)"
                >
                  <Undo2 size={14} />
                </button>
                <button
                  type="button"
                  onClick={handleRedo}
                  disabled={!canRedo}
                  className="flex h-8 w-8 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] disabled:opacity-35"
                  title="重做 (Ctrl+Shift+Z)"
                >
                  <Redo2 size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => handleDagreAutoLayout('LR')}
                  className="hidden h-8 items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/80 px-2.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] sm:inline-flex"
                  title="Dagre 有向树自动排版"
                >
                  <GitBranch size={13} />
                  自动排版
                </button>
              </>
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
          {/* 空态引导：没有真实作品时告诉用户如何开始（不再展示假海报） */}
          {!loadingArtifacts && nodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 px-8 text-center">
              <div className="aos-icon-badge aos-tone-amber flex h-16 w-16 items-center justify-center !rounded-2xl">
                <Sparkles size={28} />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-[var(--foreground)]">画布还是空的</h3>
                <p className="mt-1 max-w-md text-xs leading-relaxed text-[var(--muted-foreground)]">
                  在右侧输入画面描述，点击「生成画面」即可创作第一张作品；
                  也可以把本地图片拖进画布，或用聊天里的生图工具生成后自动出现在这里。
                </p>
              </div>
              <div className="pointer-events-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => document.querySelector<HTMLTextAreaElement>('[data-canvas-prompt]')?.focus()}
                  className="aos-cta-pill"
                >
                  开始创作
                </button>
                <button
                  type="button"
                  onClick={() => document.querySelector<HTMLInputElement>('[data-canvas-upload]')?.click()}
                  className="aos-pill-btn"
                >
                  <Upload size={14} /> 导入图片
                </button>
              </div>
            </div>
          )}
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
                  @xyflow/react · Dagre 自动排版 · Zundo 撤销重做 · 拖入图片直达画布
                </div>
              </Panel>
            </ReactFlow>
          ) : (
            /* Focus View with Konva Inpainting Mask Stage */
            <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-6 pb-24 pt-6">
              <AnimatePresence>
                {inpaintMode && (
                  <motion.div
                    initial={{ opacity: 0, y: -12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    className="aos-glass-rail absolute top-4 z-30 flex flex-wrap items-center gap-2.5 rounded-2xl px-3.5 py-2 text-xs"
                  >
                    <div className="flex items-center gap-1 rounded-xl bg-[var(--surface-2)]/80 p-0.5">
                      <button
                        type="button"
                        onClick={() => setMaskTool('brush')}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-lg px-2 py-1 font-semibold transition-all',
                          maskTool === 'brush'
                            ? 'bg-[var(--primary)] text-[var(--primary-foreground)]'
                            : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                        )}
                      >
                        <Brush size={12} />
                        画笔
                      </button>
                      <button
                        type="button"
                        onClick={() => setMaskTool('eraser')}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-lg px-2 py-1 font-semibold transition-all',
                          maskTool === 'eraser'
                            ? 'bg-[var(--primary)] text-[var(--primary-foreground)]'
                            : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                        )}
                      >
                        <Eraser size={12} />
                        橡皮
                      </button>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[var(--muted-foreground)]">大小</span>
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
                      onClick={() => setUndoMaskSignal((n) => n + 1)}
                      className="rounded-lg px-2 py-1 font-medium text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                    >
                      撤销一笔
                    </button>
                    <button
                      type="button"
                      onClick={() => setClearMaskSignal((n) => n + 1)}
                      className="rounded-lg px-2 py-1 font-medium text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                    >
                      清空
                    </button>
                    <button
                      type="button"
                      onClick={handleExportMask}
                      className="rounded-lg bg-[var(--primary)]/12 px-2 py-1 font-semibold text-[var(--primary)] hover:bg-[var(--primary)]/20"
                    >
                      导出蒙版
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
                    ref={focusImgRef}
                    src={activeArtworkData.dataUrl}
                    alt={activeArtworkData.title}
                    draggable={false}
                    onLoad={(e) => {
                      const img = e.currentTarget;
                      setFocusImgSize({ w: img.clientWidth, h: img.clientHeight });
                    }}
                    className="block max-h-[66vh] w-auto object-contain"
                  />

                  {inpaintMode && (
                    <InpaintMaskStage
                      width={focusImgSize.w}
                      height={focusImgSize.h}
                      tool={maskTool}
                      brushSize={brushSize}
                      clearSignal={clearMaskSignal}
                      undoSignal={undoMaskSignal}
                      onExportReady={(fn) => {
                        maskExporterRef.current = fn;
                      }}
                    />
                  )}

                  <AnimatePresence>
                    {isGenerating && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-slate-950/55 text-white backdrop-blur-md"
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
                    onClick={() => toggleLike(activeNode.id)}
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
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/55 p-3">
            <textarea
              data-canvas-prompt
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
              data-canvas-upload
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

            {/* 非 AI 图片工具：裁剪 / 压缩 / 缩放 / 旋转 / 水印 / 抠图蒙版 */}
            <div className="border-t border-[var(--border-subtle)] pt-3">
              <span className="mb-2 block text-xs font-semibold text-[var(--foreground)]">图片工具</span>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  { key: 'compress' as const, label: '压缩', icon: Layers },
                  { key: 'resize' as const, label: '缩放', icon: Maximize2 },
                  { key: 'rotate' as const, label: '旋转90°', icon: RotateCcw },
                  { key: 'watermark' as const, label: '水印', icon: Sparkles },
                  { key: 'thumbnail' as const, label: '缩略图', icon: Focus },
                  { key: 'crop' as const, label: '抠图蒙版', icon: Brush },
                ].map((toolItem) => (
                  <button
                    key={toolItem.key}
                    type="button"
                    disabled={isGenerating}
                    title={toolItem.key === 'crop' ? '在专注模式用画笔涂抹蒙版后导出' : undefined}
                    onClick={() => {
                      if (toolItem.key === 'crop') {
                        setInpaintMode(true);
                        setCanvasMode('focus');
                        toast.info('已进入蒙版模式：涂抹要保留的区域后点「导出蒙版」');
                        return;
                      }
                      handleProcessImage(toolItem.key, {
                        resize: toolItem.key === 'resize' || toolItem.key === 'thumbnail'
                          ? { width: 1024, height: 1024 } : undefined,
                        degrees: toolItem.key === 'rotate' ? 90 : undefined,
                      });
                    }}
                    className="flex flex-col items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)]/60 py-2 text-[10.5px] font-medium text-[var(--muted-foreground)] transition-all hover:border-[var(--border-strong)] hover:text-[var(--foreground)] active:scale-95 disabled:opacity-40"
                  >
                    <toolItem.icon size={14} />
                    {toolItem.label}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-[10px] leading-snug text-[var(--muted-foreground)]">
                本地处理，不调用 AI；「抠图蒙版」用画笔标注后导出 PNG
              </p>
            </div>
          </section>

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
