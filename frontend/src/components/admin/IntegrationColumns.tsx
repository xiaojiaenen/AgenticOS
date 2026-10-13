/**
 * 集成管理：系统列表与接口列表的 TanStack Table 列定义。
 * 从 IntegrationManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink, Pencil, TestTube, Trash2 } from 'lucide-react';
import { StatusPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { cn } from '@/lib/utils';
import { IntegrationApi, IntegrationCategory, IntegrationSystem } from '@/services/integrationService';
import { authTypeIcon, authTypeLabel, methodBadgeColor } from './integrationHelpers';

export function buildSystemColumns({
  categories,
  onViewSystem,
  onEditSystem,
  onDeleteSystem,
}: {
  categories: IntegrationCategory[];
  onViewSystem: (system: IntegrationSystem) => void;
  onEditSystem: (system: IntegrationSystem) => void;
  onDeleteSystem: (system: IntegrationSystem) => void;
}): ColumnDef<IntegrationSystem, unknown>[] {
  return [
    {
      id: 'name',
      header: '名称',
      cell: ({ row }) => {
        const sys = row.original;
        const Icon = authTypeIcon(sys.auth_type);
        return (
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-zinc-600 shadow-sm">
              <Icon size={18} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-[var(--foreground)]">{sys.name}</p>
              <p className="truncate text-xs font-medium text-[var(--muted-foreground)]">{sys.base_url}</p>
            </div>
          </div>
        );
      },
    },
    {
      id: 'description',
      header: '描述',
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block max-w-[220px] truncate text-sm font-medium text-zinc-600">
          {row.original.description || '-'}
        </span>
      ),
    },
    {
      id: 'category',
      header: '分类',
      enableSorting: false,
      cell: ({ row }) => {
        const cat = categories.find((c) => c.key === row.original.category);
        return (
          <span className="rounded-lg bg-[var(--surface-2)] px-2 py-1 text-xs font-medium text-zinc-600">
            {cat ? `${cat.icon} ${cat.label}` : row.original.category}
          </span>
        );
      },
    },
    {
      id: 'auth',
      header: '鉴权',
      enableSorting: false,
      cell: ({ row }) => (
        <span className="rounded-lg bg-[var(--surface-2)] px-2 py-1 text-xs font-medium text-zinc-600">
          {authTypeLabel(row.original.auth_type)}
        </span>
      ),
    },
    {
      accessorKey: 'api_count',
      header: () => <span className="block text-center">接口</span>,
      cell: ({ getValue }) => (
        <span className="block text-center text-sm font-medium text-zinc-700">{Number(getValue())}</span>
      ),
    },
    {
      id: 'status',
      header: () => <span className="block text-center">状态</span>,
      enableSorting: false,
      cell: ({ row }) => {
        const sys = row.original;
        const label = sys.enabled && sys.published ? '已发布' : sys.enabled ? '未发布' : '已禁用';
        return (
          <span className="block text-center">
            <StatusPill tone={sys.enabled && sys.published ? 'active' : sys.enabled ? 'warning' : 'inactive'}>
              {label}
            </StatusPill>
          </span>
        );
      },
    },
    {
      id: 'actions',
      header: () => <span className="block text-right">操作</span>,
      enableSorting: false,
      cell: ({ row }) => {
        const sys = row.original;
        return (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={(e) => {
                e.stopPropagation();
                onViewSystem(sys);
              }}
              aria-label={`查看 ${sys.name}`}
              title="查看接口"
            >
              <ExternalLink size={15} />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={(e) => {
                e.stopPropagation();
                onEditSystem(sys);
              }}
              aria-label={`编辑 ${sys.name}`}
            >
              <Pencil size={15} />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-rose-500 hover:bg-rose-50"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteSystem(sys);
              }}
              aria-label={`删除 ${sys.name}`}
            >
              <Trash2 size={15} />
            </Button>
          </div>
        );
      },
    },
  ];
}

export function buildApiColumns({
  onTestApi,
  onEditApi,
  onDeleteApi,
}: {
  onTestApi: (api: IntegrationApi) => void;
  onEditApi: (api: IntegrationApi) => void;
  onDeleteApi: (api: IntegrationApi) => void;
}): ColumnDef<IntegrationApi, unknown>[] {
  return [
    {
      id: 'api',
      header: '接口',
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--foreground)]">{row.original.display_name}</p>
          <p className="truncate text-xs font-medium text-[var(--muted-foreground)]">{row.original.name}</p>
        </div>
      ),
    },
    {
      accessorKey: 'method',
      header: '方法',
      cell: ({ getValue }) => (
        <span className={cn('rounded-lg px-2 py-1 text-xs font-semibold', methodBadgeColor(String(getValue())))}>
          {String(getValue())}
        </span>
      ),
    },
    {
      accessorKey: 'path',
      header: '路径',
      cell: ({ getValue }) => (
        <span className="block max-w-[240px] truncate font-mono text-xs text-zinc-600">
          {String(getValue())}
        </span>
      ),
    },
    {
      id: 'params',
      header: () => <span className="block text-center">参数</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block text-center text-sm font-medium text-zinc-700">
          {row.original.params.length}
        </span>
      ),
    },
    {
      id: 'approval',
      header: () => <span className="block text-center">审批</span>,
      enableSorting: false,
      cell: ({ row }) =>
        row.original.requires_approval ? (
          <span className="block text-center">
            <StatusPill tone="warning">需审批</StatusPill>
          </span>
        ) : (
          <span className="block text-center text-xs text-[var(--muted-foreground)]">—</span>
        ),
    },
    {
      id: 'actions',
      header: () => <span className="block text-right">操作</span>,
      enableSorting: false,
      cell: ({ row }) => {
        const api = row.original;
        return (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onTestApi(api)}
              title="测试"
            >
              <TestTube size={15} />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onEditApi(api)}
            >
              <Pencil size={15} />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-rose-500 hover:bg-rose-50"
              onClick={() => onDeleteApi(api)}
            >
              <Trash2 size={15} />
            </Button>
          </div>
        );
      },
    },
  ];
}
