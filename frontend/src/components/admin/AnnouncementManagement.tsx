/**
 * 公告设计台：TanStack Query 数据层 + react-hook-form/zod 表单
 * + shadcn Dialog/AlertDialog/Checkbox。功能与后端 API 不变
 * （services/announcementService.ts），含 AI 公告生成。
 * 页面骨架与状态编排；弹窗 / 列表 / 编辑器 / 预览拆分至同目录子文件。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, RefreshCw, Wand2 } from 'lucide-react';
import { AdminPageHeader, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/shadcn/alert-dialog';
import {
  Announcement,
  createAnnouncement,
  deleteAnnouncement,
  getAnnouncements,
  updateAnnouncement,
} from '@/services/announcementService';
import { AiGenerateDialog } from './AnnouncementAiGenerateDialog';
import { AnnouncementList } from './AnnouncementList';
import { AnnouncementEditor } from './AnnouncementEditor';
import { AnnouncementPreview } from './AnnouncementPreview';
import {
  EMPTY_FORM,
  announcementSchema,
  formFromAnnouncement,
  fromLocalInputValue,
  type AnnouncementFormValues,
} from './announcementHelpers';

export const AnnouncementManagement = () => {
  const queryClient = useQueryClient();

  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [aiDialogOpen, setAiDialogOpen] = React.useState(false);

  const announcementsQuery = useQuery({
    queryKey: ['admin', 'announcements'],
    queryFn: getAnnouncements,
  });
  const items = announcementsQuery.data?.items ?? [];

  const form = useForm<AnnouncementFormValues>({
    resolver: zodResolver(announcementSchema),
    defaultValues: EMPTY_FORM,
  });

  React.useEffect(() => {
    if (announcementsQuery.isSuccess) {
      if (items.length > 0) {
        setSelectedId(items[0].id);
        form.reset(formFromAnnouncement(items[0]));
      } else {
        setSelectedId(null);
        form.reset(EMPTY_FORM);
      }
    }
    // 仅在数据首次加载时同步表单
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcementsQuery.isSuccess]);

  const handleSelect = (item: Announcement) => {
    setSelectedId(item.id);
    form.reset(formFromAnnouncement(item));
    setAiDialogOpen(false);
  };

  const handleCreateNew = () => {
    setSelectedId(null);
    form.reset(EMPTY_FORM);
    setAiDialogOpen(false);
  };

  const saveMutation = useMutation({
    mutationFn: async (values: AnnouncementFormValues) => {
      const payload = {
        eyebrow: values.eyebrow.trim() || '系统公告',
        title: values.title.trim(),
        subtitle: values.subtitle.trim(),
        body: values.body.trim(),
        image_url: values.image_url.trim() || null,
        content_format: values.content_format,
        theme: values.theme,
        cta_label: values.cta_label.trim() || null,
        cta_link: values.cta_link.trim() || null,
        is_published: values.is_published,
        dismissible: values.dismissible,
        show_once: values.show_once,
        starts_at: fromLocalInputValue(values.starts_at),
        ends_at: fromLocalInputValue(values.ends_at),
      };
      return selectedId === null
        ? createAnnouncement(payload)
        : updateAnnouncement(selectedId, payload);
    },
    onSuccess: async (saved) => {
      toast.success(selectedId === null ? '公告已创建' : '公告已更新');
      await queryClient.invalidateQueries({ queryKey: ['admin', 'announcements'] });
      setSelectedId(saved.id);
      form.reset(formFromAnnouncement(saved));
    },
    onError: (err: Error) => toast.error(err.message || '公告保存失败'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAnnouncement(id),
    onSuccess: () => {
      toast.success('公告已删除');
      setSelectedId(null);
      form.reset(EMPTY_FORM);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'announcements'] });
    },
    onError: (err: Error) => toast.error(err.message || '公告删除失败'),
  });

  const [deleteConfirmOpen, setDeleteConfirmOpen] = React.useState(false);
  const selectedItem = items.find((item) => item.id === selectedId) ?? null;

  const stats = {
    total: items.length,
    published: items.filter((item) => item.is_published).length,
    activeNow: items.filter((item) => item.active_now).length,
  };

  const formValues = form.watch();

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="Announcement Studio"
        title="用户公告设计台"
        description="撰写支持 Markdown 和 HTML 的公告，或让 AI 帮你一键生成。用户进入聊天或 Agent Store 时就会看到它。"
        actions={
          <>
            <KpiPill label="总公告数" value={stats.total} />
            <KpiPill label="已发布" value={stats.published} />
            <KpiPill label="当前生效" value={stats.activeNow} />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                form.setValue('content_format', formValues.content_format);
                form.setValue('theme', formValues.theme);
                setAiDialogOpen(true);
              }}
            >
              <Wand2 size={14} />
              AI 生成
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void announcementsQuery.refetch()}
              disabled={announcementsQuery.isFetching}
            >
              {announcementsQuery.isFetching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
            <Button size="sm" className="gap-1.5" onClick={handleCreateNew}>
              <Plus size={14} />
              新建公告
            </Button>
          </>
        }
      />

      {announcementsQuery.isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
          {(announcementsQuery.error as Error).message || '公告加载失败'}
        </div>
      ) : null}

      <AiGenerateDialog
        open={aiDialogOpen}
        initialFormat={formValues.content_format}
        initialTheme={formValues.theme}
        onApply={(draft) => {
          if (draft.eyebrow !== undefined) form.setValue('eyebrow', draft.eyebrow);
          if (draft.title !== undefined) form.setValue('title', draft.title);
          if (draft.subtitle !== undefined) form.setValue('subtitle', draft.subtitle);
          if (draft.body !== undefined) form.setValue('body', draft.body);
          if (draft.cta_label !== undefined) form.setValue('cta_label', draft.cta_label);
          if (draft.cta_link !== undefined) form.setValue('cta_link', draft.cta_link);
        }}
        onClose={() => setAiDialogOpen(false)}
      />

      <section className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        {/* 公告列表 */}
        <AnnouncementList
          items={items}
          selectedId={selectedId}
          isLoading={announcementsQuery.isLoading}
          onSelect={handleSelect}
        />

        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.1fr)_420px]">
          {/* 编辑器 */}
          <AnnouncementEditor
            form={form}
            selectedId={selectedId}
            isSaving={saveMutation.isPending}
            onSubmit={(values) => void saveMutation.mutateAsync(values)}
            onDeleteClick={() => setDeleteConfirmOpen(true)}
          />

          {/* Live Preview */}
          <AnnouncementPreview values={formValues} />
        </div>
      </section>

      {/* 删除确认 */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除公告</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除公告「{selectedItem?.title}」吗？用户将不再看到这条公告。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (selectedId !== null) deleteMutation.mutate(selectedId);
              }}
            >
              {deleteMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
