/**
 * 知识库管理：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Select/Dialog/AlertDialog/Tabs。
 * 功能：知识库列表（创建/删除）、文档上传管理、Wiki 浏览、搜索测试、审核队列、知识图谱。
 * 后端 API 不变（services/knowledgeService.ts）。
 * 页面骨架与状态编排；弹窗 / Tab 面板拆分至同目录子文件。
 */
import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertCircle,
  BookOpen,
  ChevronLeft,
  Database,
  Eye,
  FileText,
  Loader2,
  Plus,
  Search,
  Trash2,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, StatusPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/shadcn/tabs';
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
  KnowledgeBase,
  WikiPage,
  deleteDocument,
  deleteKnowledgeBase,
  getDocuments,
  getKnowledgeBases,
  getWikiPages,
  searchKnowledgeBase,
  uploadDocument,
  type SearchResult,
} from '@/services/knowledgeService';
import { CreateKBDialog } from './KnowledgeCreateDialog';
import { ReviewQueue } from './KnowledgeReviewQueue';
import { KnowledgeGraph } from './KnowledgeGraph';
import { KnowledgeDocumentsTab } from './KnowledgeDocumentsTab';
import { KnowledgeWikiTab } from './KnowledgeWikiTab';
import { KnowledgeSearchTab } from './KnowledgeSearchTab';
import { scopeLabel, type DetailTab } from './knowledgeHelpers';

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
                  <span className="truncate text-sm font-semibold text-[var(--foreground)]">{kb.name}</span>
                  <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)]">
                    {scopeLabel(kb.scope)}
                  </span>
                </div>
                <p className="mt-0.5 max-w-[380px] truncate text-xs font-medium text-[var(--muted-foreground)]">
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
          <span className="text-sm font-semibold text-[var(--foreground)]">{Number(getValue())}</span>
        ),
      },
      {
        accessorKey: 'page_count',
        header: 'Wiki 页面',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-[var(--foreground)]">{Number(getValue())}</span>
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
        <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
          <DataTable
            columns={kbColumns}
            data={knowledgeBases}
            isLoading={kbsQuery.isLoading}
            emptyState={
              <div className="flex flex-col items-center justify-center py-8">
                <Database className="mb-3 h-10 w-10 text-zinc-300" />
                <p className="text-sm font-semibold text-zinc-600">暂无知识库</p>
                <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">点击「新建知识库」开始</p>
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
            <KnowledgeDocumentsTab
              documents={documents}
              isLoading={docsQuery.isLoading}
              onUpload={(file) => uploadMutation.mutate(file)}
              onDeleteDoc={setDeletingDoc}
            />
          )}

          {/* Wiki Pages Tab */}
          {detailTab === 'wiki' && (
            <KnowledgeWikiTab
              pages={wikiPages}
              isLoading={wikiQuery.isLoading}
              selectedPage={selectedPage}
              onSelectPage={setSelectedPage}
            />
          )}

          {/* Search Tab */}
          {detailTab === 'search' && (
            <KnowledgeSearchTab
              kbId={selectedKB.id}
              query={searchQuery}
              results={searchResults}
              isPending={searchMutation.isPending}
              onQueryChange={setSearchQuery}
              onSearch={(query) => searchMutation.mutate(query)}
            />
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
