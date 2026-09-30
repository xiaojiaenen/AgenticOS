/**
 * 知识库管理：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Select/Dialog/AlertDialog/Tabs。
 * 功能：知识库列表（创建/删除）、文档上传管理、Wiki 浏览、搜索测试、审核队列、知识图谱。
 * 后端 API 不变（services/knowledgeService.ts）。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  AlertCircle,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  FileText,
  Loader2,
  Plus,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, StatusPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Skeleton } from '@/components/shadcn/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/shadcn/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/shadcn/alert-dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { cn } from '@/lib/utils';
import {
  KnowledgeBase,
  ReviewItem,
  SearchResult,
  WikiPage,
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  getDocuments,
  getKnowledgeBases,
  getKnowledgeGraph,
  getReviewItems,
  getWikiPages,
  searchKnowledgeBase,
  updateReview,
  uploadDocument,
  type KnowledgeGraphData,
} from '@/services/knowledgeService';

// ---------------------------------------------------------------------------
// zod schema（对齐后端 KnowledgeBasePayload）
// ---------------------------------------------------------------------------

const kbFormSchema = z.object({
  name: z.string().min(1, '请填写知识库名称'),
  description: z.string(),
  purpose: z.string(),
  scope: z.enum(['org', 'team', 'personal']),
  visibility: z.enum(['public', 'restricted', 'private']),
});

type KBFormValues = z.infer<typeof kbFormSchema>;

function scopeLabel(scope: string): string {
  const map: Record<string, string> = { org: '组织级', team: '团队级', personal: '个人级' };
  return map[scope] || scope;
}

function docStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待编译',
    compiling: '编译中',
    compiled: '已编译',
    failed: '失败',
  };
  return map[status] || status;
}

function docStatusTone(status: string): 'active' | 'inactive' | 'warning' | 'info' {
  switch (status) {
    case 'compiled':
      return 'active';
    case 'failed':
      return 'inactive';
    case 'pending':
      return 'warning';
    default:
      return 'info';
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// 新建知识库弹窗
// ---------------------------------------------------------------------------

function CreateKBDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const form = useForm<KBFormValues>({
    resolver: zodResolver(kbFormSchema),
    defaultValues: { name: '', description: '', purpose: '', scope: 'org', visibility: 'public' },
  });

  const createMutation = useMutation({
    mutationFn: (values: KBFormValues) =>
      createKnowledgeBase({
        name: values.name.trim(),
        description: values.description.trim() || undefined,
        purpose: values.purpose.trim() || undefined,
        scope: values.scope,
        visibility: values.visibility,
      }),
    onSuccess: () => {
      toast.success('知识库创建成功');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kbs'] });
      form.reset();
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || '创建失败'),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新建知识库</DialogTitle>
          <DialogDescription>创建组织级 / 团队级 / 个人级知识库</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => void createMutation.mutateAsync(values))}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="kb-name">名称 *</Label>
            <Input id="kb-name" placeholder="例如：公司技术文档" {...form.register('name')} />
            {form.formState.errors.name ? (
              <p className="text-xs font-medium text-rose-600">{form.formState.errors.name.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="kb-description">描述</Label>
            <Input id="kb-description" placeholder="简要说明知识库用途" {...form.register('description')} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="kb-purpose">
              目标声明
              <span className="ml-1 text-xs font-normal text-zinc-400">
                （告诉 LLM 这个知识库关注什么）
              </span>
            </Label>
            <textarea
              id="kb-purpose"
              rows={3}
              placeholder="例如：本知识库包含公司后端服务的部署运维规范，关注 Docker 部署、监控告警、故障排查"
              {...form.register('purpose')}
              className="w-full resize-none rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <Label>归属</Label>
              <Select
                value={form.watch('scope')}
                onValueChange={(v) => form.setValue('scope', v as KBFormValues['scope'])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="org">组织级</SelectItem>
                  <SelectItem value="team">团队级</SelectItem>
                  <SelectItem value="personal">个人级</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 space-y-1.5">
              <Label>可见性</Label>
              <Select
                value={form.watch('visibility')}
                onValueChange={(v) => form.setValue('visibility', v as KBFormValues['visibility'])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="public">公开</SelectItem>
                  <SelectItem value="restricted">受限</SelectItem>
                  <SelectItem value="private">私有</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={createMutation.isPending}>
              取消
            </Button>
            <Button type="submit" disabled={createMutation.isPending} className="gap-2">
              {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {createMutation.isPending ? '创建中…' : '创建'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 审核队列
// ---------------------------------------------------------------------------

function ReviewQueue({ kbId }: { kbId: number }) {
  const queryClient = useQueryClient();
  const reviewsQuery = useQuery({
    queryKey: ['admin', 'kb-reviews', kbId],
    queryFn: () => getReviewItems(kbId),
  });

  const resolveMutation = useMutation({
    mutationFn: ({ reviewId, status }: { reviewId: number; status: 'approved' | 'rejected' }) =>
      updateReview(kbId, reviewId, status, status === 'approved' ? 'Approved' : 'Rejected'),
    onSuccess: () => {
      toast.success('审核处理完成');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kb-reviews', kbId] });
    },
    onError: (err: Error) => toast.error(err.message || '处理审核失败'),
  });

  const typeLabels: Record<string, string> = {
    conflict_resolution: '矛盾解决',
    page_creation: '新页面确认',
    page_merge: '页面合并',
    page_delete: '页面删除',
    authority_upgrade: '权威性提升',
  };

  if (reviewsQuery.isPending) {
    return (
      <div className="flex items-center justify-center py-16 text-zinc-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (reviewsQuery.isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <ErrorBanner message={(reviewsQuery.error as Error).message || '审核列表加载失败'} />
        <Button variant="outline" size="sm" onClick={() => void reviewsQuery.refetch()}>
          重试
        </Button>
      </div>
    );
  }

  const reviews = reviewsQuery.data;

  if (reviews.length === 0) {
    return (
      <div className="py-12 text-center text-sm font-medium text-zinc-500">
        <AlertCircle className="mx-auto mb-3 h-10 w-10 opacity-40" />
        暂无待审核项
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviews.map((review: ReviewItem) => (
        <div key={review.id} className="rounded-lg border border-zinc-200/80 bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
              {typeLabels[review.review_type] || review.review_type}
            </span>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-xs font-medium',
                review.status === 'pending'
                  ? 'bg-amber-50 text-amber-700'
                  : review.status === 'approved'
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-zinc-100 text-zinc-600',
              )}
            >
              {review.status === 'pending' ? '待审核' : review.status === 'approved' ? '已通过' : review.status}
            </span>
          </div>
          <h4 className="text-sm font-semibold text-zinc-900">{review.title}</h4>
          {review.description && <p className="mt-1 text-xs font-medium text-zinc-500">{review.description}</p>}
          {review.status === 'pending' && (
            <div className="mt-3 flex gap-2">
              <Button
                size="xs"
                className="gap-1"
                onClick={() =>
                  resolveMutation.mutate({ reviewId: review.id, status: 'approved' })
                }
                disabled={resolveMutation.isPending}
              >
                通过
              </Button>
              <Button
                size="xs"
                variant="destructive"
                className="gap-1"
                onClick={() =>
                  resolveMutation.mutate({ reviewId: review.id, status: 'rejected' })
                }
                disabled={resolveMutation.isPending}
              >
                拒绝
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 知识图谱
// ---------------------------------------------------------------------------

function KnowledgeGraph({ kbId }: { kbId: number }) {
  const graphQuery = useQuery({
    queryKey: ['admin', 'kb-graph', kbId],
    queryFn: () => getKnowledgeGraph(kbId),
    retry: 0,
  });

  if (graphQuery.isPending) {
    return (
      <div className="flex items-center justify-center py-16 text-zinc-500">
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
      <div className="py-12 text-center text-sm font-medium text-zinc-500">
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
    <div className="rounded-lg border border-zinc-200/80 bg-white p-4 shadow-sm">
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
      <div className="mt-4 flex gap-4 text-xs font-medium text-zinc-500">
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-indigo-600" /> L3 锁定</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-violet-500" /> L2 已审核</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-zinc-400" /> L1 自动</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

type DetailTab = 'documents' | 'wiki' | 'search' | 'reviews' | 'graph';

export function KnowledgeManagement() {
  const queryClient = useQueryClient();

  const [view, setView] = React.useState<'list' | 'detail'>('list');
  const [selectedKB, setSelectedKB] = React.useState<KnowledgeBase | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [deletingKB, setDeletingKB] = React.useState<KnowledgeBase | null>(null);
  const [deletingDoc, setDeletingDoc] = React.useState<{ docId: number; title: string } | null>(null);
  const [detailTab, setDetailTab] = React.useState<DetailTab>('documents');
  const [selectedPage, setSelectedPage] = React.useState<WikiPage | null>(null);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [searchResults, setSearchResults] = React.useState<SearchResult[]>([]);

  const kbsQuery = useQuery({
    queryKey: ['admin', 'kbs'],
    queryFn: getKnowledgeBases,
  });
  const knowledgeBases = kbsQuery.data ?? [];

  const docsQuery = useQuery({
    queryKey: ['admin', 'kb-docs', selectedKB?.id],
    queryFn: () => getDocuments(selectedKB!.id),
    enabled: view === 'detail' && selectedKB !== null,
  });
  const wikiQuery = useQuery({
    queryKey: ['admin', 'kb-wiki', selectedKB?.id],
    queryFn: () => getWikiPages(selectedKB!.id),
    enabled: view === 'detail' && selectedKB !== null,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDocument(selectedKB!.id, file),
    onSuccess: () => {
      toast.success('文档上传成功');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kb-docs'] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kbs'] });
    },
    onError: (err: Error) => toast.error(err.message || '上传失败'),
  });

  const deleteDocMutation = useMutation({
    mutationFn: ({ kbId, docId }: { kbId: number; docId: number }) => deleteDocument(kbId, docId),
    onSuccess: () => {
      toast.success('文档已删除');
      setDeletingDoc(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kb-docs'] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kbs'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const deleteKBMutation = useMutation({
    mutationFn: (kbId: number) => deleteKnowledgeBase(kbId),
    onSuccess: () => {
      toast.success('知识库已删除');
      setDeletingKB(null);
      if (selectedKB && deletingKB && selectedKB.id === deletingKB.id) {
        setView('list');
        setSelectedKB(null);
      }
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kbs'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const searchMutation = useMutation({
    mutationFn: (query: string) => searchKnowledgeBase(selectedKB!.id, query),
    onSuccess: (results) => setSearchResults(results),
    onError: (err: Error) => toast.error(err.message || '搜索失败'),
  });

  const openDetail = (kb: KnowledgeBase) => {
    setSelectedKB(kb);
    setView('detail');
    setDetailTab('documents');
    setSelectedPage(null);
    setSearchQuery('');
    setSearchResults([]);
  };

  const documents = docsQuery.data ?? [];
  const wikiPages = wikiQuery.data ?? [];

  const kbColumns = React.useMemo<ColumnDef<KnowledgeBase, unknown>[]>(
    () => [
      {
        id: 'name',
        header: '知识库',
        cell: ({ row }) => {
          const kb = row.original;
          return (
            <button
              type="button"
              onClick={() => openDetail(kb)}
              className="flex min-w-0 items-center gap-3 text-left"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                <BookOpen className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold text-zinc-900">{kb.name}</span>
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500">
                    {scopeLabel(kb.scope)}
                  </span>
                </div>
                <p className="mt-0.5 max-w-[380px] truncate text-xs font-medium text-zinc-500">
                  {kb.description || kb.purpose || '暂无描述'}
                </p>
              </div>
            </button>
          );
        },
      },
      {
        accessorKey: 'document_count',
        header: '文档',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-zinc-900">{Number(getValue())}</span>
        ),
      },
      {
        accessorKey: 'page_count',
        header: 'Wiki 页面',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-zinc-900">{Number(getValue())}</span>
        ),
      },
      {
        accessorKey: 'visibility',
        header: '可见性',
        cell: ({ getValue }) => {
          const map: Record<string, string> = { public: '公开', restricted: '受限', private: '私有' };
          return (
            <StatusPill tone={getValue() === 'public' ? 'active' : 'info'}>
              {map[String(getValue())] || String(getValue())}
            </StatusPill>
          );
        },
      },
      {
        accessorKey: 'is_active',
        header: '状态',
        cell: ({ getValue }) => (
          <StatusPill tone={getValue() ? 'active' : 'inactive'}>
            {getValue() ? '启用' : '停用'}
          </StatusPill>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1.5">
            <Button variant="outline" size="sm" onClick={() => openDetail(row.original)}>
              <Eye size={14} />
              详情
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-rose-500 hover:bg-rose-50 hover:text-rose-600"
              onClick={() => setDeletingKB(row.original)}
              aria-label={`删除知识库 ${row.original.name}`}
            >
              <Trash2 size={15} />
            </Button>
          </div>
        ),
      },
    ],
    [], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="知识库"
        title={view === 'list' ? '知识库管理' : selectedKB?.name || ''}
        description={
          view === 'list'
            ? '管理组织知识库、文档和 Wiki 页面'
            : selectedKB
              ? `${scopeLabel(selectedKB.scope)} · ${selectedKB.page_count} 个 Wiki 页面`
              : undefined
        }
        actions={
          view === 'list' ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void kbsQuery.refetch()}
                disabled={kbsQuery.isFetching}
                className="gap-1.5"
              >
                {kbsQuery.isFetching ? <Loader2 size={14} className="animate-spin" /> : null}
                刷新
              </Button>
              <Button size="sm" className="gap-1.5" onClick={() => setCreateOpen(true)}>
                <Plus size={14} />
                新建知识库
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setView('list');
                setSelectedKB(null);
              }}
            >
              <ChevronLeft size={14} />
              返回列表
            </Button>
          )
        }
      />

      {kbsQuery.isError && view === 'list' ? (
        <ErrorBanner message={(kbsQuery.error as Error).message || '加载失败'} />
      ) : null}

      {/* List View */}
      {view === 'list' && (
        <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
          <DataTable
            columns={kbColumns}
            data={knowledgeBases}
            isLoading={kbsQuery.isLoading}
            emptyState={
              <div className="flex flex-col items-center justify-center py-8">
                <Database className="mb-3 h-10 w-10 text-zinc-300" />
                <p className="text-sm font-semibold text-zinc-600">暂无知识库</p>
                <p className="mt-1 text-xs font-medium text-zinc-400">点击「新建知识库」开始</p>
              </div>
            }
          />
        </section>
      )}

      {/* Detail View */}
      {view === 'detail' && selectedKB && (
        <div className="space-y-4">
          <Tabs value={detailTab} onValueChange={(v) => { setDetailTab(v as DetailTab); setSelectedPage(null); }}>
            <TabsList className="flex-wrap">
              <TabsTrigger value="documents" className="gap-1.5"><FileText className="h-3.5 w-3.5" />文档</TabsTrigger>
              <TabsTrigger value="wiki" className="gap-1.5"><BookOpen className="h-3.5 w-3.5" />Wiki 页面</TabsTrigger>
              <TabsTrigger value="search" className="gap-1.5"><Search className="h-3.5 w-3.5" />搜索测试</TabsTrigger>
              <TabsTrigger value="reviews" className="gap-1.5"><AlertCircle className="h-3.5 w-3.5" />审核队列</TabsTrigger>
              <TabsTrigger value="graph" className="gap-1.5"><Database className="h-3.5 w-3.5" />知识图谱</TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Documents Tab */}
          {detailTab === 'documents' && (
            <div className="space-y-3">
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-300 bg-white py-6 text-sm font-medium text-zinc-500 transition hover:border-indigo-300 hover:text-indigo-600">
                <Upload className="h-4 w-4" />
                点击上传文档（PDF / Word / Markdown）
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.md,.html,.txt"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadMutation.mutate(file);
                    e.target.value = '';
                  }}
                />
              </label>

              {docsQuery.isLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </div>
              ) : documents.length === 0 ? (
                <p className="py-8 text-center text-sm font-medium text-zinc-500">暂无文档</p>
              ) : (
                documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between rounded-lg border border-zinc-200/80 bg-white px-4 py-3 shadow-sm"
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="h-4 w-4 text-zinc-400" />
                      <div>
                        <p className="text-sm font-medium text-zinc-900">{doc.title}</p>
                        <p className="text-xs font-medium text-zinc-500">
                          {doc.file_type.toUpperCase()} · {formatSize(doc.file_size)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusPill tone={docStatusTone(doc.status)}>{docStatusLabel(doc.status)}</StatusPill>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        className="text-rose-500 hover:bg-rose-50 hover:text-rose-600"
                        onClick={() => setDeletingDoc({ docId: doc.id, title: doc.title })}
                        aria-label={`删除文档 ${doc.title}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Wiki Pages Tab */}
          {detailTab === 'wiki' && (
            <div className="space-y-3">
              {wikiQuery.isLoading ? (
                <div className="flex items-center justify-center py-16 text-zinc-500">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  加载中…
                </div>
              ) : selectedPage ? (
                <div className="space-y-4">
                  <Button variant="ghost" size="sm" className="gap-1" onClick={() => setSelectedPage(null)}>
                    <ChevronRight className="h-4 w-4 rotate-180" />
                    返回列表
                  </Button>
                  <div className="rounded-lg border border-zinc-200/80 bg-white p-6 shadow-sm">
                    <div className="mb-4 flex flex-wrap items-center gap-3">
                      <h3 className="text-lg font-semibold text-zinc-900">{selectedPage.title}</h3>
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500">
                        {selectedPage.page_type}
                      </span>
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
                        {selectedPage.authority_level}
                      </span>
                    </div>
                    <pre className="whitespace-pre-wrap rounded-lg border border-zinc-100 bg-zinc-50 p-4 font-mono text-sm leading-relaxed text-zinc-700">
                      {selectedPage.content}
                    </pre>
                    {selectedPage.sources.length > 0 && (
                      <div className="mt-4 text-xs font-medium text-zinc-500">
                        来源: {selectedPage.sources.join(', ')}
                      </div>
                    )}
                  </div>
                </div>
              ) : wikiPages.length === 0 ? (
                <p className="py-8 text-center text-sm font-medium text-zinc-500">
                  暂无 Wiki 页面。上传文档后系统将自动编译生成。
                </p>
              ) : (
                wikiPages.map((page) => (
                  <button
                    key={page.id}
                    onClick={() => setSelectedPage(page)}
                    className="flex w-full items-center justify-between rounded-lg border border-zinc-200/80 bg-white px-4 py-3 text-left shadow-sm transition hover:border-zinc-300 hover:bg-zinc-50"
                  >
                    <div className="flex items-center gap-3">
                      <BookOpen className="h-4 w-4 text-zinc-400" />
                      <div>
                        <p className="text-sm font-medium text-zinc-900">{page.title}</p>
                        <p className="text-xs font-medium text-zinc-500">{page.page_type}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
                        {page.authority_level}
                      </span>
                      <Eye className="h-4 w-4 text-zinc-400" />
                    </div>
                  </button>
                ))
              )}
            </div>
          )}

          {/* Search Tab */}
          {detailTab === 'search' && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && searchQuery.trim()) {
                      searchMutation.mutate(searchQuery.trim());
                    }
                  }}
                  placeholder="输入查询内容测试检索效果…"
                />
                <Button
                  onClick={() => searchQuery.trim() && searchMutation.mutate(searchQuery.trim())}
                  disabled={!searchQuery.trim() || searchMutation.isPending}
                >
                  {searchMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                </Button>
              </div>

              {searchResults.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-zinc-500">{searchResults.length} 条结果</p>
                  {searchResults.map((r) => (
                    <div key={r.page_id} className="rounded-lg border border-zinc-200/80 bg-white p-4 shadow-sm">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-zinc-900">{r.title}</span>
                        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500">
                          {r.page_type}
                        </span>
                        <span className="ml-auto text-xs font-medium text-zinc-500">
                          得分: {r.score.toFixed(3)} · {r.authority_level}
                        </span>
                      </div>
                      <p className="line-clamp-3 text-sm font-medium text-zinc-600">{r.content}</p>
                    </div>
                  ))}
                </div>
              )}

              {searchResults.length === 0 && searchQuery && !searchMutation.isPending && (
                <p className="py-8 text-center text-sm font-medium text-zinc-500">无匹配结果</p>
              )}
            </div>
          )}

          {/* Reviews Tab */}
          {detailTab === 'reviews' && <ReviewQueue kbId={selectedKB.id} />}

          {/* Graph Tab */}
          {detailTab === 'graph' && <KnowledgeGraph kbId={selectedKB.id} />}
        </div>
      )}

      <CreateKBDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      <AlertDialog
        open={deletingKB !== null}
        onOpenChange={(next) => !next && setDeletingKB(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除知识库</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除知识库「{deletingKB?.name}」？所有文档和 Wiki 页面将一并删除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteKBMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteKBMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingKB) deleteKBMutation.mutate(deletingKB.id);
              }}
            >
              {deleteKBMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={deletingDoc !== null}
        onOpenChange={(next) => !next && setDeletingDoc(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除文档</AlertDialogTitle>
            <AlertDialogDescription>确定删除文档「{deletingDoc?.title}」？</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteDocMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteDocMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingDoc && selectedKB) {
                  deleteDocMutation.mutate({ kbId: selectedKB.id, docId: deletingDoc.docId });
                }
              }}
            >
              {deleteDocMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
