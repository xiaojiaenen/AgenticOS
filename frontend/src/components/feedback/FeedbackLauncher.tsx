import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { MessageSquarePlus } from 'lucide-react';
import { isAuthenticated } from '../../services/authTokenStore';
import { presenceHeartbeat } from '../../services/feedbackService';

/**
 * 全站反馈入口 + 在线心跳。
 *
 * 反馈广场已从模态框迁到独立页面 /feedback（见 pages/Feedback.tsx），
 * 这里只保留右下角入口与 5 分钟窗口的在线心跳。
 */
export function FeedbackLauncher() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const authed = isAuthenticated();
  const hidden = pathname === '/login' || pathname === '/signup' || pathname === '/feedback';

  React.useEffect(() => {
    if (!authed || hidden) return;
    const beat = () => { void presenceHeartbeat().catch(() => undefined); };
    beat();
    const timer = window.setInterval(beat, 60_000);
    const onVis = () => { if (document.visibilityState === 'visible') beat(); };
    document.addEventListener('visibilitychange', onVis);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVis); };
  }, [authed, hidden]);

  if (!authed || hidden) return null;
  return (
    <button
      type="button"
      onClick={() => navigate('/feedback')}
      aria-label="意见反馈"
      className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-4 py-2.5 text-sm font-medium text-[var(--foreground)] shadow-md backdrop-blur transition-all hover:-translate-y-0.5 hover:shadow-lg active:scale-95"
    >
      <MessageSquarePlus size={16} className="text-[var(--muted-foreground)]" />
      <span className="hidden sm:inline">反馈</span>
    </button>
  );
}
