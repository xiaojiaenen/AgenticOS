import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'motion/react';
import {
  Copy,
  Globe,
  LayoutGrid,
  Link2,
  Loader2,
  RefreshCcw,
  ShieldCheck,
} from 'lucide-react';
import { toast } from 'sonner';
import { listGallery, resetSiteAccess, type GalleryItem } from '../services/websiteService';
import { ArtifactMiniPreview, type MiniPreviewKind } from '../components/ui/ArtifactMiniPreview';
import { canEnterAdmin } from '@/services/authTokenStore';
import { toastError } from '../lib/errors';
import { cn } from '../lib/utils';

type Filter = 'all' | 'public' | 'private';

function displayName(item: { title?: string; project_slug: string }): string {
  const t = item.title?.trim();
  if (t) return t;
  return item.project_slug;
}

function relativeTime(value?: string | null): string {
  if (!value) return '—';
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return '—';
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} 个月前`;
  return `${Math.floor(months / 12)} 年前`;
}

const TYPE_LABEL = {
  website: '网站',
  ppt: 'PPT 矢量',
  document: '知识文档',
  sheet: 'UniverJS 表格',
} as const;

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
  const itemType = (item.item_type ?? 'website') as keyof typeof TYPE_LABEL;
  const isFile = itemType !== 'website';
  const openUrl = isPrivate
    ? item.access_url
    : isFile
      ? item.short_url ?? item.deploy_url
      : item.deploy_url;

  const [previewLoaded, setPreviewLoaded] = React.useState(false);

  const openPreview = () => {
    if (openUrl) window.open(openUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="aos-glass-surface aos-surface-interactive flex flex-col justify-between gap-3.5 rounded-2xl p-3.5">
      <div>
        {/* 16:9 缩略预览区：默认呈现原型同款柔和矢量图，有真实封面图时平滑淡入 */}
        <div
          role="button"
          tabIndex={0}
          onClick={openPreview}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              openPreview();
            }
          }}
          className={cn(
            'relative mb-3 aspect-[16/9] w-full overflow-hidden rounded-xl border border-[var(--border-subtle)]',
            openUrl ? 'cursor-pointer' : 'cursor-default',
          )}
        >
          <ArtifactMiniPreview kind={itemType as MiniPreviewKind} />
          {item.cover_url && (
            <img
              src={item.cover_url}
              alt={`${displayName(item)} 封面`}
              loading="lazy"
              onLoad={() => setPreviewLoaded(true)}
              className={cn(
                'absolute inset-0 h-full w-full object-cover object-top transition-opacity duration-300',
                previewLoaded ? 'opacity-100' : 'opacity-0',
              )}
            />
          )}
        </div>

        <div className="flex items-center justify-between gap-2 px-0.5">
          <h3 className="truncate text-[15px] font-semibold text-[var(--foreground)]" title={displayName(item)}>
            {displayName(item)}
          </h3>
          <span className="whitespace-nowrap rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10.5px] font-medium text-[var(--muted-foreground)]">
            {isPrivate ? '团队私密' : '已发布'}
          </span>
        </div>

        <div className="mt-1 truncate px-0.5 text-xs text-[var(--muted-foreground)]">
          <span>{TYPE_LABEL[itemType] || '应用'}</span>
          <span> · {relativeTime(item.updated_at ?? item.created_at)}</span>
          {item.project_slug && (
            <>
              <span> · </span>
              <span className="font-mono text-[11px]">{item.project_slug}</span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-0.5 pt-3">
        <button
          type="button"
          onClick={openPreview}
          disabled={!openUrl}
          className="aos-pill-btn !py-1 !px-3 !text-xs disabled:opacity-45"
        >
          打开预览
        </button>

        <div className="flex items-center gap-1.5">
          {openUrl && (
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard
                  .writeText(`${window.location.origin}${openUrl}`)
                  .then(() => toast.success('访问链接已复制'))
                  .catch(() => toast.error('复制失败'));
              }}
              className="inline-flex items-center gap-1 border-0 bg-transparent text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
            >
              <Copy size={12} />
              <span>复制链接</span>
            </button>
          )}
          {isPrivate && (
            <button
              type="button"
              disabled={resetting}
              onClick={() => onReset(item.id)}
              title="重置私密访问链接"
              className="inline-flex items-center gap-1 border-0 bg-transparent text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
            >
              {resetting ? <Loader2 size={12} className="animate-spin" /> : <Link2 size={12} />}
              <span>重置</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export const GalleryPage = () => {
  const queryClient = useQueryClient();
  const [filter, setFilter] = React.useState<Filter>('all');
  const canMod = canEnterAdmin();

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
    <motion.div
      key="gallery"
      initial={false}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="relative h-full w-full overflow-y-auto px-1 pb-14 font-sans text-[var(--foreground)] sm:px-3"
    >
      <main id="main-content" className="mx-auto w-full max-w-[1140px] px-1 sm:px-4">
        {/* 原版原型同款暖橙+天蓝渐层英雄横幅 */}
        <div className="aos-hero-banner mb-6 mt-1 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[var(--border-subtle)] p-6">
          <div className="flex items-center gap-3.5">
            <span className="aos-icon-badge aos-tone-violet h-11 w-11 !rounded-2xl">
              <LayoutGrid size={20} />
            </span>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)] sm:text-2xl">
                作品库与公开应用
              </h1>
              <p className="mt-0.5 text-xs text-[var(--muted-foreground)] sm:text-sm">
                团队已发布的网站短链、公开智能体应用与精品 PPT 模板
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {canMod && (
              <span className="aos-glass-surface inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-[var(--foreground)]">
                <ShieldCheck size={14} className="text-emerald-600 dark:text-emerald-400" />
                <span>已启用审核 / 下架权限</span>
              </span>
            )}
            <div className="flex items-center gap-1">
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
                  className={cn('aos-pill-btn !py-1 !px-3 !text-xs', filter === key && 'active')}
                >
                  {label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => void galleryQuery.refetch()}
                disabled={galleryQuery.isFetching}
                aria-label="刷新作品库"
                className="aos-pill-btn !p-1.5"
              >
                {galleryQuery.isFetching ? <Loader2 size={13} className="animate-spin" /> : <RefreshCcw size={13} />}
              </button>
            </div>
          </div>
        </div>

        {galleryQuery.isLoading ? (
          <div className="flex h-48 items-center justify-center">
            <Loader2 className="animate-spin text-[var(--muted-foreground)]" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="aos-glass-surface flex h-56 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[var(--border-subtle)] text-center">
            <Globe size={32} className="text-[var(--muted-foreground)]/50" />
            <p className="text-sm font-medium text-[var(--foreground)]">还没有作品</p>
            <p className="max-w-sm text-xs leading-relaxed text-[var(--muted-foreground)]">
              在对话里生成网站、PPT、文档或表格，点击产物上的「发布 / 公开」，审批通过后作品会出现在这里
            </p>
          </div>
        ) : (
          /* 原型同款 3 列卡片网格 */
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filtered.map((item) => (
              <GalleryCard
                key={`${item.item_type ?? 'website'}-${item.id}`}
                item={item}
                resetting={resetMutation.isPending}
                onReset={(id) => resetMutation.mutate(id)}
              />
            ))}
          </div>
        )}
      </main>
    </motion.div>
  );
};

export default GalleryPage;
