import { ArrowLeft } from 'lucide-react';
import { FeedbackSquare } from '../components/feedback/FeedbackSquare';
import { PageShell } from '../components/ui/PageShell';
import { useGoBack } from '../hooks/useGoBack';

/** 反馈广场独立页（取代原来的模态框）。 */
export function Feedback() {
  const goBack = useGoBack('/chat');
  return (
    <PageShell width="narrow">
      <button
        type="button"
        onClick={goBack}
        className="mb-5 inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
      >
        <ArrowLeft size={14} /> 返回
      </button>
      <FeedbackSquare />
    </PageShell>
  );
}

export default Feedback;
