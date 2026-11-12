import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { FeedbackSquare } from '../components/feedback/FeedbackSquare';

/** 反馈广场独立页（取代原来的模态框）。 */
export function Feedback() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-[var(--surface-0)] text-[var(--foreground)]">
      <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col px-5 py-6 md:px-8">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-5 inline-flex w-fit items-center gap-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          <ArrowLeft size={14} /> 返回
        </button>
        <div className="min-h-0 flex-1">
          <FeedbackSquare />
        </div>
      </div>
    </div>
  );
}

export default Feedback;
