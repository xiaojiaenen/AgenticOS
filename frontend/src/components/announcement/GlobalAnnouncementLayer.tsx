import React, { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { BellRing, ExternalLink, Sparkles, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getActiveAnnouncement, type Announcement, type AnnouncementTheme } from '../../services/announcementService';
import { getStoredUser, isAuthenticated } from '../../services/authService';
import { cn } from '../../lib/utils';
import { THEME_DEFS } from './announcementTheme';

function dismissalKey(item: Announcement): string {
  return `announcement:dismissed:${item.id}:${item.updated_at}`;
}

function shouldSkipForRoute(pathname: string): boolean {
  return pathname === '/login' || pathname === '/signup' || pathname === '/admin';
}

/* ──────────────────────────────────────
   Right-panel ambient decorative layer
   Always visible, regardless of image
   ────────────────────────────────────── */
const DecoElements: React.FC<{ theme: AnnouncementTheme }> = ({ theme }) => {
  const meta = THEME_DEFS[theme];

  return (
    <>
      {/* large soft orbs */}
      <motion.div
        animate={{ scale: [1, 1.08, 1], rotate: [0, 3, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute -right-8 -top-8 h-52 w-52 rounded-full blur-2xl"
        style={{ background: meta.orbA }}
      />
      <motion.div
        animate={{ scale: [1, 0.93, 1], rotate: [0, -2, 0] }}
        transition={{ duration: 9, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute -left-6 bottom-10 h-44 w-44 rounded-full blur-2xl"
        style={{ background: meta.orbB }}
      />
      <motion.div
        animate={{ scale: [1, 1.05, 1] }}
        transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut', delay: 2 }}
        className="absolute right-16 top-1/2 h-32 w-32 rounded-full blur-2xl"
        style={{ background: meta.orbC }}
      />

      {/* floating decorative dots */}
      <motion.div
        animate={{ y: [0, -8, 0], opacity: [0.35, 0.7, 0.35] }}
        transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute right-12 top-12 h-2.5 w-2.5 rounded-full"
        style={{ background: meta.dotColor, boxShadow: `0 0 10px ${meta.dotColor}` }}
      />
      <motion.div
        animate={{ y: [0, 6, 0], opacity: [0.3, 0.6, 0.3] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut', delay: 1.2 }}
        className="absolute right-28 top-28 h-2 w-2 rounded-full"
        style={{ background: meta.dotColor, boxShadow: `0 0 6px ${meta.dotColor}` }}
      />
      <motion.div
        animate={{ y: [0, -5, 0], opacity: [0.25, 0.55, 0.25] }}
        transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut', delay: 0.6 }}
        className="absolute left-6 top-16 h-2 w-2 rounded-full"
        style={{ background: meta.dotColor, boxShadow: `0 0 6px ${meta.dotColor}` }}
      />
      <motion.div
        animate={{ y: [0, 5, 0], opacity: [0.2, 0.5, 0.2] }}
        transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut', delay: 2.2 }}
        className="absolute right-20 bottom-28 h-1.5 w-1.5 rounded-full"
        style={{ background: meta.dotColor }}
      />

      {/* subtle dot grid — matching system's admin backdrop */}
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: 'radial-gradient(rgba(15,23,42,0.35) 0.5px, transparent 0.5px)',
          backgroundSize: '20px 20px',
        }}
      />

      {/* glass sheen overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(200deg,rgba(255,255,255,0.40)_0%,transparent_50%,rgba(255,255,255,0.18)_100%)]" />
    </>
  );
};

/* ──────────────────────────────────────
   No-image: glass-card decorative blocks
   ────────────────────────────────────── */
const NoImageDeco: React.FC<{ theme: AnnouncementTheme }> = ({ theme }) => {
  const meta = THEME_DEFS[theme];

  return (
    <>
      {/* bottom hero card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className="absolute bottom-6 right-6 left-6 rounded-[28px] border border-white/70 bg-white/72 p-6 shadow-lg backdrop-blur-xl"
      >
        <div className="mb-3 h-1.5 w-12 rounded-full bg-slate-300/80" />
        <div className="space-y-2.5">
          <div className="h-3 w-full rounded-full bg-slate-200/90" />
          <div className="h-3 w-5/6 rounded-full bg-slate-200/80" />
          <div className="h-3 w-3/4 rounded-full bg-slate-200/70" />
        </div>
        <div className="mt-5 flex items-center gap-3">
          <div className={cn('flex h-10 w-10 items-center justify-center rounded-2xl text-white shadow-md', meta.accentClass)}>
            <Sparkles size={16} />
          </div>
          <div>
            <p className="text-sm font-black text-slate-800">AgenticOS</p>
            <p className="text-[11px] font-semibold text-slate-400">Platform Notice</p>
          </div>
        </div>
      </motion.div>

      {/* top-right badge */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
        className="absolute right-8 top-12 rounded-2xl border border-white/60 bg-white/68 px-4 py-3 shadow-md backdrop-blur-lg"
      >
        <div className="flex items-center gap-2.5">
          <div className={cn('h-2.5 w-2.5 rounded-full shadow-[0_0_7px_currentColor]', meta.accentClass)} />
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Notice</div>
        </div>
        <div className="mt-2 flex gap-1.5">
          <div className="h-1 w-8 rounded-full bg-slate-300/70" />
          <div className="h-1 w-5 rounded-full bg-slate-300/50" />
          <div className="h-1 w-6 rounded-full bg-slate-300/60" />
        </div>
      </motion.div>
    </>
  );
};

export const GlobalAnnouncementLayer: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [item, setItem] = useState<Announcement | null>(null);
  const [open, setOpen] = useState(false);
  const [zoomImage, setZoomImage] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated() || shouldSkipForRoute(location.pathname)) {
      setItem(null);
      setOpen(false);
      return;
    }

    let cancelled = false;

    getActiveAnnouncement()
      .then((response) => {
        if (cancelled) return;
        const next = response.item;
        if (!next) {
          setItem(null);
          setOpen(false);
          return;
        }
        if (next.show_once && localStorage.getItem(dismissalKey(next)) === '1') {
          setItem(next);
          setOpen(false);
          return;
        }
        setItem(next);
        window.setTimeout(() => {
          if (!cancelled) setOpen(true);
        }, 220);
      })
      .catch(() => {
        if (!cancelled) {
          setItem(null);
          setOpen(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  const meta = useMemo(
    () => THEME_DEFS[item?.theme ?? 'aurora'],
    [item?.theme],
  );

  const handleClose = () => {
    if (!item) return;
    if (item.show_once) {
      localStorage.setItem(dismissalKey(item), '1');
    }
    setOpen(false);
  };

  const handleAction = () => {
    if (!item?.cta_link) {
      handleClose();
      return;
    }
    if (item.show_once) {
      localStorage.setItem(dismissalKey(item), '1');
    }
    setOpen(false);
    if (item.cta_link.startsWith('/')) {
      navigate(item.cta_link);
      return;
    }
    window.open(item.cta_link, '_blank', 'noopener,noreferrer');
  };

  if (!item || !getStoredUser() || shouldSkipForRoute(location.pathname)) {
    return null;
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[65] flex items-center justify-center px-4 py-6"
          style={{
            background: 'rgba(15,23,42,0.28)',
            backdropFilter: 'blur(8px)',
          }}
          onClick={() => {
            if (item.dismissible) handleClose();
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: 26, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 18, scale: 0.97 }}
            transition={{ duration: 0.30, ease: [0.16, 1, 0.3, 1] }}
            onClick={(event) => event.stopPropagation()}
            className="relative w-full max-w-3xl overflow-hidden rounded-[34px] border text-slate-800"
            style={{
              background: meta.bgGradient,
              borderColor: meta.borderColor,
              boxShadow: meta.shadow,
            }}
          >
            {/* left/right large ambient orbs (behind everything) */}
            <div className="absolute -left-16 top-6 h-60 w-60 rounded-full blur-3xl" style={{ background: meta.orbA }} />
            <div className="absolute -right-20 -bottom-12 h-72 w-72 rounded-full blur-3xl" style={{ background: meta.orbB }} />

            {/* top-edge highlight bar */}
            <div className="absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.7),rgba(255,255,255,0.9),rgba(255,255,255,0.7),transparent)]" />

            {item.dismissible && (
              <button
                type="button"
                onClick={handleClose}
                className="absolute right-5 top-5 z-20 flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200/60 bg-white/70 text-slate-400 transition-all hover:bg-white hover:text-slate-600 hover:shadow-sm"
                aria-label="关闭公告"
              >
                <X size={17} />
              </button>
            )}

            <div className="relative z-10 grid gap-0 lg:grid-cols-[1fr_1fr]">
              {/* ── Left column: text content ── */}
              <div className="p-7 sm:p-9">
                <div className={cn(
                  'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.18em]',
                  meta.accentLightClass, meta.accentTextClass,
                )}
                style={{ borderColor: 'currentColor', borderWidth: 1, background: 'rgba(255,255,255,0.6)' }}
                >
                  <BellRing size={13} />
                  {item.eyebrow || '系统公告'}
                </div>

                <h2 className="mt-6 max-w-lg font-display text-3xl font-black leading-tight tracking-[-0.04em] text-slate-900 sm:text-4xl">
                  {item.title}
                </h2>

                {item.subtitle && (
                  <p className="mt-4 max-w-lg text-base font-semibold leading-8 text-slate-600">
                    {item.subtitle}
                  </p>
                )}

                {item.body && (
                  item.content_format === 'html' ? (
                    <div
                      className="mt-5 max-w-xl text-sm font-medium leading-7 text-slate-500 sm:text-[15px]"
                      dangerouslySetInnerHTML={{ __html: item.body }}
                    />
                  ) : (
                    <div className="mt-5 max-w-xl text-sm font-medium leading-7 text-slate-500 sm:text-[15px] [&_strong]:text-slate-800 [&_h1]:text-slate-900 [&_h2]:text-slate-900 [&_h3]:text-slate-900 [&_pre]:bg-slate-100 [&_pre]:border [&_pre]:border-slate-200 [&_pre]:rounded-xl [&_pre]:p-4 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:text-[13px] [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded-md [&_code]:text-[0.9em] [&_code]:text-brand-700 [&_blockquote]:border-l-[3px] [&_blockquote]:border-brand-300 [&_blockquote]:pl-3.5 [&_blockquote]:my-2.5 [&_blockquote]:text-slate-500 [&_blockquote]:italic [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2.5 [&_ul]:space-y-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2.5 [&_ol]:space-y-1 [&_a]:text-brand-600 [&_a]:underline [&_hr]:border-t [&_hr]:border-slate-200 [&_hr]:my-4">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {item.body}
                      </ReactMarkdown>
                    </div>
                  )
                )}

                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={handleAction}
                    className={cn(
                      'inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-black text-white shadow-lg shadow-black/10 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-black/15',
                      meta.ctaBg,
                    )}
                  >
                    {item.cta_label || '进入平台'}
                    {item.cta_link && <ExternalLink size={15} />}
                  </button>
                  <button
                    type="button"
                    onClick={handleClose}
                    className={cn(
                      'inline-flex items-center gap-2 rounded-2xl border border-slate-200/70 bg-white/70 px-4 py-3 text-sm font-bold text-slate-500 transition-all hover:bg-white hover:text-slate-700',
                    )}
                  >
                    稍后再看
                  </button>
                </div>
              </div>

              {/* ── Right column: decoration always, image when present ── */}
              <div className="relative hidden min-h-[440px] overflow-hidden lg:block">
                <DecoElements theme={item.theme ?? 'aurora'} />

                {item.image_url && (
                  <motion.div
                    initial={{ opacity: 0, x: 30 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
                    className="absolute bottom-6 right-6 z-10 w-[68%] cursor-pointer overflow-hidden rounded-2xl border border-white/60 shadow-xl shadow-black/8 transition-transform hover:scale-[1.03]"
                    onClick={() => setZoomImage(item.image_url!)}
                  >
                    <div className="absolute -inset-2 rounded-2xl bg-white/30 blur-md" />
                    <img
                      src={item.image_url}
                      alt=""
                      className="relative w-full rounded-2xl object-cover"
                      style={{ aspectRatio: '4/3' }}
                    />
                    <div className="absolute inset-0 rounded-2xl bg-[linear-gradient(35deg,rgba(0,0,0,0.08)_0%,transparent_45%,rgba(255,255,255,0.10)_100%)]" />
                    <div className="absolute bottom-2 right-2 flex items-center gap-1 rounded-lg bg-white/80 px-2 py-1 text-[10px] font-semibold text-slate-500 backdrop-blur-sm shadow-sm">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/><path d="M11 8v6"/><path d="M8 11h6"/></svg>
                      点击放大
                    </div>
                  </motion.div>
                )}

                {!item.image_url && <NoImageDeco theme={item.theme ?? 'aurora'} />}
              </div>
            </div>

            {/* Click-to-enlarge image overlay */}
            <AnimatePresence>
              {zoomImage && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-lg"
                  onClick={() => setZoomImage(null)}
                >
                  <motion.div
                    initial={{ opacity: 0, scale: 0.88 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.88 }}
                    transition={{ duration: 0.22 }}
                    className="max-h-[85vh] max-w-[90vw] overflow-hidden rounded-3xl shadow-2xl"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <img
                      src={zoomImage}
                      alt="announcement illustration"
                      className="h-auto max-h-[85vh] w-auto max-w-[90vw] object-contain"
                    />
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
