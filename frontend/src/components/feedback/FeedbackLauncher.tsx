import React from 'react';
import { useLocation } from 'react-router-dom';
import { MessageSquarePlus } from 'lucide-react';
import { isAuthenticated } from '../../services/authTokenStore';
import { presenceHeartbeat } from '../../services/feedbackService';
import { FeedbackSquare } from './FeedbackSquare';

/**
 * 全站反馈入口 + 在线心跳。
 * - 右下角克制胶囊按钮（与聊天页浮动胶囊同规格），任意登录页可提反馈。
 * - 周期调用 /presence/heartbeat 刷新「当前在线」（5 分钟窗口）。
 * 登录/注册页不显示。
 */
export function FeedbackLauncher() {
  const { pathname } = useLocation();
  const [open, setOpen] = React.useState(false);
  const authed = isAuthenticated();
  const hidden = pathname === '/login' || pathname === '/signup';

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
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="意见反馈"
        className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-4 py-2.5 text-sm font-medium text-[var(--foreground)] shadow-md backdrop-blur transition-all hover:shadow-lg hover:-translate-y-0.5 active:scale-95"
      >
        <MessageSquarePlus size={16} className="text-indigo-500" />
        <span className="hidden sm:inline">反馈</span>
      </button>
      <FeedbackSquare open={open} onOpenChange={setOpen} />
    </>
  );
}
