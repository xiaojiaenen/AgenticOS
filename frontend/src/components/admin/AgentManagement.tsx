/**
 * 智能体配置：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Select/Dialog/AlertDialog/Tabs。
 * 后端 API 不变（services/agentProfileService.ts、userService.ts、integrationService.ts）。
 * 页面骨架与状态编排；编辑弹窗拆分至同目录子文件。
 */
import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Bot, Loader2, Plus, RefreshCw, Trash2, Wrench } from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Skeleton } from '@/components/shadcn/skeleton';
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
  AgentProfile,
  deleteAgentProfile,
  getAgentProfiles,
} from '@/services/agentProfileService';
import { listUsers } from '@/services/userService';
import { AgentMode } from '@/services/toolConfigService';
import { listSystems } from '@/services/integrationService';
import { AgentFormDialog } from './AgentFormDialog';
import { modeLabel } from './agentHelpers';

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export const AgentManagement = () => {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = React.useState(false);
  const [editingProfile, setEditingProfile] = React.useState<AgentProfile | null>(null);
  const [deletingProfile, setDeletingProfile] = React.useState<AgentProfile | null>(null);

  const profilesQuery = useQuery({
    queryKey: ['admin', 'agents'],
    queryFn: getAgentProfiles,
  });

  const usersQuery = useQuery({
    queryKey: ['admin', 'users', 'all'],
    queryFn: () => listUsers({ offset: 0, limit: 100 }),
    select: (data) => data.items.filter((user) => user.is_active),
  });

  const systemsQuery = useQuery({
    queryKey: ['admin', 'integrations', 'enabled'],
    queryFn: async () => {
      const response = await listSystems();
      return response.items.filter((s) => s.enabled);
    },
    retry: 0,
  });

  const profiles = profilesQuery.data?.items ?? [];
  const catalog = profilesQuery.data?.catalog ?? [];
  const availableSkills = profilesQuery.data?.available_skills ?? [];
  const availableUsers = usersQuery.data ?? [];
  const externalSystems = systemsQuery.data ?? [];

  const deleteMutation = useMutation({
    mutationFn: (profileId: number) => deleteAgentProfile(profileId),
    onSuccess: () => {
      toast.success('智能体已删除');
      setDeletingProfile(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'agents'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const enabledAgents = profiles.filter((profile) => profile.enabled).length;
  const listedAgents = profiles.filter((profile) => profile.listed).length;
  const totalBindings = profiles.reduce((sum, profile) => sum + profile.skills.length, 0);

  const columns = React.useMemo<ColumnDef<AgentProfile, unknown>[]>(
    () => [
      {
        id: 'agent',
        header: '智能体',
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-semibold text-[var(--foreground)]">{profile.name}</p>
                {profile.is_builtin && (
                  <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                    内置
                  </span>
                )}
              </div>
              <p className="mt-0.5 truncate text-xs font-semibold tracking-wide text-[var(--muted-foreground)]">
                {profile.slug}
              </p>
              <p className="mt-1 line-clamp-2 max-w-[360px] text-sm font-medium leading-6 text-[var(--muted-foreground)]">
                {profile.description || '暂无描述'}
              </p>
            </div>
          );
        },
      },
      {
        accessorKey: 'response_mode',
        header: '模式',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-[var(--foreground)]">
            {modeLabel(getValue() as AgentMode)}
          </span>
        ),
      },
      {
        id: 'tools',
        header: '工具',
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <span className="text-sm font-medium text-zinc-600">
              {profile.tools.filter((tool) => tool.enabled).length} / {profile.tools.length}
            </span>
          );
        },
      },
      {
        id: 'skills',
        header: 'Skill',
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          if (profile.skills.length === 0) {
            return <span className="text-sm font-medium text-[var(--muted-foreground)]">未绑定</span>;
          }
          return (
            <div className="flex flex-wrap gap-1.5">
              {profile.skills.slice(0, 2).map((skill) => (
                <span
                  key={skill.id}
                  className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 py-0.5 text-[11px] font-medium text-zinc-600"
                >
                  {skill.name}
                </span>
              ))}
              {profile.skills.length > 2 && (
                <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                  +{profile.skills.length - 2}
                </span>
              )}
            </div>
          );
        },
      },
      {
        id: 'status',
        header: '状态',
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <div className="flex flex-wrap gap-1.5">
              <span
                className={cn(
                  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
                  profile.enabled
                    ? 'border-emerald-200/80 bg-emerald-50 text-emerald-700'
                    : 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
                )}
              >
                {profile.enabled ? '启用' : '停用'}
              </span>
              <span
                className={cn(
                  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
                  profile.listed
                    ? 'border-amber-200/80 bg-amber-50 text-amber-700'
                    : 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
                )}
              >
                {profile.listed ? '上架' : '未上架'}
              </span>
              <span className="inline-flex items-center rounded-full border border-indigo-200/80 bg-indigo-50 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
                {profile.audience_mode === 'selected'
                  ? `指定用户 ${profile.audience_users.length}`
                  : '全体用户'}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: 'updated_at',
        header: '更新时间',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium text-zinc-600">{formatApiDate(String(getValue()))}</span>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setEditingProfile(profile);
                  setFormOpen(true);
                }}
              >
                <Wrench size={14} />
                编辑
              </Button>
              {!profile.is_builtin && (
                <Button
                  variant="destructive"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => setDeletingProfile(profile)}
                >
                  <Trash2 size={14} />
                  删除
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    [],
  );

  if (profilesQuery.isLoading) {
    return (
      <div className="space-y-4">
        <AdminPageHeader kicker="智能体配置" title="智能体目录" />
        <div className="space-y-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="智能体配置"
        title="智能体目录"
        actions={
          <>
            <KpiPill label="共" value={profiles.length} />
            <KpiPill label="已启用" value={enabledAgents} />
            <KpiPill label="已上架" value={listedAgents} />
            <KpiPill label="绑定" value={totalBindings} />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void profilesQuery.refetch()}
              disabled={profilesQuery.isFetching}
            >
              {profilesQuery.isFetching ? (
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
                setEditingProfile(null);
                setFormOpen(true);
              }}
            >
              <Plus size={14} />
              新建
            </Button>
          </>
        }
      />

      {profilesQuery.isError ? (
        <ErrorBanner message={(profilesQuery.error as Error).message || '智能体配置加载失败'} />
      ) : null}

      <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
        <DataTable
          columns={columns}
          data={profiles}
          emptyState={
            <div className="flex flex-col items-center justify-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--muted-foreground)] shadow-sm">
                <Bot size={20} />
              </div>
              <p className="text-sm font-semibold text-zinc-600">还没有智能体配置</p>
              <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">先创建一个智能体，再绑定工具和 Skill</p>
            </div>
          }
        />
      </section>

      <AgentFormDialog
        open={formOpen}
        editingProfile={editingProfile}
        catalog={catalog}
        availableSkills={availableSkills}
        availableUsers={availableUsers}
        externalSystems={externalSystems}
        onClose={() => {
          setFormOpen(false);
          setEditingProfile(null);
        }}
      />

      <AlertDialog
        open={deletingProfile !== null}
        onOpenChange={(next) => !next && setDeletingProfile(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除智能体</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除智能体「{deletingProfile?.name}」吗？删除后用户将无法继续使用该智能体。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingProfile) deleteMutation.mutate(deletingProfile.id);
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
