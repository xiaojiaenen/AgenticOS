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
      title="提建议、报问题、参与投票 — 你的声音会被看见"
      className="aos-top-pill fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full px-4 py-2.5 text-xs font-semibold text-[var(--foreground)] transition-all hover:-translate-y-0.5 active:scale-95"
    >
      <MessageSquarePlus size={16} className="aos-pulse-dot text-[var(--aos-brand-mark, #E85D2A)]" />
      <span className="hidden sm:inline">提建议 / 反馈</span>
    </button>
  );
}
