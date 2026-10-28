/**
 * 知识库管理：共享成员面板。
 *
 * private / personal 知识库默认只有创建者可见，这里把库显式分享给其他同事。
 * 角色只有三档：viewer（可读可检索）/ editor（可写、可上传）/ admin（可删库）。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, Share2, Trash2, Users } from 'lucide-react';
import { ErrorBanner } from './shared';
import { Button } from '@/components/shadcn/button';
import {
  getKnowledgeBaseAcl,
  replaceKnowledgeBaseAcl,
  type KBACLRole,
  type KBACLPayloadEntry,
} from '@/services/knowledgeService';
import { toastError } from '../../lib/errors';

const roleLabels: Record<KBACLRole, string> = {
  viewer: '只读',
  editor: '可编辑',
  admin: '可管理',
};

const roleHints: Record<KBACLRole, string> = {
  viewer: '可检索、可阅读 Wiki 页面',
  editor: '可上传文档、触发重建索引',
  admin: '可修改知识库设置、删除知识库',
};

export function KnowledgeACLTab({ kbId, canManage }: { kbId: number; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<KBACLRole>('viewer');

  const aclQuery = useQuery({
    queryKey: ['admin', 'kb-acl', kbId],
    queryFn: () => getKnowledgeBaseAcl(kbId),
  });

  const saveMutation = useMutation({
    mutationFn: (entries: KBACLPayloadEntry[]) => replaceKnowledgeBaseAcl(kbId, entries),
    onSuccess: () => {
      toast.success('共享成员已保存');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kb-acl', kbId] });
    },
    onError: (err: Error) => toast.error(toastError(err, '保存共享成员失败')),
  });

  if (aclQuery.isPending) {
    return (
      <div className="flex items-center justify-center py-16 text-[var(--muted-foreground)]">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        加载中…
      </div>
    );
  }

  if (aclQuery.isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <ErrorBanner message={toastError(aclQuery.error, '共享成员加载失败')} onRetry={() => void aclQuery.refetch()} />
        <Button variant="outline" size="sm" onClick={() => void aclQuery.refetch()}>
          重试
        </Button>
      </div>
    );
  }

  const items = aclQuery.data;
  const toEntries = (next: { principal_id: number; role: KBACLRole }[]): KBACLPayloadEntry[] =>
    next.map((item) => ({ principal_id: item.principal_id, role: item.role }));

  const handleAdd = () => {
    const value = email.trim();
    if (!value) {
      toast.error('请填写同事的登录邮箱');
      return;
    }
    if (items.some((item) => (item.email || '').toLowerCase() === value.toLowerCase())) {
      toast.error('该邮箱已在共享列表中');
      return;
    }
    saveMutation.mutate(
      [...toEntries(items), { principal_email: value, role }],
      { onSuccess: () => setEmail('') },
    );
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
        <div className="mb-1 flex items-center gap-2">
          <Share2 className="h-4 w-4 text-[var(--muted-foreground)]" />
          <h4 className="text-sm font-semibold text-[var(--foreground)]">共享成员</h4>
        </div>
        <p className="text-xs font-medium text-[var(--muted-foreground)]">
          private / personal 知识库默认仅创建者可见。加到这里的人可以直接检索到该库内容；
          创建者与系统管理员无需添加。
        </p>

        {canManage && (
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="同事的登录邮箱"
              className="h-9 flex-1 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--border-primary)]"
            />
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as KBACLRole)}
              className="h-9 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 text-sm text-[var(--foreground)]"
            >
              {(Object.keys(roleLabels) as KBACLRole[]).map((key) => (
                <option key={key} value={key}>
                  {roleLabels[key]}
                </option>
              ))}
            </select>
            <Button size="sm" className="gap-1" onClick={handleAdd} disabled={saveMutation.isPending}>
              <Plus className="h-3.5 w-3.5" />
              添加
            </Button>
          </div>
        )}
        {canManage && (
          <p className="mt-2 text-xs text-[var(--muted-foreground)]">{roleHints[role]}</p>
        )}
      </div>

      {items.length === 0 ? (
        <div className="py-12 text-center text-sm font-medium text-[var(--muted-foreground)]">
          <Users className="mx-auto mb-3 h-10 w-10 opacity-40" />
          还没有共享给任何人
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-[var(--foreground)]">
                  {item.name || item.email || `用户 #${item.principal_id}`}
                </div>
                <div className="truncate text-xs text-[var(--muted-foreground)]">{item.email}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <select
                  value={item.role}
                  disabled={!canManage || saveMutation.isPending}
                  onChange={(event) =>
                    saveMutation.mutate(
                      toEntries(
                        items.map((row) =>
                          row.id === item.id
                            ? { principal_id: row.principal_id, role: event.target.value as KBACLRole }
                            : { principal_id: row.principal_id, role: row.role },
                        ),
                      ),
                    )
                  }
                  className="h-8 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 text-xs text-[var(--foreground)] disabled:opacity-60"
                >
                  {(Object.keys(roleLabels) as KBACLRole[]).map((key) => (
                    <option key={key} value={key}>
                      {roleLabels[key]}
                    </option>
                  ))}
                </select>
                {canManage && (
                  <Button
                    size="xs"
                    variant="ghost"
                    className="gap-1 text-[var(--danger)]"
                    disabled={saveMutation.isPending}
                    onClick={() =>
                      saveMutation.mutate(
                        toEntries(
                          items
                            .filter((row) => row.id !== item.id)
                            .map((row) => ({ principal_id: row.principal_id, role: row.role })),
                        ),
                      )
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    移除
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
