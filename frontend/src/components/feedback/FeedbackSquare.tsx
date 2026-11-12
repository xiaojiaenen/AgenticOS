import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft, ChevronUp, Lock, MessageSquare, Plus, Search, Send } from 'lucide-react';
import { Button } from '../shadcn/button';
import { Input } from '../shadcn/input';
import { cn } from '../../lib/utils';
import { formatApiDateTime } from '../../lib/datetime';
import { toastError } from '../../lib/errors';
import {
  commentFeedback, createFeedback, getFeedback, listFeedback, voteFeedback,
  type FeedbackIssue, type IssueStatus, type IssueType, type IssueVisibility,
} from '../../services/feedbackService';
import { PRIORITY_META, STATUS_META, TYPE_META } from './feedbackMeta';

type View = { kind: 'list' } | { kind: 'detail'; id: number } | { kind: 'create' };

const FIELD =
  'w-full rounded-[10px] border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none transition placeholder:text-[var(--muted-foreground)] focus-visible:border-[var(--ring)] focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)]';

function StatusBadge({ status }: { status: IssueStatus }) {
  const m = STATUS_META[status];
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold', m.className)}>
      <span className={cn('size-1.5 rounded-full', m.dot)} /> {m.label}
    </span>
  );
}

function VoteButton({ issue, onVoted }: { issue: FeedbackIssue; onVoted: () => void }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => voteFeedback(issue.id),
    onSuccess: () => { onVoted(); void qc.invalidateQueries({ queryKey: ['feedback'] }); },
    onError: (e) => toast.error(toastError(e, '投票失败')),
  });
  return (
    <button
      type="button"
      onClick={() => mut.mutate()}
      disabled={mut.isPending}
      aria-label="我也有这个问题"
      className={cn(
        'flex w-12 shrink-0 flex-col items-center gap-0.5 rounded-xl border py-2 transition-all active:scale-95',
        issue.my_vote
          ? 'border-zinc-400 bg-zinc-100 text-zinc-600 dark:border-zinc-500/40 dark:bg-zinc-500/15 dark:text-zinc-400'
          : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:border-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-400',
      )}
    >
      <ChevronUp size={16} />
      <span className="text-xs font-semibold tabular-nums">{issue.vote_count}</span>
    </button>
  );
}

function IssueRow({ issue, onOpen }: { issue: FeedbackIssue; onOpen: (id: number) => void }) {
  return (
    <div className="relative flex items-start gap-3 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3 pl-4 transition-colors hover:border-[var(--border)]">
      {/* 左侧状态色条：列表里一眼分辨待处理 / 处理中 / 已解决 */}
      <span aria-hidden className={cn('absolute inset-y-0 left-0 w-[3px]', STATUS_META[issue.status].rail)} />
      <VoteButton issue={issue} onVoted={() => undefined} />
      <button type="button" onClick={() => onOpen(issue.id)} className="min-w-0 flex-1 text-left">
        <div className="flex items-center gap-2">
          <span className="text-sm">{TYPE_META[issue.type].emoji}</span>
          <span className="truncate text-sm font-semibold text-[var(--foreground)]">{issue.title}</span>
          {issue.visibility === 'private' && <Lock size={12} className="shrink-0 text-[var(--muted-foreground)]" />}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
          <StatusBadge status={issue.status} />
          <span>#{issue.id}</span>
          <span>{issue.author.name}</span>
          <span className="inline-flex items-center gap-1"><MessageSquare size={11} /> {issue.comment_count}</span>
          <span>{formatApiDateTime(issue.created_at)}</span>
        </div>
      </button>
    </div>
  );
}

function ListView({ onOpen, onCreate }: { onOpen: (id: number) => void; onCreate: () => void }) {
  const [search, setSearch] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [sort, setSort] = React.useState<'votes' | 'newest' | 'active'>('votes');
  const [mine, setMine] = React.useState(false);
  const [page, setPage] = React.useState(1);

  const list = useQuery({
    queryKey: ['feedback', 'list', { search, status, sort, mine, page }],
    queryFn: () => listFeedback({ search, status: status as IssueStatus | '', sort, mine, page, page_size: 15 }),
  });
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / 15));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[160px] flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="搜索反馈…" className="h-9 pl-8" />
        </div>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className={cn(FIELD, 'h-9 w-auto py-0')}>
          <option value="">全部状态</option>
          {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <Button size="sm" onClick={onCreate} className="h-9 gap-1"><Plus size={14} /> 提反馈</Button>
      </div>

      <div className="flex items-center gap-1 text-xs">
        {([['votes', '热门'], ['newest', '最新'], ['active', '活跃']] as const).map(([k, label]) => (
          <button key={k} type="button" onClick={() => { setSort(k); setPage(1); }}
            className={cn('rounded-full px-3 py-1 font-medium transition-colors', sort === k && !mine ? 'bg-[var(--foreground)] text-[var(--background)]' : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]')}>
            {label}
          </button>
        ))}
        <button type="button" onClick={() => { setMine((m) => !m); setPage(1); }}
          className={cn('ml-auto rounded-full px-3 py-1 font-medium transition-colors', mine ? 'bg-[var(--foreground)] text-[var(--background)]' : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]')}>
          我的
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {list.isLoading ? (
          <div className="py-10 text-center text-sm text-[var(--muted-foreground)]">加载中…</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <MessageSquare size={28} className="text-[var(--muted-foreground)]" />
            <p className="text-sm font-medium text-[var(--foreground)]">还没有反馈</p>
            <p className="text-xs text-[var(--muted-foreground)]">第一个提出建议或缺陷，推动产品变得更好。</p>
            <Button size="sm" variant="outline" onClick={onCreate} className="mt-1 gap-1"><Plus size={14} /> 提反馈</Button>
          </div>
        ) : (
          items.map((i) => <IssueRow key={i.id} issue={i} onOpen={onOpen} />)
        )}
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-2 text-xs">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</Button>
          <span className="text-[var(--muted-foreground)]">{page} / {pages}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>下一页</Button>
        </div>
      )}
    </div>
  );
}

function DetailView({ id, onBack }: { id: number; onBack: () => void }) {
  const qc = useQueryClient();
  const [comment, setComment] = React.useState('');
  const detail = useQuery({ queryKey: ['feedback', 'detail', id], queryFn: () => getFeedback(id) });
  const commentMut = useMutation({
    mutationFn: () => commentFeedback(id, comment.trim()),
    onSuccess: () => { setComment(''); void qc.invalidateQueries({ queryKey: ['feedback', 'detail', id] }); void qc.invalidateQueries({ queryKey: ['feedback'] }); },
    onError: (e) => toast.error(toastError(e, '评论失败')),
  });
  const data = detail.data;
  if (detail.isLoading) return <div className="py-10 text-center text-sm text-[var(--muted-foreground)]">加载中…</div>;
  if (!data) return <div className="py-10 text-center text-sm text-[var(--muted-foreground)]">反馈不存在或无权查看</div>;
  const { issue, comments } = data;

  return (
    <div className="flex flex-col gap-4">
      <button type="button" onClick={onBack} className="inline-flex w-fit items-center gap-1 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        <ArrowLeft size={14} /> 返回列表
      </button>
      <div>
        <div className="flex items-start gap-3">
          <VoteButton issue={issue} onVoted={() => void qc.invalidateQueries({ queryKey: ['feedback', 'detail', id] })} />
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold text-[var(--foreground)]">{issue.title}</h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
              <StatusBadge status={issue.status} />
              <span>{TYPE_META[issue.type].emoji} {TYPE_META[issue.type].label}</span>
              <span className={PRIORITY_META[issue.priority].className}>优先级 {PRIORITY_META[issue.priority].label}</span>
              <span>#{issue.id} · {issue.author.name} · {formatApiDateTime(issue.created_at)}</span>
            </div>
          </div>
        </div>
        {issue.body && <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">{issue.body}</p>}
        {Object.keys(issue.context || {}).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {Object.entries(issue.context).map(([k, v]) => (
              <span key={k} className="rounded-md bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[10px] text-[var(--muted-foreground)]">{k}: {String(v).slice(0, 40)}</span>
            ))}
          </div>
        )}
        {issue.resolution_note && (
          <div className="mt-3 rounded-xl border border-emerald-200/70 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
            <span className="font-semibold">处理结论：</span>{issue.resolution_note}
            {issue.shipped_version && <span className="ml-2 rounded bg-emerald-600/15 px-1.5 py-0.5 text-xs font-semibold">上线 {issue.shipped_version}</span>}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">讨论 · {comments.length}</p>
        {comments.map((c) => (
          <div key={c.id} className={cn('rounded-xl border p-3', c.is_system ? 'border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)]' : c.is_official ? 'border-zinc-300/70 bg-zinc-100/60 dark:border-zinc-500/30 dark:bg-zinc-500/10' : 'border-[var(--border-subtle)]')}>
            <div className="mb-1 flex items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
              <span className="font-semibold text-[var(--foreground)]">{c.is_system ? '系统' : c.author?.name ?? '匿名'}</span>
              {c.is_official && <span className="rounded bg-zinc-600/15 px-1.5 py-0.5 font-semibold text-zinc-600 dark:text-zinc-400">官方</span>}
              <span>{formatApiDateTime(c.created_at)}</span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">{c.body}</p>
          </div>
        ))}
        <div className="flex items-end gap-2">
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder="写下你的看法…" className={cn(FIELD, 'resize-none')} />
          <Button size="sm" className="h-9 gap-1" disabled={!comment.trim() || commentMut.isPending} onClick={() => commentMut.mutate()}>
            <Send size={14} /> 发送
          </Button>
        </div>
      </div>
    </div>
  );
}

function CreateView({ onDone, onCancel }: { onDone: (id: number) => void; onCancel: () => void }) {
  const [type, setType] = React.useState<IssueType>('feature');
  const [title, setTitle] = React.useState('');
  const [body, setBody] = React.useState('');
  const [visibility, setVisibility] = React.useState<IssueVisibility>('public');
  const mut = useMutation({
    mutationFn: () => createFeedback({
      type, title: title.trim(), body: body.trim(), visibility,
      context: { page: window.location.pathname, user_agent: navigator.userAgent.slice(0, 200) },
    }),
    onSuccess: (d) => { toast.success('反馈已提交，感谢你的建议！'); onDone(d.id); },
    onError: (e) => toast.error(toastError(e, '提交反馈失败')),
  });
  return (
    <div className="flex flex-col gap-4">
      <button type="button" onClick={onCancel} className="inline-flex w-fit items-center gap-1 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        <ArrowLeft size={14} /> 返回列表
      </button>
      <div className="grid grid-cols-4 gap-2">
        {(Object.keys(TYPE_META) as IssueType[]).map((t) => (
          <button key={t} type="button" onClick={() => setType(t)}
            className={cn('flex flex-col items-center gap-1 rounded-xl border py-3 text-xs font-medium transition-all', type === t ? 'border-zinc-400 bg-zinc-100 text-zinc-700 dark:border-zinc-500/40 dark:bg-zinc-500/15 dark:text-zinc-400' : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]')}>
            <span className="text-lg">{TYPE_META[t].emoji}</span>{TYPE_META[t].label}
          </button>
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold text-[var(--foreground)]">标题</label>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="一句话描述你的建议或问题" />
      </div>
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold text-[var(--foreground)]">详细描述</label>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} maxLength={10000} placeholder="补充背景、复现步骤或期望效果…" className={cn(FIELD, 'resize-y')} />
      </div>
      <label className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
        <input type="checkbox" checked={visibility === 'private'} onChange={(e) => setVisibility(e.target.checked ? 'private' : 'public')} className="size-4 rounded" />
        仅管理员和我可见（涉及敏感信息时勾选）
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
        <Button size="sm" disabled={!title.trim() || mut.isPending} onClick={() => mut.mutate()} className="gap-1">
          <Send size={14} /> {mut.isPending ? '提交中…' : '提交反馈'}
        </Button>
      </div>
    </div>
  );
}

/**
 * 反馈广场（页面形态，不再是模态框）。
 *
 * 迁移原因：模态框宽度受限、列表滚不动、详情挤在弹层里读不全。改成
 * 独立页面 /feedback 后可以直接占满内容区，列表与详情并排也不挤。
 * 内部三视图（列表 / 详情 / 新建）逻辑保持原样，只换外壳。
 */
export function FeedbackSquare({ embedded = false }: { embedded?: boolean }) {
  const [view, setView] = React.useState<View>({ kind: 'list' });
  return (
    <div className={cn('flex h-full min-h-0 flex-col', embedded ? '' : 'mx-auto w-full max-w-4xl')}>
      <div className="shrink-0 border-b border-[var(--border-subtle)] px-1 pb-3">
        <h1 className="flex items-center gap-2 text-base font-semibold text-[var(--foreground)]">
          <MessageSquare size={17} className="text-[var(--muted-foreground)]" /> 反馈广场
        </h1>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-4">
        {view.kind === 'list' && <ListView onOpen={(id) => setView({ kind: 'detail', id })} onCreate={() => setView({ kind: 'create' })} />}
        {view.kind === 'detail' && <DetailView id={view.id} onBack={() => setView({ kind: 'list' })} />}
        {view.kind === 'create' && <CreateView onCancel={() => setView({ kind: 'list' })} onDone={(id) => setView({ kind: 'detail', id })} />}
      </div>
    </div>
  );
}
