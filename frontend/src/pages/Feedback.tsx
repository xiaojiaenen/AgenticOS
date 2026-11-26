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
        description: '一句话就能提，好想法会被投票顶上来；处理进度会主动通知你。',
        back: true,
      }}
    >
      <FeedbackSquare />
    </PageShell>
  );
}

export default Feedback;
