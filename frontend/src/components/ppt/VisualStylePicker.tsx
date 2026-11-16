/**
 * PPT 视觉风格选择器（输入区上方一行）。
 *
 * **为什么需要它**：主题（配色）和视觉风格是正交的两层 ——
 *   - 主题：色值 / 字体族 / 圆角 / 阴影，生成后还能 retheme 切换；
 *   - 风格：形状语言 / 装饰密度 / 留白节奏 / 纹理层次，写进 SVG 本体，
 *     生成后无法更改。
 * 本地此前只有主题层，用户切主题只看到颜色变化、觉得"样式没变"。
 *
 * 因此这个选择器管的是「**下一次生成**用哪个风格」，只在 ppt 模式出现，
 * 不影响已生成的产物。留空 = 让模型从 18 种目录里自行挑选。
 */
import * as React from 'react';
import { createPortal } from 'react-dom';
import { Palette, X } from 'lucide-react';
import { toast } from 'sonner';

import { cn } from '../../lib/utils';
import {
  listPptVisualStyles,
  VISUAL_STYLE_CATEGORY_LABELS,
  type PptVisualStyle,
} from '../../services/agentService';

export interface VisualStylePickerProps {
  /** 当前选中的风格 id；空串 = 不指定 */
  value: string;
  onChange: (styleId: string) => void;
}

export const VisualStylePicker: React.FC<VisualStylePickerProps> = ({ value, onChange }) => {
  const [open, setOpen] = React.useState(false);
  const [styles, setStyles] = React.useState<PptVisualStyle[]>([]);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!open || styles.length > 0) return;
    setLoading(true);
    listPptVisualStyles()
      .then(setStyles)
      .catch((err) => {
        console.error('[VisualStyle] load failed:', err);
        toast.error('加载视觉风格失败');
      })
      .finally(() => setLoading(false));
  }, [open, styles.length]);

  const selected = styles.find((s) => s.id === value);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
          value
            ? 'border-[var(--ring)] bg-[var(--ring-halo)] text-[var(--foreground)]'
            : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
        )}
        title="选择 PPT 视觉风格（与配色正交，仅影响下次生成）"
      >
        <Palette size={12} />
        {selected ? selected.label : '视觉风格：自动'}
      </button>

      {/* portal 到 body：本组件在 Chat 页根 motion.div（带 transform）内，
          fixed 遮罩会被裁剪（同 PublishToGalleryButton 的坑）。 */}
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
            role="presentation"
            onClick={(e) => {
              if (e.target === e.currentTarget) setOpen(false);
            }}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-label="选择视觉风格"
              className="max-h-[85vh] w-[min(92%,720px)] overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-2xl"
            >
              <div className="mb-1 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-[var(--foreground)]">视觉风格</h3>
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    风格决定形状语言、装饰密度、留白节奏、纹理层次；<b>配色由主题单独决定</b>。
                    两者组合使用 —— 例如 <code className="rounded bg-[var(--surface-2)] px-1">github</code> 主题 ×{' '}
                    <code className="rounded bg-[var(--surface-2)] px-1">swiss-minimal</code> 风格。
                    风格写进 SVG 本体，<b>只在下次生成生效</b>，不改动已有产物。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="shrink-0 rounded-lg p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                  aria-label="关闭"
                >
                  <X size={16} />
                </button>
              </div>

              {/* 自动 = 让模型从目录里挑 */}
              <button
                type="button"
                onClick={() => {
                  onChange('');
                  setOpen(false);
                }}
                className={cn(
                  'mt-3 flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs transition-colors',
                  !value
                    ? 'border-[var(--ring)] bg-[var(--ring-halo)] font-semibold text-[var(--foreground)]'
                    : 'border-[var(--border-subtle)] hover:bg-[var(--surface-2)]',
                )}
              >
                自动（由模型按内容选择）
                <span className="text-[10px] font-normal text-[var(--muted-foreground)]">
                  推荐首次使用
                </span>
              </button>

              {loading && (
                <p className="mt-4 text-center text-xs text-[var(--muted-foreground)]">加载中…</p>
              )}

              {(['corporate', 'editorial', 'expressive', 'hand_drawn', 'specialty'] as const).map(
                (cat) => {
                  const items = styles.filter((s) => s.category === cat);
                  if (items.length === 0) return null;
                  return (
                    <div key={cat} className="mt-4">
                      <div className="mb-2 text-[11px] font-semibold text-[var(--foreground)]">
                        {VISUAL_STYLE_CATEGORY_LABELS[cat] ?? cat}
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {items.map((s) => (
                          <button
                            key={s.id}
                            type="button"
                            onClick={() => {
                              onChange(s.id);
                              setOpen(false);
                            }}
                            className={cn(
                              'rounded-xl border p-2.5 text-left transition-colors',
                              value === s.id
                                ? 'border-[var(--ring)] bg-[var(--ring-halo)]'
                                : 'border-[var(--border-subtle)] hover:bg-[var(--surface-2)]',
                            )}
                          >
                            <div className="flex items-baseline gap-1.5">
                              <span className="text-xs font-semibold text-[var(--foreground)]">
                                {s.label}
                              </span>
                              <code className="text-[9px] text-[var(--muted-foreground)]">{s.id}</code>
                            </div>
                            <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-[var(--muted-foreground)]">
                              {s.summary}
                            </p>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                },
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
};
