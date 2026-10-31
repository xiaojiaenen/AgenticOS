/**
 * 智能体「发布为应用 + Prompt 版本历史」面板（AgentFormDialog 的第 5 个 Tab）。
 *
 * 发布：生成不可猜测 slug → 公开聊天页 /app/{slug} + 嵌入 widget.js；
 * 版本：保存时后端/前端把当前配置快照存入 agent_profile_versions，
 * 可随时回滚（回滚会先给当前配置存快照，历史不被覆盖）。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Copy, Globe, History, Loader2, RotateCcw, Unplug } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../shadcn/button';
import { Input } from '../shadcn/input';
import { Label } from '../shadcn/label';
import { toastError } from '@/lib/errors';
import {
  getPublishStatus,
  listProfileVersions,
  publishProfile,
  restoreProfileVersion,
  saveProfileVersion,
  unpublishProfile,
} from '@/services/llmopsService';

export const AgentPublishVersionPanel = ({ profileId }: { profileId: number }) => {
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ['llmops', 'publish', profileId],
    queryFn: () => getPublishStatus(profileId),
  });
  const versionsQuery = useQuery({
    queryKey: ['llmops', 'versions', profileId],
    queryFn: () => listProfileVersions(profileId),
  });

  const publishMutation = useMutation({
    mutationFn: (payload: { title: string; welcome: string; access_code: string }) =>
      publishProfile(profileId, payload),
    onSuccess: (data) => {
      toast.success(`已发布：${data.chat_url}`);
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'publish', profileId] });
    },
    onError: (err: Error) => toast.error(toastError(err, '发布失败')),
  });

  const unpublishMutation = useMutation({
    mutationFn: () => unpublishProfile(profileId),
    onSuccess: () => {
      toast.success('已下线');
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'publish', profileId] });
    },
    onError: (err: Error) => toast.error(toastError(err, '下线失败')),
  });

  const saveVersionMutation = useMutation({
    mutationFn: () => saveProfileVersion(profileId, '手动快照'),
    onSuccess: (data) => {
      toast.success(`已保存版本 v${data.version}`);
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'versions', profileId] });
    },
    onError: (err: Error) => toast.error(toastError(err, '保存版本失败')),
  });

  const restoreMutation = useMutation({
    mutationFn: (version: number) => restoreProfileVersion(profileId, version),
    onSuccess: () => {
      toast.success('已回滚（回滚前配置已另存快照），重新打开编辑器可看到恢复的内容');
      void queryClient.invalidateQueries({ queryKey: ['llmops', 'versions', profileId] });
    },
    onError: (err: Error) => toast.error(toastError(err, '回滚失败')),
  });

  const copy = (text: string, label: string) => {
    void navigator.clipboard.writeText(text).then(
      () => toast.success(`${label}已复制`),
      () => toast.error('复制失败'),
    );
  };

  if (statusQuery.isLoading || versionsQuery.isLoading) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="animate-spin" /></div>;
  }

  const status = statusQuery.data;
  const versions = versionsQuery.data?.items ?? [];
  const chatUrl = status?.chat_url ? `${window.location.origin}${status.chat_url}` : null;
  const widgetCode = status?.chat_url
    ? `<script src="${window.location.origin}/api/v1/public/agents/${status.slug}/widget.js"></script>`
    : null;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* 发布为应用 */}
      <div className="space-y-3 rounded-lg border border-slate-200/80 bg-[var(--surface-1)] p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold">
            <Globe size={15} /> 发布为独立应用
          </h3>
          {status?.published ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
              <CheckCircle2 size={12} /> 已发布
            </span>
          ) : (
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--muted-foreground)]">
              未发布
            </span>
          )}
        </div>
        <PublishForm
          key={status?.published ? `pub-${status.slug}` : 'unpub'}
          initial={status}
          onSubmit={(values) => publishMutation.mutate(values)}
          submitting={publishMutation.isPending}
        />
        {status?.published && chatUrl && (
          <div className="space-y-2 rounded-md bg-[var(--surface-2)] p-3">
            <div className="flex items-center gap-2">
              <Input readOnly className="h-8 flex-1 bg-[var(--surface-1)] text-xs" value={chatUrl} />
              <Button type="button" size="sm" variant="outline" className="gap-1" onClick={() => copy(chatUrl, '链接')}>
                <Copy size={13} /> 复制链接
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Input readOnly className="h-8 flex-1 bg-[var(--surface-1)] font-mono text-xs" value={widgetCode ?? ''} />
              <Button type="button" size="sm" variant="outline" className="gap-1" onClick={() => copy(widgetCode ?? '', '嵌入代码')}>
                <Copy size={13} /> 复制嵌入代码
              </Button>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="w-full gap-1 text-rose-600"
              disabled={unpublishMutation.isPending}
              onClick={() => {
                if (window.confirm('下线后公开链接立即失效，确定下线？')) unpublishMutation.mutate();
              }}
            >
              <Unplug size={13} /> 下线应用
            </Button>
          </div>
        )}
      </div>

      {/* 版本历史 */}
      <div className="rounded-lg border border-slate-200/80 bg-[var(--surface-1)] p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold">
            <History size={15} /> Prompt 版本历史
          </h3>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1"
            disabled={saveVersionMutation.isPending}
            onClick={() => saveVersionMutation.mutate()}
          >
            {saveVersionMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : null}
            保存当前为版本
          </Button>
        </div>
        {versions.length === 0 ? (
          <div className="rounded-md bg-[var(--surface-2)] p-4 text-center text-sm text-[var(--muted-foreground)]">
            还没有版本快照 —— 改提示词前先存一版，改坏了随时回滚
          </div>
        ) : (
          <div className="max-h-72 space-y-1.5 overflow-y-auto">
            {versions.map((v) => (
              <div key={v.id} className="flex items-center gap-2 rounded-md bg-[var(--surface-2)] px-3 py-2">
                <span className="text-sm font-semibold">v{v.version}</span>
                <span className="truncate text-xs text-[var(--muted-foreground)]">{v.note || '—'}</span>
                <span className="ml-auto shrink-0 text-xs text-[var(--muted-foreground)]">
                  {v.created_at ? new Date(v.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={restoreMutation.isPending}
                  onClick={() => {
                    if (window.confirm(`回滚到 v${v.version}？当前配置会先自动存为快照。`)) {
                      restoreMutation.mutate(v.version);
                    }
                  }}
                >
                  <RotateCcw size={12} /> 回滚
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const PublishForm = ({
  initial,
  onSubmit,
  submitting,
}: {
  initial?: { published: boolean; config: { title: string; welcome: string; has_access_code: boolean } };
  onSubmit: (values: { title: string; welcome: string; access_code: string }) => void;
  submitting: boolean;
}) => {
  const [title, setTitle] = useState(initial?.config.title ?? '');
  const [welcome, setWelcome] = useState(initial?.config.welcome ?? '');
  const [accessCode, setAccessCode] = useState('');

  return (
    <div className="space-y-2.5">
      <div className="space-y-1.5">
        <Label className="text-xs">应用标题</Label>
        <Input className="h-8" placeholder="默认用智能体名称" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">欢迎语</Label>
        <Input
          className="h-8"
          placeholder="访客打开页面看到的第一句话"
          value={welcome}
          onChange={(e) => setWelcome(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">访问码（可选，留空 = 任何人可访问）</Label>
        <Input
          className="h-8"
          type="password"
          placeholder={initial?.config.has_access_code ? '已设置（输入新值可更换）' : '设置后访客需输入访问码'}
          value={accessCode}
          onChange={(e) => setAccessCode(e.target.value)}
        />
      </div>
      <Button type="button" size="sm" className="w-full gap-1" disabled={submitting} onClick={() => onSubmit({ title, welcome, access_code: accessCode })}>
        {submitting ? <Loader2 size={13} className="animate-spin" /> : <Globe size={13} />}
        {initial?.published ? '更新发布配置' : '立即发布'}
      </Button>
    </div>
  );
};

export default AgentPublishVersionPanel;
