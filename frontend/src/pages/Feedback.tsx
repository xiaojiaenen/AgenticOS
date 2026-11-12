import { FeedbackSquare } from '../components/feedback/FeedbackSquare';
import { PageShell } from '../components/ui/PageShell';

/** 反馈广场独立页（取代原来的模态框）。 */
export function Feedback() {
  return (
    <PageShell
      width="narrow"
      header={{
        kicker: 'FEEDBACK',
        title: '反馈广场',
        description: '提出建议或缺陷，投票推动优先级；每一步处理进度都可见。',
        back: true,
      }}
    >
      <FeedbackSquare />
    </PageShell>
  );
}

export default Feedback;
