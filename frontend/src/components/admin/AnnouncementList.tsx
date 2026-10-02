/**
 * 公告设计台：公告列表面板。
 * 从 AnnouncementManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { BellRing, Loader2, Megaphone } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Announcement } from '@/services/announcementService';
import { THEME_DEFS } from '@/components/announcement/announcementTheme';

export function AnnouncementList({
  items,
  selectedId,
  isLoading,
  onSelect,
}: {
  items: Announcement[];
  selectedId: number | null;
  isLoading: boolean;
  onSelect: (item: Announcement) => void;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-700">已保存公告</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-[var(--foreground)]">公告列表</h2>
        </div>
        <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm">
          <Megaphone size={18} />
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-52 items-center justify-center gap-3 rounded-lg border border-dashed border-[var(--border-subtle)] bg-zinc-50/70 text-sm font-medium text-[var(--muted-foreground)]">
          <Loader2 size={16} className="animate-spin" />
          正在加载公告
        </div>
      ) : items.length === 0 ? (
        <div className="flex h-52 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[var(--border-subtle)] bg-zinc-50/70 text-center">
          <BellRing size={30} className="text-zinc-300" />
          <div>
            <p className="text-sm font-semibold text-zinc-700">还没有公告</p>
            <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">先创建一条给用户的入场提示吧。</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              className={cn(
                'w-full rounded-lg border px-4 py-4 text-left transition-all',
                selectedId === item.id
                  ? 'border-zinc-900 bg-zinc-100/80 shadow-md'
                  : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-zinc-300 hover:shadow-sm',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="h-11 w-11 rounded-lg" style={{ background: THEME_DEFS[item.theme].chipGradient }} />
                <div className="flex flex-wrap justify-end gap-2">
                  <span
                    className={cn(
                      'rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide',
                      item.active_now ? 'bg-emerald-100 text-emerald-700' : 'bg-[var(--surface-2)] text-[var(--muted-foreground)]',
                    )}
                  >
                    {item.active_now ? 'live' : item.is_published ? 'scheduled' : 'draft'}
                  </span>
                </div>
              </div>
              <p className="mt-4 text-lg font-semibold tracking-tight text-[var(--foreground)]">{item.title}</p>
              <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-[var(--muted-foreground)]">
                {item.subtitle || item.body || '暂无补充文案'}
              </p>
              <div className="mt-4 flex items-center justify-between gap-2 text-xs font-semibold text-[var(--muted-foreground)]">
                <div className="flex items-center gap-2">
                  <span>{item.eyebrow}</span>
                  <span
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]',
                      item.content_format === 'html' ? 'bg-amber-50 text-amber-600' : 'bg-zinc-100 text-zinc-700',
                    )}
                  >
                    {item.content_format === 'html' ? 'HTML' : 'MD'}
                  </span>
                </div>
                <span>{new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
