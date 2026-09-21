/**
 * 知识库管理组件
 *
 * 功能：
 * - 知识库列表（创建/编辑/删除）
 * - 文档上传与管理
 * - Wiki 页面浏览
 * - 搜索测试
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  BookOpen,
  Plus,
  Trash2,
  Upload,
  X,
  Loader2,
  AlertCircle,
  FileText,
  Search,
  Eye,
  ChevronRight,
  Database,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { Button } from '../ui/Button';
import { useAdminModalBackdrop } from './useAdminModalBackdrop';
import {
  getKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getDocuments,
  uploadDocument,
  deleteDocument,
  getWikiPages,
  searchKnowledgeBase,
  type KnowledgeBase,
  type KnowledgeBasePayload,
  type KBDocument,
  type WikiPage,
  type SearchResult,
} from '../../services/knowledgeService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type View = 'list' | 'detail';
type DetailTab = 'documents' | 'wiki' | 'search';

interface KBDraft {
  name: string;
  description: string;
  purpose: string;
  scope: 'org' | 'team' | 'personal';
  visibility: 'public' | 'restricted' | 'private';
}

const EMPTY_DRAFT: KBDraft = {
  name: '',
  description: '',
  purpose: '',
  scope: 'org',
  visibility: 'public',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function KnowledgeManagement() {
  // List state
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Create modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [draft, setDraft] = useState<KBDraft>(EMPTY_DRAFT);
  const [isSaving, setIsSaving] = useState(false);

  // Detail view
  const [view, setView] = useState<View>('list');
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('documents');

  // Detail data
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [wikiPages, setWikiPages] = useState<WikiPage[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<WikiPage | null>(null);

  // ---- Data loading ----

  const loadKBs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getKnowledgeBases();
      setKnowledgeBases(data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadKBs(); }, [loadKBs]);

  const loadDetail = useCallback(async (kb: KnowledgeBase) => {
    setIsDetailLoading(true);
    try {
      const [docs, pages] = await Promise.all([
        getDocuments(kb.id),
        getWikiPages(kb.id),
      ]);
      setDocuments(docs);
      setWikiPages(pages);
    } catch (e: any) {
      setError(e.message || '加载详情失败');
    } finally {
      setIsDetailLoading(false);
    }
  }, []);

  // ---- Actions ----

  const handleCreate = async () => {
    if (!draft.name.trim()) return;
    setIsSaving(true);
    try {
      await createKnowledgeBase(draft);
      setMessage('知识库创建成功');
      setIsCreateModalOpen(false);
      setDraft(EMPTY_DRAFT);
      await loadKBs();
    } catch (e: any) {
      setError(e.message || '创建失败');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (kb: KnowledgeBase) => {
    if (!confirm(`确定删除知识库「${kb.name}」？所有文档和 Wiki 页面将一并删除。`)) return;
    try {
      await deleteKnowledgeBase(kb.id);
      setMessage('已删除');
      if (selectedKB?.id === kb.id) {
        setView('list');
        setSelectedKB(null);
      }
      await loadKBs();
    } catch (e: any) {
      setError(e.message || '删除失败');
    }
  };

  const handleUpload = async (kbId: number, file: File) => {
    try {
      await uploadDocument(kbId, file);
      setMessage('文档上传成功');
      if (selectedKB) {
        const docs = await getDocuments(kbId);
        setDocuments(docs);
      }
    } catch (e: any) {
      setError(e.message || '上传失败');
    }
  };

  const handleDeleteDoc = async (kbId: number, docId: number) => {
    if (!confirm('确定删除此文档？')) return;
    try {
      await deleteDocument(kbId, docId);
      setMessage('文档已删除');
      const docs = await getDocuments(kbId);
      setDocuments(docs);
    } catch (e: any) {
      setError(e.message || '删除失败');
    }
  };

  const handleSearch = async () => {
    if (!selectedKB || !searchQuery.trim()) return;
    setIsDetailLoading(true);
    try {
      const results = await searchKnowledgeBase(selectedKB.id, searchQuery);
      setSearchResults(results);
    } catch (e: any) {
      setError(e.message || '搜索失败');
    } finally {
      setIsDetailLoading(false);
    }
  };

  const openDetail = (kb: KnowledgeBase) => {
    setSelectedKB(kb);
    setView('detail');
    setDetailTab('documents');
    setSelectedPage(null);
    setSearchQuery('');
    setSearchResults([]);
    loadDetail(kb);
  };

  // Auto-clear messages
  useEffect(() => {
    if (message) {
      const t = setTimeout(() => setMessage(null), 3000);
      return () => clearTimeout(t);
    }
  }, [message]);

  // ---- Render ----

  const scopeLabel = (scope: string) => {
    const map: Record<string, string> = { org: '组织级', team: '团队级', personal: '个人级' };
    return map[scope] || scope;
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = {
      pending: '待编译', compiling: '编译中', compiled: '已编译', failed: '失败',
    };
    return map[status] || status;
  };

  const statusColor = (status: string) => {
    const map: Record<string, string> = {
      pending: 'text-amber-400',
      compiling: 'text-blue-400',
      compiled: 'text-emerald-400',
      failed: 'text-red-400',
    };
    return map[status] || 'text-slate-400';
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* Toast messages */}
      <AnimatePresence>
        {message && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-6 right-6 z-[9999] rounded-lg bg-emerald-500/90 px-4 py-2 text-sm text-white shadow-lg backdrop-blur"
          >
            {message}
          </motion.div>
        )}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-6 right-6 z-[9999] flex items-center gap-2 rounded-lg bg-red-500/90 px-4 py-2 text-sm text-white shadow-lg backdrop-blur"
          >
            <AlertCircle className="h-4 w-4" />
            {error}
            <button onClick={() => setError(null)} className="ml-1 opacity-70 hover:opacity-100">
              <X className="h-3 w-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {view === 'detail' && (
            <button
              onClick={() => { setView('list'); setSelectedKB(null); }}
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
            >
              <ChevronRight className="h-5 w-5 rotate-180" />
            </button>
          )}
          <div>
            <h2 className="text-lg font-semibold text-white">
              {view === 'list' ? '知识库管理' : selectedKB?.name}
            </h2>
            <p className="text-sm text-slate-400">
              {view === 'list'
                ? '管理组织知识库、文档和 Wiki 页面'
                : `${scopeLabel(selectedKB?.scope || '')} · ${selectedKB?.page_count || 0} 个 Wiki 页面`}
            </p>
          </div>
        </div>
        {view === 'list' && (
          <Button
            onClick={() => setIsCreateModalOpen(true)}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            新建知识库
          </Button>
        )}
      </div>

      {/* List View */}
      {view === 'list' && (
        <div className="space-y-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-20 text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              加载中…
            </div>
          ) : knowledgeBases.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <Database className="mb-3 h-10 w-10 opacity-40" />
              <p>暂无知识库</p>
              <p className="mt-1 text-xs">点击"新建知识库"开始</p>
            </div>
          ) : (
            knowledgeBases.map((kb) => (
              <motion.div
                key={kb.id}
                layout
                className="group flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 transition-colors hover:border-white/[0.12] hover:bg-white/[0.05]"
              >
                <button
                  onClick={() => openDetail(kb)}
                  className="flex flex-1 items-center gap-4 text-left"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400">
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-white">{kb.name}</span>
                      <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-slate-400">
                        {scopeLabel(kb.scope)}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-sm text-slate-500">
                      {kb.description || kb.purpose || '暂无描述'}
                    </p>
                  </div>
                  <div className="flex items-center gap-6 text-sm text-slate-500">
                    <span>{kb.document_count} 文档</span>
                    <span>{kb.page_count} 页面</span>
                  </div>
                </button>
                <button
                  onClick={() => handleDelete(kb)}
                  className="ml-3 rounded-lg p-2 text-slate-600 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400 group-hover:opacity-100"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </motion.div>
            ))
          )}
        </div>
      )}

      {/* Detail View */}
      {view === 'detail' && selectedKB && (
        <div className="space-y-4">
          {/* Tabs */}
          <div className="flex gap-1 rounded-lg bg-white/[0.03] p-1 flex-wrap">
            {([
              { id: 'documents' as const, label: '文档', icon: FileText },
              { id: 'wiki' as const, label: 'Wiki 页面', icon: BookOpen },
              { id: 'search' as const, label: '搜索测试', icon: Search },
              { id: 'reviews' as const, label: '审核队列', icon: AlertCircle },
              { id: 'graph' as const, label: '知识图谱', icon: Database },
            ]).map((tab) => (
              <button
                key={tab.id}
                onClick={() => { setDetailTab(tab.id); setSelectedPage(null); }}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors',
                  detailTab === tab.id
                    ? 'bg-white/[0.08] text-white'
                    : 'text-slate-500 hover:text-slate-300',
                )}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {isDetailLoading && detailTab !== 'search' && (
            <div className="flex items-center justify-center py-16 text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              加载中…
            </div>
          )}

          {/* Documents Tab */}
          {detailTab === 'documents' && !isDetailLoading && (
            <div className="space-y-3">
              {/* Upload area */}
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-white/[0.08] py-6 text-sm text-slate-500 transition-colors hover:border-brand-500/30 hover:text-brand-400">
                <Upload className="h-4 w-4" />
                点击上传文档（PDF / Word / Markdown）
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.md,.html,.txt"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUpload(selectedKB.id, file);
                    e.target.value = '';
                  }}
                />
              </label>

              {/* Document list */}
              {documents.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-600">暂无文档</p>
              ) : (
                documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="h-4 w-4 text-slate-500" />
                      <div>
                        <p className="text-sm text-white">{doc.title}</p>
                        <p className="text-xs text-slate-600">
                          {doc.file_type.toUpperCase()} · {formatSize(doc.file_size)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={cn('text-xs', statusColor(doc.status))}>
                        {statusLabel(doc.status)}
                      </span>
                      <button
                        onClick={() => handleDeleteDoc(selectedKB.id, doc.id)}
                        className="rounded p-1 text-slate-600 hover:bg-red-500/10 hover:text-red-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Wiki Pages Tab */}
          {detailTab === 'wiki' && !isDetailLoading && (
            <div className="space-y-3">
              {selectedPage ? (
                /* Page detail */
                <div className="space-y-4">
                  <button
                    onClick={() => setSelectedPage(null)}
                    className="flex items-center gap-1 text-sm text-slate-500 hover:text-white"
                  >
                    <ChevronRight className="h-4 w-4 rotate-180" />
                    返回列表
                  </button>
                  <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-6">
                    <div className="mb-4 flex items-center gap-3">
                      <h3 className="text-lg font-semibold text-white">{selectedPage.title}</h3>
                      <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-slate-400">
                        {selectedPage.page_type}
                      </span>
                      <span className="rounded-full bg-brand-500/10 px-2 py-0.5 text-xs text-brand-400">
                        {selectedPage.authority_level}
                      </span>
                    </div>
                    <pre className="whitespace-pre-wrap rounded-lg bg-black/20 p-4 font-mono text-sm leading-relaxed text-slate-300">
                      {selectedPage.content}
                    </pre>
                    {selectedPage.sources.length > 0 && (
                      <div className="mt-4 text-xs text-slate-600">
                        来源: {selectedPage.sources.join(', ')}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* Page list */
                wikiPages.length === 0 ? (
                  <p className="py-8 text-center text-sm text-slate-600">
                    暂无 Wiki 页面。上传文档后系统将自动编译生成。
                  </p>
                ) : (
                  wikiPages.map((page) => (
                    <button
                      key={page.id}
                      onClick={() => setSelectedPage(page)}
                      className="flex w-full items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3 text-left transition-colors hover:border-white/[0.1] hover:bg-white/[0.04]"
                    >
                      <div className="flex items-center gap-3">
                        <BookOpen className="h-4 w-4 text-slate-500" />
                        <div>
                          <p className="text-sm text-white">{page.title}</p>
                          <p className="text-xs text-slate-600">{page.page_type}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-brand-500/10 px-2 py-0.5 text-xs text-brand-400">
                          {page.authority_level}
                        </span>
                        <Eye className="h-4 w-4 text-slate-600" />
                      </div>
                    </button>
                  ))
                )
              )}
            </div>
          )}

          {/* Search Tab */}
          {detailTab === 'search' && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="输入查询内容测试检索效果…"
                  className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-white placeholder-slate-600 outline-none transition-colors focus:border-brand-500/40"
                />
                <Button onClick={handleSearch} disabled={!searchQuery.trim() || isDetailLoading}>
                  {isDetailLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                </Button>
              </div>

              {searchResults.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-slate-500">{searchResults.length} 条结果</p>
                  {searchResults.map((r) => (
                    <div
                      key={r.page_id}
                      className="rounded-lg border border-white/[0.04] bg-white/[0.02] p-4"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <span className="text-sm font-medium text-white">{r.title}</span>
                        <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-slate-500">
                          {r.page_type}
                        </span>
                        <span className="ml-auto text-xs text-slate-600">
                          得分: {r.score.toFixed(3)} · {r.authority_level}
                        </span>
                      </div>
                      <p className="line-clamp-3 text-sm text-slate-400">{r.content}</p>
                    </div>
                  ))}
                </div>
              )}

              {searchResults.length === 0 && searchQuery && !isDetailLoading && (
                <p className="py-8 text-center text-sm text-slate-600">无匹配结果</p>
              )}
            </div>
          )}

          {/* Reviews Tab */}
          {detailTab === 'reviews' && !isDetailLoading && (
            <ReviewQueue kbId={selectedKB.id} />
          )}

          {/* Graph Tab */}
          {detailTab === 'graph' && !isDetailLoading && (
            <KnowledgeGraph kbId={selectedKB.id} />
          )}
        </div>
      )}

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateModalOpen && (
          <CreateKBModal
            draft={draft}
            setDraft={setDraft}
            isSaving={isSaving}
            onCreate={handleCreate}
            onClose={() => { setIsCreateModalOpen(false); setDraft(EMPTY_DRAFT); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create Modal
// ---------------------------------------------------------------------------

function CreateKBModal({
  draft,
  setDraft,
  isSaving,
  onCreate,
  onClose,
}: {
  draft: KBDraft;
  setDraft: (d: KBDraft) => void;
  isSaving: boolean;
  onCreate: () => void;
  onClose: () => void;
}) {
  useAdminModalBackdrop(true);

  return createPortal(
    <div
      className="fixed inset-0 z-[9000] flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-lg rounded-xl border border-slate-200/80 bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-900">新建知识库</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">名称 *</label>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="例如：公司技术文档"
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 outline-none transition-colors focus:border-[#2b87c2] focus:ring-2 focus:ring-[#2b87c2]/20"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">描述</label>
            <input
              type="text"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="简要说明知识库用途"
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 outline-none transition-colors focus:border-[#2b87c2] focus:ring-2 focus:ring-[#2b87c2]/20"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              目标声明
              <span className="ml-1 text-xs text-slate-400">（告诉 LLM 这个知识库关注什么）</span>
            </label>
            <textarea
              value={draft.purpose}
              onChange={(e) => setDraft({ ...draft, purpose: e.target.value })}
              placeholder="例如：本知识库包含公司后端服务的部署运维规范，关注 Docker 部署、监控告警、故障排查"
              rows={3}
              className="w-full resize-none rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 outline-none transition-colors focus:border-[#2b87c2] focus:ring-2 focus:ring-[#2b87c2]/20"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-slate-700">归属</label>
              <select
                value={draft.scope}
                onChange={(e) => setDraft({ ...draft, scope: e.target.value as KBDraft['scope'] })}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors focus:border-[#2b87c2] focus:ring-2 focus:ring-[#2b87c2]/20"
              >
                <option value="org">组织级</option>
                <option value="team">团队级</option>
                <option value="personal">个人级</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-slate-700">可见性</label>
              <select
                value={draft.visibility}
                onChange={(e) => setDraft({ ...draft, visibility: e.target.value as KBDraft['visibility'] })}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors focus:border-[#2b87c2] focus:ring-2 focus:ring-[#2b87c2]/20"
              >
                <option value="public">公开</option>
                <option value="restricted">受限</option>
                <option value="private">私有</option>
              </select>
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button onClick={onCreate} disabled={!draft.name.trim() || isSaving}>
            {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {isSaving ? '创建中…' : '创建'}
          </Button>
        </div>
      </motion.div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Review Queue Component
// ---------------------------------------------------------------------------

function ReviewQueue({ kbId }: { kbId: number }) {
  const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<number | null>(null);

  const loadReviews = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/knowledge/bases/${kbId}/reviews`);
      if (res.ok) {
        setReviews(await res.json());
      }
    } catch (e) {
      console.error('Failed to load reviews:', e);
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => { loadReviews(); }, [loadReviews]);

  const handleResolve = async (reviewId: number, status: string, note: string) => {
    setResolving(reviewId);
    try {
      await fetch(`/api/v1/knowledge/bases/${kbId}/reviews/${reviewId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, resolution_note: note }),
      });
      loadReviews();
    } catch (e) {
      console.error('Failed to resolve review:', e);
    } finally {
      setResolving(null);
    }
  };

  const typeLabels: Record<string, string> = {
    conflict_resolution: '矛盾解决',
    page_creation: '新页面确认',
    page_merge: '页面合并',
    page_delete: '页面删除',
    authority_upgrade: '权威性提升',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (reviews.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-slate-500">
        <AlertCircle className="mx-auto mb-3 h-10 w-10 opacity-40" />
        暂无待审核项
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviews.map((review) => (
        <div key={review.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400">
              {typeLabels[review.review_type] || review.review_type}
            </span>
            <span className={cn(
              'rounded-full px-2 py-0.5 text-xs',
              review.status === 'pending' ? 'bg-amber-500/10 text-amber-400' :
              review.status === 'approved' ? 'bg-emerald-500/10 text-emerald-400' :
              'bg-slate-500/10 text-slate-400'
            )}>
              {review.status === 'pending' ? '待审核' : review.status === 'approved' ? '已通过' : review.status}
            </span>
          </div>
          <h4 className="text-sm font-medium text-white">{review.title}</h4>
          {review.description && (
            <p className="mt-1 text-xs text-slate-400">{review.description}</p>
          )}
          {review.status === 'pending' && (
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => handleResolve(review.id, 'approved', 'Approved')}
                disabled={resolving === review.id}
                className="rounded-md bg-emerald-500/20 px-3 py-1.5 text-xs text-emerald-400 hover:bg-emerald-500/30"
              >
                通过
              </button>
              <button
                onClick={() => handleResolve(review.id, 'rejected', 'Rejected')}
                disabled={resolving === review.id}
                className="rounded-md bg-rose-500/20 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/30"
              >
                拒绝
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Knowledge Graph Component (Simple)
// ---------------------------------------------------------------------------

function KnowledgeGraph({ kbId }: { kbId: number }) {
  const [graph, setGraph] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/v1/knowledge/bases/${kbId}/graph`)
      .then(res => res.ok ? res.json() : { nodes: [], edges: [] })
      .then(data => setGraph(data))
      .catch(() => setGraph({ nodes: [], edges: [] }))
      .finally(() => setLoading(false));
  }, [kbId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (graph.nodes.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-slate-500">
        <Database className="mx-auto mb-3 h-10 w-10 opacity-40" />
        暂无知识图谱数据
      </div>
    );
  }

  // Simple force-directed layout simulation
  const width = 600;
  const height = 400;
  const positionedNodes = graph.nodes.map((node, i) => ({
    ...node,
    x: width / 2 + Math.cos((i / graph.nodes.length) * Math.PI * 2) * 150,
    y: height / 2 + Math.sin((i / graph.nodes.length) * Math.PI * 2) * 150,
  }));

  const nodeMap = new Map(positionedNodes.map(n => [n.id, n]));

  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* Edges */}
        {graph.edges.map((edge, i) => {
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
              stroke={edge.type === 'contradicts' ? '#f87171' : '#64748b'}
              strokeWidth={edge.type === 'contradicts' ? 2 : 1}
              strokeDasharray={edge.type === 'reference' ? '4 4' : undefined}
              opacity={0.6}
            />
          );
        })}
        {/* Nodes */}
        {positionedNodes.map((node) => (
          <g key={node.id}>
            <circle
              cx={node.x}
              cy={node.y}
              r={node.authority === 'L3' ? 20 : node.authority === 'L2' ? 16 : 12}
              fill={node.authority === 'L3' ? '#3b82f6' : node.authority === 'L2' ? '#8b5cf6' : '#64748b'}
              opacity={0.8}
            />
            <text
              x={node.x}
              y={node.y + 30}
              textAnchor="middle"
              fill="#94a3b8"
              fontSize={10}
            >
              {node.label.length > 10 ? node.label.slice(0, 10) + '...' : node.label}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-4 flex gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-blue-500" /> L3 锁定</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-purple-500" /> L2 已审核</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-full bg-slate-500" /> L1 自动</span>
      </div>
    </div>
  );
}
