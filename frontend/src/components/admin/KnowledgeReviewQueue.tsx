/**
 * 知识库管理：审核队列面板。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertCircle, Loader2 } from 'lucide-react';
import { ErrorBanner } from './shared';
import { Button } from '@/components/shadcn/button';
import { cn } from '@/lib/utils';
import { ReviewItem, getReviewItems, updateReview } from '@/services/knowledgeService';

const typeLabels: Record<string, string> = {
  conflict_resolution: '矛盾解决',
  page_creation: '新页面确认',
  page_merge: '页面合并',
  page_delete: '页面删除',
  authority_upgrade: '权威性提升',
};

export function ReviewQueue({ kbId }: { kbId: number }) {
  const queryClient = useQueryClient();
  const reviewsQuery = useQuery({
    queryKey: ['admin', 'kb-reviews', kbId],
    queryFn: () => getReviewItems(kbId),
  });

  const resolveMutation = useMutation({
    mutationFn: ({ reviewId, status }: { reviewId: number; status: 'approved' | 'rejected' }) =>
      updateReview(kbId, reviewId, status, status === 'approved' ? 'Approved' : 'Rejected'),
    onSuccess: () => {
      toast.success('审核处理完成');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kb-reviews', kbId] });
    },
    onError: (err: Error) => toast.error(err.message || '处理审核失败'),
  });

  if (reviewsQuery.isPending) {
    return (
      <div className="flex items-center justify-center py-16 text-[var(--muted-foreground)]">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (reviewsQuery.isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <ErrorBanner message={(reviewsQuery.error as Error).message || '审核列表加载失败'} />
        <Button variant="outline" size="sm" onClick={() => void reviewsQuery.refetch()}>
          重试
        </Button>
      </div>
    );
  }

  const reviews = reviewsQuery.data;

  if (reviews.length === 0) {
    return (
      <div className="py-12 text-center text-sm font-medium text-[var(--muted-foreground)]">
        <AlertCircle className="mx-auto mb-3 h-10 w-10 opacity-40" />
        暂无待审核项
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviews.map((review: ReviewItem) => (
        <div key={review.id} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
              {typeLabels[review.review_type] || review.review_type}
            </span>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-xs font-medium',
                review.status === 'pending'
                  ? 'bg-amber-50 text-amber-700'
                  : review.status === 'approved'
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-[var(--surface-2)] text-zinc-600',
              )}
            >
              {review.status === 'pending' ? '待审核' : review.status === 'approved' ? '已通过' : review.status}
            </span>
          </div>
          <h4 className="text-sm font-semibold text-[var(--foreground)]">{review.title}</h4>
          {review.description && <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">{review.description}</p>}
          {review.status === 'pending' && (
            <div className="mt-3 flex gap-2">
              <Button
                size="xs"
                className="gap-1"
                onClick={() =>
                  resolveMutation.mutate({ reviewId: review.id, status: 'approved' })
                }
                disabled={resolveMutation.isPending}
              >
                通过
              </Button>
              <Button
                size="xs"
                variant="destructive"
                className="gap-1"
                onClick={() =>
                  resolveMutation.mutate({ reviewId: review.id, status: 'rejected' })
                }
                disabled={resolveMutation.isPending}
              >
                拒绝
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
