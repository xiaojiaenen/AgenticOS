/**
 * 作品库（Gallery）：deployed 状态的网站作品。
 *
 * - 公开作品：所有人可见，卡片直接打开 /sites/{slug}/；
 * - 私密作品：仅部署者（和管理员）可见，附 30 天签名访问链接，可重置。
 *
 * 设计：卡片网格 + 可见性徽章 + 技术栈标签；缩略预览用 iframe 按
 * `pointer-events-none` + 缩放渲染首屏（比纯色块直观，比截图轻）。
 */
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'motion/react';
import {
  ArrowLeft,
  Copy,
  ExternalLink,
  Globe,
  Link2,
  Loader2,
  Lock,
  RefreshCcw,
} from 'lucide-react';
import { toast } from 'sonner';
import { listGallery, resetSiteAccess, type GalleryItem } from '../services/websiteService';
import { Button } from '../components/shadcn/button';
import { toastError } from '../lib/errors';
import { cn } from '../lib/utils';
import { useGoBack } from '../hooks/useGoBack';
import { PageShell } from '../components/ui/PageShell';

type Filter = 'all' | 'public' | 'private';

const stackLabel = (stack: string | undefined) =>
  stack === 'react' ? 'React' : stack === 'vue' ? 'Vue' : 'Vanilla';

const VisibilityBadge = ({ visibility }: { visibility: 'public' | 'private' }) =>
  visibility === 'public' ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-400">
      <Globe size={10} /> 公开
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-400">
      <Lock size={10} /> 私密
    </span>
  );

const GalleryCard = ({
  item,
  onReset,
  resetting,
}: {
  item: GalleryItem;
  onReset: (id: number) => void;
  resetting: boolean;
}) => {
  const isPrivate = item.visibility === 'private';
  // 公开走 nginx /sites/；私密走带签名的私有端点
  const openUrl = isPrivate ? item.access_url : item.deploy_url;

  // 预览 iframe 很重（每卡一个完整页面渲染）：滚到视口内才挂载，
  // 加载完成前展示品牌占位卡 —— 避免整屏「白板卡」（走查问题）。
  const cardRef = React.useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = React.useState(false);
  const [previewLoaded, setPreviewLoaded] = React.useState(false);

  React.useEffect(() => {
    const el = cardRef.current;
    if (!el || inView) return;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setInView(true)),
      { rootMargin: '200px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [inView]);

  return (
    <motion.div
      ref={cardRef}
      className="group overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--border-strong)] hover:shadow-md"
    >
      {/* 预览条：占位卡在底层，iframe 懒挂载 + onLoad 淡入盖住占位 */}
      <div className="relative h-28 overflow-hidden border-b border-[var(--border-subtle)] bg-gradient-to-br from-slate-100 to-slate-50 dark:from-zinc-800 dark:to-zinc-900">
        <div
          className={cn(
            'absolute inset-0 flex flex-col items-center justify-center gap-1.5 transition-opacity duration-300',
            previewLoaded ? 'opacity-0' : 'opacity-100',
          )}
          aria-hidden="true"
        >
          <Globe size={20} className="text-[var(--muted-foreground)]/50" />
          <span className="max-w-[80%] truncate px-3 text-[10px] font-medium text-[var(--muted-foreground)]/70">
            {item.project_slug}
          </span>
        </div>
        {openUrl && inView && (
          <iframe
            title={`gallery-${item.project_slug}`}
            src={openUrl}
            onLoad={() => setPreviewLoaded(true)}
            className={cn(
              'pointer-events-none absolute left-0 top-0 h-[560px] w-[1280px] origin-top-left scale-[0.28] border-0 bg-white transition-opacity duration-300',
              previewLoaded ? 'opacity-100' : 'opacity-0',
            )}
            sandbox="allow-scripts"
            loading="lazy"
            tabIndex={-1}
          />
        )}
        <div className="absolute right-2 top-2">
          <VisibilityBadge visibility={item.visibility} />
        </div>
      </div>

      <div className="p-4">
        <div className="mb-2 flex items-center gap-2">
          <Globe size={14} className="shrink-0 text-[var(--muted-foreground)]" />
          <h3 className="min-w-0 truncate text-sm font-semibold text-[var(--foreground)]" title={item.project_slug}>
            {item.project_slug}
          </h3>
          <span className="ml-auto shrink-0 rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-semibold text-[var(--muted-foreground)]">
            {stackLabel(item.stack)}
          </span>
        </div>

        <p className="mb-3 text-xs text-[var(--muted-foreground)]">
          更新于 {item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
        </p>

        <div className="flex items-center gap-2">
          {openUrl ? (
            <a
              href={openUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-xs font-semibold text-[var(--primary-foreground)] transition-all hover:opacity-90 active:scale-[0.98]"
            >
              <ExternalLink size={12} /> 打开
            </a>
          ) : (
            <span className="inline-flex flex-1 items-center justify-center rounded-lg bg-[var(--surface-2)] px-3 py-1.5 text-xs text-[var(--muted-foreground)]">
              无访问链接
            </span>
          )}
          {openUrl && (
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1 px-2 text-xs"
              title="复制访问链接"
              aria-label="复制访问链接"
              onClick={() => {
                void navigator.clipboard
                  .writeText(`${window.location.origin}${openUrl}`)
                  .then(() => toast.success('链接已复制'))
                  .catch(() => toast.error('复制失败'));
              }}
            >
              <Copy size={12} />
            </Button>
          )}
          {isPrivate && (
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1 px-2 text-xs"
              title="重置私密访问链接（旧链接立即失效）"
              aria-label="重置私密访问链接"
              disabled={resetting}
              onClick={() => onReset(item.id)}
            >
              {resetting ? <Loader2 size={12} className="animate-spin" /> : <Link2 size={12} />}
            </Button>
          )}
        </div>
        {/* 之前这里直接打印原始 API 路径（api/v1/website/site/...），技术细节泄漏观感差；
            复制按钮已覆盖取链需求，不再展示 */}
      </div>
    </motion.div>
  );
};

export const GalleryPage = () => {
  const queryClient = useQueryClient();
  const goBack = useGoBack('/chat');
  const [filter, setFilter] = React.useState<Filter>('all');

  const galleryQuery = useQuery({
    queryKey: ['gallery'],
    queryFn: listGallery,
    refetchOnWindowFocus: false,
  });

  const resetMutation = useMutation({
    mutationFn: resetSiteAccess,
    onSuccess: () => {
      toast.success('访问链接已重置（旧链接立即失效）');
      void queryClient.invalidateQueries({ queryKey: ['gallery'] });
    },
    onError: (err: Error) => toast.error(toastError(err, '重置失败')),
  });

  const items = galleryQuery.data ?? [];
  const filtered = items.filter((i) => filter === 'all' || i.visibility === filter);
  const publicCount = items.filter((i) => i.visibility === 'public').length;
  const privateCount = items.length - publicCount;

  return (
    <PageShell width="wide">
      {/* /gallery 是独立路由、不带侧栏，必须有显式返回入口 */}
      <button
        type="button"
        onClick={goBack}
        className={cn(
          'mb-5 inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium transition-colors',
          'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
        )}
      >
        <ArrowLeft size={16} />
        返回对话
      </button>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-[var(--foreground)]">
            <Globe size={20} className="text-[var(--foreground)]" />
            作品库
          </h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            你构建并部署的网站作品——公开作品所有人可见，私密作品仅自己可见
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-[var(--surface-2)] p-1">
          {(
            [
              ['all', `全部 ${items.length}`],
              ['public', `公开 ${publicCount}`],
              ['private', `私密 ${privateCount}`],
            ] as [Filter, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                filter === key
                  ? 'bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
              )}
            >
              {label}
            </button>
          ))}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-1"
            onClick={() => void galleryQuery.refetch()}
            disabled={galleryQuery.isFetching}
            aria-label="刷新作品库"
          >
            {galleryQuery.isFetching ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCcw size={13} />
            )}
          </Button>
        </div>
      </div>

      {galleryQuery.isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Loader2 className="animate-spin text-[var(--muted-foreground)]" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex h-56 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border-subtle)] text-center">
          <Globe size={32} className="text-[var(--muted-foreground)]/50" />
          <p className="text-sm font-medium text-[var(--foreground)]">还没有作品</p>
          <p className="max-w-sm text-xs leading-relaxed text-[var(--muted-foreground)]">
            在对话里让网站智能体生成页面并构建，部署（可选公开或私密）后作品会出现在这里
          </p>
        </div>
      ) : (
        // 不做入场 stagger：同 AgentStore，避免 e2e 可见性计数竞态
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((item) => (
            <GalleryCard
              key={item.id}
              item={item}
              resetting={resetMutation.isPending}
              onReset={(id) => resetMutation.mutate(id)}
            />
          ))}
        </div>
      )}
    </PageShell>
  );
};

export default GalleryPage;
