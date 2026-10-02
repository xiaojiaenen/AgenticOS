/**
 * 集成管理：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Select/Dialog/AlertDialog/Checkbox。
 * 功能：第三方系统 CRUD、接口 CRUD、API 测试、OpenAPI 导入。
 * 后端 API 不变（services/integrationService.ts）。
 * 页面骨架与状态编排；弹窗 / 抽屉 / 列定义拆分至同目录子文件。
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  ChevronLeft,
  ExternalLink,
  Loader2,
  Plug,
  Plus,
  Upload,
} from 'lucide-react';
import { DataTable } from './data-table';
import { McpManagementPanel } from './McpManagementPanel';
import { AdminPageHeader, ErrorBanner } from './shared';
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
import {
  IntegrationApi,
  IntegrationSystem,
  deleteApi,
  deleteSystem,
  listApis,
  listCategories,
  listSystems,
  previewOpenApiImport,
  confirmOpenApiImport,
  testApi,
  type OpenApiPreview,
} from '@/services/integrationService';
import { SystemModal } from './IntegrationSystemModal';
import { ApiModal } from './IntegrationApiModal';
import { TestDrawer, type TestState } from './IntegrationTestDrawer';
import { OpenApiImportDialog } from './IntegrationOpenApiImportDialog';
import { buildApiColumns, buildSystemColumns } from './IntegrationColumns';

export const IntegrationManagement = () => {
  const queryClient = useQueryClient();

  const [selectedSystem, setSelectedSystem] = React.useState<IntegrationSystem | null>(null);
  const [systemModalOpen, setSystemModalOpen] = React.useState(false);
  const [editingSystem, setEditingSystem] = React.useState<IntegrationSystem | null>(null);
  const [apiModalOpen, setApiModalOpen] = React.useState(false);
  const [editingApi, setEditingApi] = React.useState<IntegrationApi | null>(null);
  const [showMcp, setShowMcp] = React.useState(false);
  const [deletingSystem, setDeletingSystem] = React.useState<IntegrationSystem | null>(null);
  const [deletingApi, setDeletingApi] = React.useState<IntegrationApi | null>(null);
  const [testState, setTestState] = React.useState<TestState | null>(null);
  const [openApiModal, setOpenApiModal] = React.useState(false);
  const [openApiInput, setOpenApiInput] = React.useState('');
  const [openApiPreview, setOpenApiPreview] = React.useState<OpenApiPreview | null>(null);
  const [activeCategory, setActiveCategory] = React.useState<string>('all');

  const systemsQuery = useQuery({
    queryKey: ['admin', 'integrations'],
    queryFn: listSystems,
  });
  const systems = systemsQuery.data?.items ?? [];

  const categoriesQuery = useQuery({
    queryKey: ['admin', 'integration-categories'],
    queryFn: listCategories,
    retry: 0,
  });
  const categories = categoriesQuery.data?.items ?? [];

  const apisQuery = useQuery({
    queryKey: ['admin', 'integrations', selectedSystem?.id, 'apis'],
    queryFn: () => listApis(selectedSystem!.id),
    enabled: selectedSystem !== null,
  });
  const apis = apisQuery.data?.items ?? [];

  const saveSystemMutation = useMutation({
    mutationFn: (payload: { system: IntegrationSystem }) => deleteSystem(payload.system.id),
    onSuccess: () => {
      toast.success('集成已删除');
      setDeletingSystem(null);
      if (selectedSystem) {
        setSelectedSystem(null);
      }
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const deleteApiMutation = useMutation({
    mutationFn: (api: IntegrationApi) => {
      if (!selectedSystem) throw new Error('未指定集成');
      return deleteApi(selectedSystem.id, api.id);
    },
    onSuccess: () => {
      toast.success('接口已删除');
      setDeletingApi(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const testMutation = useMutation({
    mutationFn: (api: IntegrationApi) => {
      if (!selectedSystem) throw new Error('未指定集成');
      const params: Record<string, string> = {};
      api.params.forEach((p) => {
        params[p.name] = p.default_value || '';
      });
      setTestState({ apiId: api.id, params, result: null, loading: true });
      return testApi(selectedSystem.id, api.id, params);
    },
    onSuccess: (result) => {
      setTestState((prev) => (prev ? { ...prev, result, loading: false } : null));
    },
    onError: (err: Error) => {
      setTestState((prev) =>
        prev
          ? {
              ...prev,
              result: { success: false, status_code: 0, body: err.message, elapsed_ms: 0 },
              loading: false,
            }
          : null,
      );
    },
  });

  const previewMutation = useMutation({
    mutationFn: (input: string) => {
      const isUrl = input.trim().startsWith('http');
      return previewOpenApiImport(isUrl ? undefined : input.trim(), isUrl ? input.trim() : undefined);
    },
    onSuccess: (preview) => setOpenApiPreview(preview),
    onError: (err: Error) => toast.error(err.message || '解析失败'),
  });

  const confirmImportMutation = useMutation({
    mutationFn: (preview: OpenApiPreview) => confirmOpenApiImport(preview),
    onSuccess: () => {
      toast.success('导入成功');
      setOpenApiModal(false);
      setOpenApiPreview(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
    },
    onError: (err: Error) => toast.error(err.message || '导入失败'),
  });

  const enabledCount = systems.filter((s) => s.enabled).length;
  const filteredSystems =
    activeCategory === 'all'
      ? systems
      : systems.filter((s) => s.category === activeCategory);

  // ── 系统列表表格 ──
  const systemColumns = React.useMemo(
    () =>
      buildSystemColumns({
        categories,
        onViewSystem: setSelectedSystem,
        onEditSystem: (sys) => {
          setEditingSystem(sys);
          setSystemModalOpen(true);
        },
        onDeleteSystem: setDeletingSystem,
      }),
    [categories],
  );

  // ── 接口列表表格 ──
  const apiColumns = React.useMemo(
    () =>
      buildApiColumns({
        onTestApi: (api) => testMutation.mutate(api),
        onEditApi: (api) => {
          setEditingApi(api);
          setApiModalOpen(true);
        },
        onDeleteApi: setDeletingApi,
      }),
    [testMutation],
  );

  if (!selectedSystem) {
    return (
      <div className="space-y-5">
        <AdminPageHeader
          kicker="集成管理"
          title="第三方集成"
          description={`${enabledCount} 个已启用 / ${systems.length} 个总计`}
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setOpenApiModal(true);
                  setOpenApiInput('');
                  setOpenApiPreview(null);
                }}
              >
                <Upload size={14} />
                导入 OpenAPI
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setShowMcp(true)}
              >
                <Plug size={14} />
                MCP 服务器
              </Button>
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setEditingSystem(null);
                  setSystemModalOpen(true);
                }}
              >
                <Plus size={14} />
                新增集成
              </Button>
            </>
          }
        />

        {systemsQuery.isError ? (
          <ErrorBanner message={(systemsQuery.error as Error).message || '加载失败'} />
        ) : null}

        {/* 分类 Tab */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant={activeCategory === 'all' ? 'default' : 'secondary'}
            size="xs"
            onClick={() => setActiveCategory('all')}
          >
            全部 ({systems.length})
          </Button>
          {categories
            .filter((c) => systems.some((s) => s.category === c.key))
            .map((c) => (
              <Button
                key={c.key}
                variant={activeCategory === c.key ? 'default' : 'secondary'}
                size="xs"
                onClick={() => setActiveCategory(c.key)}
              >
                {c.icon} {c.label} ({systems.filter((s) => s.category === c.key).length})
              </Button>
            ))}
        </div>

        <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
          {systemsQuery.isLoading ? (
            <div className="space-y-3 p-5">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <DataTable
              columns={systemColumns}
              data={filteredSystems}
              emptyState={
                <div className="flex flex-col items-center justify-center py-8">
                  <Plug size={32} className="mb-3 text-zinc-300" />
                  <p className="text-sm font-semibold text-zinc-600">暂无集成</p>
                  <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
                    点击「新增集成」创建第一个第三方系统连接
                  </p>
                </div>
              }
            />
          )}
        </section>

        <OpenApiImportDialog
          open={openApiModal}
          input={openApiInput}
          preview={openApiPreview}
          previewPending={previewMutation.isPending}
          confirmPending={confirmImportMutation.isPending}
          onOpenChange={setOpenApiModal}
          onInputChange={setOpenApiInput}
          onPreview={() => previewMutation.mutate(openApiInput)}
          onConfirm={() => openApiPreview && confirmImportMutation.mutate(openApiPreview)}
        />

        <SystemModal
          open={systemModalOpen}
          editingSystem={editingSystem}
          onClose={() => {
            setSystemModalOpen(false);
            setEditingSystem(null);
          }}
        />

        <AlertDialog
          open={deletingSystem !== null}
          onOpenChange={(next) => !next && setDeletingSystem(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>删除集成</AlertDialogTitle>
              <AlertDialogDescription>
                确定删除集成「{deletingSystem?.name}」？该操作不可撤销。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={saveSystemMutation.isPending}>取消</AlertDialogCancel>
              <AlertDialogAction
                className="bg-rose-600 text-white hover:bg-rose-600/90"
                disabled={saveSystemMutation.isPending}
                onClick={(event) => {
                  event.preventDefault();
                  if (deletingSystem) saveSystemMutation.mutate({ system: deletingSystem });
                }}
              >
                {saveSystemMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
                确认删除
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="集成详情"
        title={selectedSystem.name}
        description={selectedSystem.description || selectedSystem.base_url}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setSelectedSystem(null)}
            >
              <ChevronLeft size={14} />
              返回列表
            </Button>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setEditingApi(null);
                setApiModalOpen(true);
              }}
            >
              <Plus size={14} />
              新增接口
            </Button>
          </>
        }
      />

      {showMcp ? (
        <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
              MCP 服务器
            </h3>
            <Button variant="ghost" size="sm" onClick={() => setShowMcp(false)}>
              关闭
            </Button>
          </div>
          <McpManagementPanel />
        </section>
      ) : null}

      {apisQuery.isError ? (
        <ErrorBanner message={(apisQuery.error as Error).message || '加载接口失败'} />
      ) : null}

      <section className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
        {apisQuery.isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : (
          <DataTable
            columns={apiColumns}
            data={apis}
            emptyState={
              <div className="flex flex-col items-center justify-center py-8">
                <ExternalLink size={32} className="mb-3 text-zinc-300" />
                <p className="text-sm font-semibold text-zinc-600">暂无接口</p>
                <p className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
                  为 {selectedSystem.name} 定义可用的 API 接口
                </p>
              </div>
            }
          />
        )}
      </section>

      {testState && (
        <TestDrawer
          state={testState}
          api={apis.find((a) => a.id === testState.apiId)}
          onClose={() => setTestState(null)}
          onParamChange={(name, value) =>
            setTestState((prev) => (prev ? { ...prev, params: { ...prev.params, [name]: value } } : null))
          }
          onRun={() => {
            const api = apis.find((a) => a.id === testState.apiId);
            if (api) testMutation.mutate(api);
          }}
        />
      )}

      <ApiModal
        open={apiModalOpen}
        systemId={selectedSystem.id}
        editingApi={editingApi}
        onClose={() => {
          setApiModalOpen(false);
          setEditingApi(null);
        }}
      />

      <AlertDialog open={deletingApi !== null} onOpenChange={(next) => !next && setDeletingApi(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除接口</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除接口「{deletingApi?.display_name}」？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteApiMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteApiMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingApi) deleteApiMutation.mutate(deletingApi);
              }}
            >
              {deleteApiMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
