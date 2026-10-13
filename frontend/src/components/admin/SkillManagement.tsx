/**
 * Skill 管理：TanStack Query 数据层 + TanStack Table + react-hook-form/zod 表单
 * + shadcn Dialog/AlertDialog。
 * 后端 API 不变（services/skillService.ts）。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  FileCode2,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Upload,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Checkbox } from '@/components/shadcn/checkbox';
import { Skeleton } from '@/components/shadcn/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
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
import { formatApiDate } from '@/lib/datetime';
import { cn } from '@/lib/utils';
import {
  Skill,
  SkillPayload,
  createSkill,
  deleteSkill,
  getSkills,
  updateSkill,
  uploadSkill,
} from '@/services/skillService';

const emptyInstruction =
  '请说明这个 Skill 适合在什么场景下使用、如何使用，以及什么情况下允许调用 scripts。';

function shortRootDir(rootDir: string): string {
  if (!rootDir) return '-';
  const segments = rootDir.split(/[\\/]/).filter(Boolean);
  return segments.slice(-2).join('/') || rootDir;
}

// ---------------------------------------------------------------------------
// zod schema（对齐后端 SkillPayload）
// ---------------------------------------------------------------------------

const skillFormSchema = z.object({
  name: z.string().min(1, '请填写 Skill 名称'),
  slug: z
    .string()
    .regex(/^[a-z0-9-]*$/, 'slug 仅允许小写字母、数字和连字符')
    .optional(),
  description: z.string(),
  enabled: z.boolean(),
  instruction: z.string().min(1, 'SKILL.md 正文不能为空'),
});

type SkillFormValues = z.infer<typeof skillFormSchema>;

const uploadFormSchema = z.object({
  slug: z
    .string()
    .regex(/^[a-z0-9-]*$/, 'slug 仅允许小写字母、数字和连字符'),
});

type UploadFormValues = z.infer<typeof uploadFormSchema>;

// ---------------------------------------------------------------------------
// Skill 编辑弹窗
// ---------------------------------------------------------------------------

function SkillFormDialog({
  open,
  editingSkill,
  onClose,
}: {
  open: boolean;
  editingSkill: Skill | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = editingSkill !== null;

  const form = useForm<SkillFormValues>({
    resolver: zodResolver(skillFormSchema),
    defaultValues: {
      name: '',
      slug: '',
      description: '',
      enabled: true,
      instruction: emptyInstruction,
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({
        name: editingSkill?.name ?? '新 Skill',
        slug: editingSkill?.slug ?? '',
        description: editingSkill?.description ?? '',
        enabled: editingSkill?.enabled ?? true,
        instruction: editingSkill?.instruction ?? emptyInstruction,
      });
    }
  }, [open, editingSkill, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: SkillFormValues) => {
      const payload: SkillPayload = {
        name: values.name.trim(),
        slug: values.slug?.trim() || undefined,
        description: values.description,
        enabled: values.enabled,
        instruction: values.instruction,
      };
      return isEdit && editingSkill
        ? updateSkill(editingSkill.id, payload)
        : createSkill(payload);
    },
    onSuccess: () => {
      toast.success(isEdit ? 'Skill 已保存' : 'Skill 已创建');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'skills'] });
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || 'Skill 保存失败'),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑 Skill' : '新建 Skill'}</DialogTitle>
          <DialogDescription>
            保存后将更新本地 Skill 目录的 SKILL.md 与配置。
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => void saveMutation.mutateAsync(values))}
          className="space-y-4"
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="skill-name">名称</Label>
              <Input id="skill-name" {...form.register('name')} />
              {form.formState.errors.name ? (
                <p className="text-xs font-medium text-rose-600">
                  {form.formState.errors.name.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="skill-slug">Slug（可选）</Label>
              <Input id="skill-slug" placeholder="小写字母 / 数字 / 连字符" {...form.register('slug')} />
              {form.formState.errors.slug ? (
                <p className="text-xs font-medium text-rose-600">
                  {form.formState.errors.slug.message}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="skill-description">描述</Label>
            <Input id="skill-description" {...form.register('description')} />
          </div>

          <label className="flex items-center gap-2.5">
            <Checkbox
              checked={form.watch('enabled')}
              onCheckedChange={(checked) => form.setValue('enabled', checked === true)}
            />
            <span className="text-sm font-medium text-zinc-700">启用该 Skill</span>
          </label>

          <div className="space-y-1.5">
            <Label htmlFor="skill-instruction">SKILL.md 正文</Label>
            <textarea
              id="skill-instruction"
              rows={12}
              {...form.register('instruction')}
              className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5 text-sm font-medium leading-6 text-[var(--foreground)] outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25"
            />
            {form.formState.errors.instruction ? (
              <p className="text-xs font-medium text-rose-600">
                {form.formState.errors.instruction.message}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={saveMutation.isPending}
            >
              取消
            </Button>
            <Button type="submit" disabled={saveMutation.isPending} className="gap-2">
              {saveMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Save size={16} />
              )}
              保存 Skill
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export const SkillManagement = () => {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = React.useState(false);
  const [editingSkill, setEditingSkill] = React.useState<Skill | null>(null);
  const [deletingSkill, setDeletingSkill] = React.useState<Skill | null>(null);
  const [uploadFile, setUploadFile] = React.useState<File | null>(null);

  const skillsQuery = useQuery({
    queryKey: ['admin', 'skills'],
    queryFn: getSkills,
  });
  const skills = skillsQuery.data?.items ?? [];

  const uploadForm = useForm<UploadFormValues>({
    resolver: zodResolver(uploadFormSchema),
    defaultValues: { slug: '' },
  });

  const uploadMutation = useMutation({
    mutationFn: async (values: UploadFormValues) => {
      if (!uploadFile) throw new Error('请先选择 Zip Skill 包');
      return uploadSkill(uploadFile, values.slug || undefined, true);
    },
    onSuccess: (saved) => {
      toast.success('items' in saved ? `成功上传 ${saved.count} 个 Skill` : 'Skill 包上传成功');
      setUploadFile(null);
      uploadForm.reset({ slug: '' });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'skills'] });
    },
    onError: (err: Error) => toast.error(err.message || 'Skill 包上传失败'),
  });

  const deleteMutation = useMutation({
    mutationFn: (skillId: number) => deleteSkill(skillId),
    onSuccess: () => {
      toast.success('Skill 已删除');
      setDeletingSkill(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'skills'] });
    },
    onError: (err: Error) => toast.error(err.message || 'Skill 删除失败'),
  });

  const enabledCount = skills.filter((skill) => skill.enabled).length;
  const pythonSkillCount = skills.filter((skill) => skill.has_python_scripts).length;
  const referenceSkillCount = skills.filter((skill) => skill.has_references).length;

  const columns = React.useMemo<ColumnDef<Skill, unknown>[]>(
    () => [
      {
        id: 'skill',
        header: 'Skill',
        cell: ({ row }) => {
          const skill = row.original;
          return (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-[var(--foreground)]">{skill.name}</p>
              <p className="mt-0.5 truncate text-xs font-semibold tracking-wide text-[var(--muted-foreground)]">
                {skill.slug}
              </p>
              <p className="mt-1 line-clamp-2 max-w-[420px] text-sm font-medium leading-6 text-[var(--muted-foreground)]">
                {skill.description || '暂无描述'}
              </p>
            </div>
          );
        },
      },
      {
        id: 'scripts',
        header: '脚本数',
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm font-semibold text-[var(--foreground)]">
            {row.original.script_paths.length}
          </span>
        ),
      },
      {
        id: 'root_dir',
        header: '目录',
        enableSorting: false,
        cell: ({ row }) => (
          <span className="font-mono text-xs font-medium text-zinc-600">
            {shortRootDir(row.original.root_dir)}
          </span>
        ),
      },
      {
        accessorKey: 'updated_at',
        header: '更新时间',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium text-zinc-600">
            {formatApiDate(String(getValue()))}
          </span>
        ),
      },
      {
        id: 'status',
        header: '状态',
        enableSorting: false,
        cell: ({ row }) => {
          const skill = row.original;
          return (
            <div className="flex flex-wrap gap-1.5">
              <span
                className={cn(
                  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
                  skill.enabled
                    ? 'border-emerald-200/80 bg-emerald-50 text-emerald-700'
                    : 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
                )}
              >
                {skill.enabled ? '启用' : '停用'}
              </span>
              {skill.has_python_scripts ? (
                <span className="inline-flex items-center rounded-full border border-amber-200/80 bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700">
                  Python
                </span>
              ) : null}
              {skill.has_references ? (
                <span className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-100 px-2.5 py-0.5 text-[11px] font-semibold text-zinc-800">
                  refs
                </span>
              ) : null}
            </div>
          );
        },
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const skill = row.original;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setEditingSkill(skill);
                  setFormOpen(true);
                }}
              >
                <FileCode2 size={14} />
                编辑
              </Button>
              <Button
                variant="destructive"
                size="sm"
                className="gap-1.5"
                onClick={() => setDeletingSkill(skill)}
              >
                <Trash2 size={14} />
                删除
              </Button>
            </div>
          );
        },
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="Skill 管理"
        title="本地 Skill 目录"
        actions={
          <>
            <KpiPill label="共" value={skills.length} />
            <KpiPill label="启用" value={enabledCount} />
            <KpiPill label="脚本" value={pythonSkillCount} />
            <KpiPill label="参考" value={referenceSkillCount} />
            <Button
              variant="outline"
              size="sm"
              onClick={() => void skillsQuery.refetch()}
              disabled={skillsQuery.isFetching}
              className="gap-1.5"
            >
              {skillsQuery.isFetching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setEditingSkill(null);
                setFormOpen(true);
              }}
            >
              <Plus size={14} />
              新建
            </Button>
          </>
        }
      />

      {skillsQuery.isError ? (
        <ErrorBanner message={(skillsQuery.error as Error).message || 'Skill 列表加载失败'} />
      ) : null}

      {/* 上传入口 */}
      <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
        <div className="grid grid-cols-1 items-end gap-4 xl:grid-cols-[minmax(0,1fr)_200px_auto]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-700">
              上传入口
            </p>
            <h3 className="mt-1 text-base font-semibold tracking-tight text-[var(--foreground)]">
              上传 Zip Skill 包
            </h3>
            <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
              上传成功后自动写入本地目录并出现在列表中
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="skill-upload-slug">Slug 覆盖（可选）</Label>
            <Input id="skill-upload-slug" placeholder="可选 slug" {...uploadForm.register('slug')} />
            {uploadForm.formState.errors.slug ? (
              <p className="text-xs font-medium text-rose-600">
                {uploadForm.formState.errors.slug.message}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-2.5 sm:flex-row">
            <label className="flex w-full cursor-pointer items-center rounded-md border border-dashed border-zinc-300 bg-[var(--surface-2)] px-3.5 py-2.5 text-sm font-medium text-[var(--muted-foreground)] transition hover:border-zinc-900 hover:text-zinc-700 sm:max-w-[260px]">
              <span className="block truncate">
                {uploadFile ? uploadFile.name : '选择 Zip...'}
              </span>
              <input
                type="file"
                accept=".zip"
                className="hidden"
                onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <Button
              size="sm"
              className="gap-1.5"
              disabled={!uploadFile || uploadMutation.isPending}
              onClick={() => void uploadForm.handleSubmit((v) => uploadMutation.mutate(v))()}
            >
              {uploadMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              上传
            </Button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
        {skillsQuery.isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-14 w-full" />
            ))}
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={skills}
            emptyState={
              <div className="flex flex-col items-center justify-center py-8">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--muted-foreground)] shadow-sm">
                  <FileCode2 size={20} />
                </div>
                <p className="text-sm font-semibold text-zinc-600">还没有 Skill</p>
                <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
                  你可以先创建一个本地 Skill，或者直接上传 Zip Skill 包。
                </p>
              </div>
            }
          />
        )}
      </section>

      <SkillFormDialog
        open={formOpen}
        editingSkill={editingSkill}
        onClose={() => {
          setFormOpen(false);
          setEditingSkill(null);
        }}
      />

      <AlertDialog
        open={deletingSkill !== null}
        onOpenChange={(next) => !next && setDeletingSkill(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除 Skill</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除 Skill「{deletingSkill?.name}」吗？本地目录中的对应文件也将被移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingSkill) deleteMutation.mutate(deletingSkill.id);
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
