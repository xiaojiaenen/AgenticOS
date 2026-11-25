/**
 * 网站应用化管理面板（docs/research/网站应用化设计.md 步骤 1+2 的前端承载）。
 *
 * 之前后端 16 个端点全齐但无 UI——管理员只能裸调 API。本面板承载完整工作流：
 *
 *   创建应用（secret 仅本次返回） → AI 生成 manifest 草稿（业务描述）→
 *   编辑 manifest → 提交（自动生成 plan）→ 审批（逐项收紧 / 全批 / 拒绝）→
 *   生效版本查看
 *
 * 面向「应用开发者」的接入说明（SDK 用法）内嵌在详情抽屉，管理员看完即可
 * 转发给建站用户。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check, Copy, FileCode, Loader2, Pencil, Plus, RefreshCw, ShieldAlert, Sparkles, X,
} from 'lucide-react';
import { apiFetch } from '../../services/apiClient';
import { toast } from 'sonner';
import { toastError } from '../../lib/errors';

type AppItem = {
  id: string;
  name: string;
  slug: string;
  status: string;
  owner_user_id: number | null;
  has_manifest: boolean;
  has_pending_manifest: boolean;
  created_at: string | null;
  updated_at: string | null;
};

type PlanItem = {
  op: string; // ~ + = !
  path: string;
  detail: string;
  risk?: boolean;
  old?: unknown;
  new?: unknown;
};

const OP_LABEL: Record<string, { label: string; cls: string }> = {
  '~': { label: '修改', cls: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300' },
  '+': { label: '新增', cls: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300' },
  '=': { label: '不变', cls: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-500/10 dark:text-zinc-400' },
  '!': { label: '风险', cls: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300' },
};

const statusLabel = (s: string): string =>
  ({ draft: '草稿', pending: '待审批', deployed: '已生效', rejected: '已拒绝', cancelled: '已取消' }[s] ?? s);

const timeOf = (v: string | null): string =>
  v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '—';

/** 应用终端用户接入说明（管理员复制给建站用户） */
function sdkUsageMarkdown(app: AppItem): string {
  return [
    `## 在生成的网站里使用数据（${app.name}）`,
    '',
    '页面里引入一行脚本：',
    '',
    '```html',
    `<script src="/sdk/agenticos.js"></script>`,
    '```',
    '',
    '登录（终端用户，与平台账号无关）：',
    '',
    '```js',
    `await AgenticOS.auth.login('${app.slug}', { email, password });`,
    '```',
    '',
    '读写数据（权限由平台判，前端不用写 if）：',
    '',
    '```js',
    `const list = await AgenticOS.data.feedback.list({ env: 'prod' });`,
    `await AgenticOS.data.feedback.create({ title: '…' });`,
    '```',
    '',
    '> 数据端点：`/api/v1/apps/' + app.slug + '/data/<model>`；',
    '> 终端用户注册需 manifest `auth.allowSignup: true`。',
  ].join('\n');
}

export const AppManagement: React.FC = () => {
  const [apps, setApps] = useState<AppItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 新建应用（showCreate = 对话框开关；creating = 请求进行中，两者必须分离——
  // 否则对话框一打开按钮就永久 disabled）
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSlug, setNewSlug] = useState('');
  const [createdSecret, setCreatedSecret] = useState<{ name: string; slug: string; secret: string } | null>(null);

  // manifest 编辑器（新建后或对已有应用提交新版本）
  const [editing, setEditing] = useState<{ app: AppItem; manifestText: string; brief: string; aiLoading: boolean } | null>(null);

  // plan 审批
  const [reviewing, setReviewing] = useState<{ app: AppItem; plan: PlanItem[] } | null>(null);
  const [approvedPaths, setApprovedPaths] = useState<Set<string> | null>(null); // null = 全部批准
  const [deciding, setDeciding] = useState(false);

  // 详情（SDK 用法 + 生效 manifest）
  const [detail, setDetail] = useState<{ app: AppItem; manifest: Record<string, unknown> | null } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await apiFetch<{ items: AppItem[]; count: number }>('/api/v1/admin/apps');
      setApps(body.items);
    } catch (err) {
      setError(toastError(err, '加载应用列表失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const createApp = useCallback(async () => {
    if (!newName.trim() || !newSlug.trim()) {
      toast.error('名称与 slug 必填（slug：小写字母/数字/连字符）');
      return;
    }
    setCreating(true);
    try {
      const body = await apiFetch<{ app: AppItem; secret_key: string }>('/api/v1/admin/apps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim(), slug: newSlug.trim() }),
      });
      // secret 明文仅本次返回——展示复制区，关闭后无法再取
      setCreatedSecret({ name: body.app.name, slug: body.app.slug, secret: body.secret_key });
      setNewName('');
      setNewSlug('');
      setCreating(false);
      setShowCreate(false);
      void load();
    } catch (err) {
      toast.error(toastError(err, '创建应用失败'));
      setCreating(false);
    }
  }, [newName, newSlug, load]);

  const openEditor = useCallback((app: AppItem) => {
    setEditing({ app, manifestText: '', brief: '', aiLoading: false });
  }, []);

  const aiDraft = useCallback(async () => {
    if (!editing || !editing.brief.trim()) {
      toast.error('先写一句业务描述（要做什么、谁能看、谁能改）');
      return;
    }
    setEditing((prev) => (prev ? { ...prev, aiLoading: true } : prev));
    try {
      const body = await apiFetch<{ requirements_md: string; manifest: Record<string, unknown> }>(
        '/api/v1/admin/apps/manifest/draft',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ brief: editing.brief.trim() }),
        },
      );
      setEditing((prev) =>
        prev
          ? {
              ...prev,
              manifestText: JSON.stringify(body.manifest, null, 2),
              aiLoading: false,
            }
          : prev,
      );
      toast.success('AI 草稿已生成（仍需提交 → 审批生效）');
    } catch (err) {
      toast.error(toastError(err, 'AI 生成失败'));
      setEditing((prev) => (prev ? { ...prev, aiLoading: false } : prev));
    }
  }, [editing]);

  const submitManifest = useCallback(
    async (app: AppItem, manifestText: string) => {
      let manifest: unknown;
      try {
        manifest = JSON.parse(manifestText);
      } catch {
        toast.error('manifest 不是合法 JSON');
        return;
      }
      try {
        await apiFetch(`/api/v1/admin/apps/${app.id}/manifest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ manifest }),
        });
        toast.success('已提交，生成变更计划待审批');
        setEditing(null);
        void load();
      } catch (err) {
        toast.error(toastError(err, '提交失败'));
      }
    },
    [load],
  );

  const openReview = useCallback(
    async (app: AppItem) => {
      try {
        const body = await apiFetch<{ plan: PlanItem[] }>(`/api/v1/admin/apps/${app.id}/plan`);
        setReviewing({ app, plan: body.plan });
        setApprovedPaths(null);
      } catch (err) {
        toast.error(toastError(err, '读取变更计划失败'));
      }
    },
    [],
  );

  const decide = useCallback(
    async (app: AppItem, approve: boolean) => {
      setDeciding(true);
      try {
        if (approve) {
          await apiFetch(`/api/v1/admin/apps/${app.id}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(
              approvedPaths ? { approved_paths: [...approvedPaths] } : {},
            ),
          });
          toast.success('已批准并生效');
        } else {
          await apiFetch(`/api/v1/admin/apps/${app.id}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: '管理员拒绝' }),
          });
          toast.success('已拒绝');
        }
        setReviewing(null);
        void load();
      } catch (err) {
        toast.error(toastError(err, '审批操作失败'));
      } finally {
        setDeciding(false);
      }
    },
    [approvedPaths, load],
  );

  const openDetail = useCallback(async (app: AppItem) => {
    setDetail({ app, manifest: null });
    setDetailLoading(true);
    try {
      // 生效 manifest 从 plan 接口旁路拿不到（它只回候选版），直接复用 list 里的
      // has_manifest 标记 + 详情接口（后端无单独生效 manifest 端点 → 用 plan 404 兜底）
      const body = await apiFetch<{ manifest?: Record<string, unknown> } | null>(
        `/api/v1/admin/apps/${app.id}/plan`,
      ).catch(() => null);
      setDetail({ app, manifest: body?.manifest ?? null });
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const cardBase =
    'rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm';
  const chipBase = 'rounded-full px-2.5 py-1 text-[11px] font-semibold';

  const riskCount = useMemo(
    () => (reviewing ? reviewing.plan.filter((p) => p.risk || p.op === '!').length : 0),
    [reviewing],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[var(--foreground)]">网站应用</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            生成的网站升级为「有登录、有数据、有权限」的应用——manifest 声明 + plan 审批
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)]"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3.5 py-2 text-sm font-semibold text-[var(--primary-foreground)] transition-colors hover:bg-[var(--primary)]/90 active:scale-[0.98]"
          >
            <Plus size={15} /> 新建应用
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-300/60 bg-rose-50/80 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
          {error}
        </div>
      )}

      {loading && !apps && (
        <div className="h-40 animate-pulse rounded-xl bg-[var(--surface-2)]" aria-busy="true" />
      )}

      {/* 应用列表 */}
      {apps && (
        <div className={cardBase}>
          {apps.length === 0 ? (
            <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 text-sm text-[var(--muted-foreground)]">
              <FileCode size={32} className="opacity-40" />
              <p>还没有应用</p>
              <p className="max-w-md text-center text-xs opacity-70">
                「新建应用」生成 slug 与 secret，之后用 AI 从业务描述生成 manifest，
                经 plan 审批后即可让生成的网站读写数据
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-[var(--border-subtle)]/60">
              {apps.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 font-medium text-[var(--foreground)]">
                      {a.name}
                      <span className="font-mono text-xs text-[var(--muted-foreground)]">{a.slug}</span>
                      {a.has_pending_manifest && (
                        <span className={`${chipBase} bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300`}>
                          待审批
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                      状态 {statusLabel(a.status)} · 创建于 {timeOf(a.created_at)}
                    </p>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    {a.has_pending_manifest && (
                      <button
                        type="button"
                        onClick={() => void openReview(a)}
                        className="inline-flex items-center gap-1 rounded-full bg-amber-500 px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-amber-600 active:scale-95"
                      >
                        <ShieldAlert size={12} /> 审批变更
                      </button>
                    )}
                    {a.has_manifest && (
                      <button
                        type="button"
                        onClick={() => void openDetail(a)}
                        className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)] active:scale-95"
                      >
                        <FileCode size={12} /> 生效版本
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => openEditor(a)}
                      className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-2)] active:scale-95"
                    >
                      <Pencil size={12} /> {a.has_manifest ? '提交新版本' : '编写 manifest'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* 新建应用 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="新建应用" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-3 text-base font-bold text-[var(--foreground)]">新建应用</h2>
            <label className="block text-xs font-medium text-[var(--muted-foreground)]">名称</label>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="例如：客户反馈看板"
              className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-3 py-2 text-sm text-[var(--foreground)]"
            />
            <label className="mt-3 block text-xs font-medium text-[var(--muted-foreground)]">slug（数据端点路径标识）</label>
            <input
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value.toLowerCase())}
              placeholder="feedback-board"
              className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-3 py-2 font-mono text-sm text-[var(--foreground)]"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="rounded-lg px-3 py-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                取消
              </button>
              <button
                type="button"
                onClick={() => void createApp()}
                disabled={creating}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-foreground)] active:scale-[0.98] disabled:opacity-60"
              >
                {creating && <Loader2 size={14} className="animate-spin" />} 创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* secret 仅本次返回 */}
      {createdSecret && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="应用密钥">
          <div className="w-full max-w-lg rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-xl">
            <h2 className="mb-1 text-base font-bold text-[var(--foreground)]">「{createdSecret.name}」已创建</h2>
            <p className="mb-3 flex items-center gap-1 text-xs text-rose-600 dark:text-rose-400">
              <ShieldAlert size={13} /> secret 仅本次显示，关闭后无法再取（请立即复制保存）
            </p>
            <div className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2.5">
              <code className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--foreground)]">{createdSecret.secret}</code>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(createdSecret.secret);
                  toast.success('已复制');
                }}
                className="flex-shrink-0 rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--surface-3)] hover:text-[var(--foreground)]"
                aria-label="复制 secret"
              >
                <Copy size={14} />
              </button>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => {
                  setCreatedSecret(null);
                  const app = apps?.find((x) => x.slug === createdSecret.slug);
                  if (app) openEditor(app);
                }}
                className="rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-foreground)] active:scale-[0.98]"
              >
                已保存，继续编写 manifest
              </button>
            </div>
          </div>
        </div>
      )}

      {/* manifest 编辑器（AI 草稿 + 手工微调） */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="编辑 manifest" onClick={() => setEditing(null)}>
          <div className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-base font-bold text-[var(--foreground)]">
              {editing.app.has_manifest ? '提交新版本 manifest' : '编写 manifest'} · {editing.app.name}
            </h2>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              建议流程：写一句业务描述 → AI 起草 → 手工微调 → 提交（生成 plan 待审批）
            </p>

            <label className="mt-3 block text-xs font-medium text-[var(--muted-foreground)]">
              业务描述（AI 起草用：「收集客户反馈，作者能改自己的，管理员能删」）
            </label>
            <div className="mt-1 flex gap-2">
              <input
                value={editing.brief}
                onChange={(e) => setEditing((prev) => (prev ? { ...prev, brief: e.target.value } : prev))}
                placeholder="一句话说清这个应用是给谁、干什么用的…"
                className="min-w-0 flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-3 py-2 text-sm text-[var(--foreground)]"
              />
              <button
                type="button"
                onClick={() => void aiDraft()}
                disabled={editing.aiLoading}
                className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3.5 py-2 text-sm font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-3)] active:scale-[0.98] disabled:opacity-60"
              >
                {editing.aiLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {editing.aiLoading ? '生成中…' : 'AI 起草'}
              </button>
            </div>

            <label className="mt-3 block text-xs font-medium text-[var(--muted-foreground)]">manifest JSON</label>
            <textarea
              value={editing.manifestText}
              onChange={(e) => setEditing((prev) => (prev ? { ...prev, manifestText: e.target.value } : prev))}
              rows={16}
              spellCheck={false}
              placeholder='点击「AI 起草」从业务描述生成，或直接粘贴 manifest…'
              className="mt-1 w-full flex-1 resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] px-3 py-2.5 font-mono text-xs leading-relaxed text-[var(--foreground)]"
              aria-label="manifest JSON"
            />

            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded-lg px-3 py-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                取消
              </button>
              <button
                type="button"
                onClick={() => void submitManifest(editing.app, editing.manifestText)}
                className="rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-foreground)] active:scale-[0.98]"
              >
                提交（生成变更计划）
              </button>
            </div>
          </div>
        </div>
      )}

      {/* plan 审批 */}
      {reviewing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="审批变更计划" onClick={() => setReviewing(null)}>
          <div className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-[var(--foreground)]">变更计划 · {reviewing.app.name}</h2>
              {riskCount > 0 && (
                <span className={`${chipBase} bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300`}>
                  {riskCount} 项风险
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              「申请什么 ≠ 批什么」：可逐项收紧（取消勾选的项回退旧值），批准即生效并落审计。
            </p>

            <div className="mt-3 flex items-center gap-3 text-xs">
              <label className="inline-flex items-center gap-1.5 font-medium text-[var(--foreground)]">
                <input
                  type="radio"
                  checked={approvedPaths === null}
                  onChange={() => setApprovedPaths(null)}
                />
                全部批准
              </label>
              <label className="inline-flex items-center gap-1.5 text-[var(--muted-foreground)]">
                <input
                  type="radio"
                  checked={approvedPaths !== null}
                  onChange={() => {
                    // 逐项收紧：默认只勾选非风险项（风险项必须显式点头）
                    setApprovedPaths(
                      new Set(reviewing.plan.filter((p) => !p.risk && p.op !== '!').map((p) => p.path)),
                    );
                  }}
                />
                逐项收紧
              </label>
            </div>

            <ul className="mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto">
              {reviewing.plan.map((p) => {
                const meta = OP_LABEL[p.op] ?? OP_LABEL['='];
                const isRisk = p.risk || p.op === '!';
                const checked = approvedPaths === null ? true : approvedPaths.has(p.path);
                return (
                  <li
                    key={p.path}
                    className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
                      isRisk
                        ? 'border-rose-200 bg-rose-50/60 dark:border-rose-500/30 dark:bg-rose-500/5'
                        : 'border-[var(--border-subtle)] bg-[var(--surface-2)]'
                    }`}
                  >
                    {approvedPaths !== null ? (
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          setApprovedPaths((prev) => {
                            const next = new Set(prev ?? []);
                            if (e.target.checked) next.add(p.path);
                            else next.delete(p.path);
                            return next;
                          });
                        }}
                        className="mt-0.5"
                        aria-label={`批准 ${p.path}`}
                      />
                    ) : (
                      <span className={`${chipBase} ${meta.cls} flex-shrink-0`}>{meta.label}</span>
                    )}
                    <div className="min-w-0">
                      <p className="font-mono text-[var(--foreground)]">{p.path}</p>
                      <p className="mt-0.5 text-[var(--muted-foreground)]">{p.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ul>

            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => void decide(reviewing.app, false)}
                disabled={deciding}
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-500/40 dark:hover:bg-rose-500/15 disabled:opacity-60"
              >
                <X size={14} /> 拒绝
              </button>
              <button
                type="button"
                onClick={() => void decide(reviewing.app, true)}
                disabled={deciding || (approvedPaths !== null && approvedPaths.size === 0 && riskCount > 0)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-foreground)] active:scale-[0.98] disabled:opacity-60"
              >
                {deciding ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                {approvedPaths === null ? '全部批准并生效' : `批准 ${approvedPaths?.size ?? 0} 项并生效`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 详情（生效版本 + SDK 接入说明） */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="应用详情" onClick={() => setDetail(null)}>
          <div className="flex max-h-[88vh] w-full max-w-2xl flex-col overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-base font-bold text-[var(--foreground)]">应用详情 · {detail.app.name}</h2>
            {detailLoading ? (
              <div className="flex h-40 items-center justify-center" aria-busy="true">
                <Loader2 size={18} className="animate-spin text-[var(--muted-foreground)]" />
              </div>
            ) : (
              <>
                <details className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]">
                  <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-[var(--foreground)]">
                    生效 manifest
                  </summary>
                  <pre className="max-h-64 overflow-auto px-3 pb-3 font-mono text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    {detail.manifest ? JSON.stringify(detail.manifest, null, 2) : '（读取失败或为空）'}
                  </pre>
                </details>
                <details className="mt-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]" open>
                  <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-[var(--foreground)]">
                    建站用户接入说明（复制转发）
                  </summary>
                  <div className="px-3 pb-3">
                    <button
                      type="button"
                      onClick={() => {
                        void navigator.clipboard.writeText(sdkUsageMarkdown(detail.app));
                        toast.success('接入说明已复制（Markdown）');
                      }}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-semibold text-[var(--foreground)] hover:bg-[var(--surface-3)]"
                    >
                      <Copy size={12} /> 复制接入说明
                    </button>
                  </div>
                </details>
              </>
            )}
            <div className="mt-3 flex justify-end">
              <button type="button" onClick={() => setDetail(null)} className="rounded-lg px-3 py-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
