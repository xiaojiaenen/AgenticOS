/**
 * 对外接口面板：把网关支持的协议、可用模型、接入配置集中展示。
 *
 * 为什么需要这个面板：网关同时支持 5 种协议（OpenAI Chat / Responses /
 * Anthropic Messages / Embeddings / Images），且 model 字段能指向两类东西
 * （智能体 vs 纯模型）。这些信息散在文档里，管理员根本不知道自己该填什么。
 *
 * 设计取舍：
 * - **按客户端分组**，不按协议分组 —— 用户的真实问题是「我要用 Cursor /
 *   Claude Code，怎么填」，不是「Responses 协议是什么」。
 * - **配置块可一键复制**，含完整的 base_url + 示例代码。
 * - **模型清单来自 /v1/models 实时数据**，不用手写，避免文档漂移。
 */
import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Bot,
  Copy,
  Cpu,
  Image as ImageIcon,
  Loader2,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Terminal,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/shadcn/button';
import { Skeleton } from '@/components/shadcn/skeleton';
import { AdminPageHeader, AdminPanel, ErrorBanner, SectionHeading } from './shared';
import { GATEWAY_BASE_URL, listApiKeys } from '@/services/apiKeyService';
import { cn } from '@/lib/utils';

type GatewayModel = {
  id: string;
  object?: string;
  display_name?: string;
  description?: string;
  owned_by?: string;
};

/** 复制到剪贴板，带降级（非 HTTPS 环境下 navigator.clipboard 不可用） */
async function copyText(text: string, label: string): Promise<void> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      document.body.removeChild(area);
    }
    toast.success(`${label} 已复制`);
  } catch {
    toast.error('复制失败，请手动选择文本');
  }
}

/** 可复制的代码块 */
function CodeBlock({ code, label }: { code: string; label: string }) {
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2.5 text-[11.5px] leading-relaxed font-medium text-[var(--foreground)]">
        <code>{code}</code>
      </pre>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => copyText(code, label)}
        className="absolute top-1.5 right-1.5 h-7 gap-1 px-2 text-[11px] opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
      >
        <Copy size={12} />
        复制
      </Button>
    </div>
  );
}

/** 单个客户端接入卡片 */
function ClientCard({
  icon: Icon,
  name,
  subtitle,
  baseUrl,
  modelHint,
  code,
}: {
  icon: React.ElementType;
  name: string;
  subtitle: string;
  baseUrl: string;
  modelHint: string;
  code: string;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--surface-2)] text-[var(--muted-foreground)]">
          <Icon size={14} />
        </span>
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-[var(--foreground)]">{name}</div>
          <div className="mt-0.5 text-[11.5px] font-medium text-[var(--muted-foreground)]">
            {subtitle}
          </div>
        </div>
      </div>

      <dl className="space-y-1.5 text-[11.5px]">
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 font-medium text-[var(--muted-foreground)]">Base URL</dt>
          <dd className="min-w-0 flex-1 truncate font-medium text-[var(--foreground)]">{baseUrl}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 font-medium text-[var(--muted-foreground)]">Model</dt>
          <dd className="min-w-0 flex-1 font-medium text-[var(--foreground)]">{modelHint}</dd>
        </div>
      </dl>

      <CodeBlock code={code} label={`${name} 配置`} />
    </div>
  );
}

export function GatewayEndpointsPanel() {
  const [selectedKeyId, setSelectedKeyId] = React.useState<string>('');

  const keysQuery = useQuery({
    queryKey: ['admin', 'api-keys', 'for-gateway'],
    queryFn: listApiKeys,
  });

  const activeKeys = React.useMemo(
    () => (keysQuery.data ?? []).filter((k) => k.enabled),
    [keysQuery.data],
  );

  // 默认选第一个可用 Key
  React.useEffect(() => {
    if (!selectedKeyId && activeKeys.length > 0) {
      setSelectedKeyId(String(activeKeys[0].id));
    }
  }, [activeKeys, selectedKeyId]);

  // 模型清单：用管理端 llm-providers 接口拼出来（含智能体 + 模型），
  // 不依赖明文 Key。与 /v1/models 的差异仅在于不含「实时探测」。
  const providerModelsQuery = useQuery({
    queryKey: ['admin', 'gateway', 'provider-models'],
    queryFn: async () => {
      const { apiFetch } = await import('@/services/apiClient');
      const res = await apiFetch<{ items?: Array<{ id: number; name: string; slug: string }> }>(
        '/api/v1/settings/llm-providers',
        {},
        '加载提供商失败',
      );
      const items = res.items ?? [];
      const out: GatewayModel[] = [];

      // 智能体（从 agent-profiles 拿）
      try {
        const agents = await apiFetch<{ items?: Array<{ slug: string; name: string }> }>(
          '/api/v1/agent-profiles',
          {},
          '加载智能体失败',
        );
        for (const a of agents.items ?? []) {
          out.push({
            id: a.slug,
            display_name: a.name,
            description: '智能体（带工具与多步编排）',
          });
        }
      } catch {
        /* 拿不到不影响其他 */
      }

      // 纯模型 + 向量化 + 生图（从各 provider 的 models 接口拿）
      for (const p of items) {
        try {
          const detail = await apiFetch<{
            roles?: Record<string, string>;
            role_options?: Array<{ value: string; label: string }>;
          }>(`/api/v1/settings/llm-providers/${p.id}/models`, {}, '加载模型失败');
          const roles = detail.roles ?? {};
          if (roles.chat) {
            out.push({
              id: `llm:${roles.chat}`,
              display_name: `直通模型 ${roles.chat}`,
              description: '纯模型调用（无系统工具，保留模型自身能力）',
            });
          }
          if (roles.embedding) {
            out.push({
              id: roles.embedding,
              display_name: `向量化 ${roles.embedding}`,
              description: '用于 /v1/embeddings',
            });
          }
          if (roles.image) {
            out.push({
              id: roles.image,
              display_name: `生图 ${roles.image}`,
              description: '用于 /v1/images/generations',
            });
          }
        } catch {
          /* 单个 provider 失败不影响其他 */
        }
      }

      // 去重（同一模型可能在多个 provider 上）
      const seen = new Set<string>();
      return out.filter((m) => (seen.has(m.id) ? false : (seen.add(m.id), true)));
    },
  });

  const models = providerModelsQuery.data ?? [];
  const loading = providerModelsQuery.isLoading;

  const agentModels = models.filter((m) => !m.id.startsWith('llm:') && !m.id.includes('embedding') && !m.id.includes('dall-e') && !m.id.includes('flux'));
  const llmModels = models.filter((m) => m.id.startsWith('llm:'));

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="对外接口"
        title="网关与接入"
        description="外部软件通过本平台调用 AI 能力。支持 5 种协议，模型既可以是智能体，也可以是纯模型。"
      />

      {keysQuery.isError && (
        <ErrorBanner
          message={
            keysQuery.error instanceof Error ? keysQuery.error.message : '加载 API Key 失败'
          }
          onRetry={() => keysQuery.refetch()}
        />
      )}

      {providerModelsQuery.isError && (
        <ErrorBanner
          message={
            providerModelsQuery.error instanceof Error
              ? providerModelsQuery.error.message
              : '加载模型清单失败'
          }
          onRetry={() => providerModelsQuery.refetch()}
        />
      )}

      {activeKeys.length === 0 && !keysQuery.isLoading && (
        <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 dark:border-amber-500/40 dark:bg-amber-500/10">
          <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-700 dark:text-amber-300" />
          <div className="min-w-0 text-[12px] font-medium text-amber-800 dark:text-amber-200">
            <p>还没有可用的 API Key。外部软件无法调用接口。</p>
            <p className="mt-1 opacity-80">
              请先到「API Key」页面创建一个，再回来查看接入配置。
            </p>
          </div>
        </div>
      )}

      {/* ============================================================ 协议端点 */}
      <AdminPanel>
        <SectionHeading
          title="支持的协议"
          description="同一个网关，不同客户端用不同协议，鉴权方式自动兼容。"
        />
        <div className="mt-3 overflow-hidden rounded-lg border border-[var(--border-subtle)]">
          <table className="w-full text-[12px]">
            <thead className="bg-[var(--surface-2)]">
              <tr className="text-left">
                <th className="px-3 py-2 font-semibold text-[var(--foreground)]">端点</th>
                <th className="px-3 py-2 font-semibold text-[var(--foreground)]">协议</th>
                <th className="px-3 py-2 font-semibold text-[var(--foreground)]">鉴权头</th>
                <th className="px-3 py-2 font-semibold text-[var(--foreground)]">典型客户端</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)]">
              {[
                ['/v1/chat/completions', 'OpenAI Chat', 'Authorization: Bearer', 'Cursor / Cherry Studio / Dify'],
                ['/v1/responses', 'OpenAI Responses', 'Authorization: Bearer', 'Codex / 新版 OpenAI SDK'],
                ['/v1/messages', 'Anthropic Messages', 'x-api-key', 'Claude Code / Anthropic SDK'],
                ['/v1/embeddings', 'OpenAI Embeddings', 'Authorization: Bearer', 'RAG 客户端'],
                ['/v1/images/generations', 'OpenAI Images', 'Authorization: Bearer', '绘图工具'],
                ['/v1/models', 'OpenAI Models', '两种都认', '所有客户端（列可用模型）'],
              ].map(([path, proto, auth, clients]) => (
                <tr key={path} className="hover:bg-[var(--surface-2)]">
                  <td className="px-3 py-2 font-medium tabular-nums text-[var(--foreground)]">{path}</td>
                  <td className="px-3 py-2 font-medium text-[var(--muted-foreground)]">{proto}</td>
                  <td className="px-3 py-2 font-medium text-[var(--muted-foreground)]">{auth}</td>
                  <td className="px-3 py-2 font-medium text-[var(--muted-foreground)]">{clients}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AdminPanel>

      {/* ============================================================ 客户端配置 */}
      <AdminPanel>
        <SectionHeading
          title="接入配置"
          description="按你使用的客户端选一个，复制后直接填进去。"
        />

        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <ClientCard
            icon={MessageSquare}
            name="OpenAI 兼容客户端"
            subtitle="Cursor / Cherry Studio / Dify / 任意 OpenAI SDK"
            baseUrl={GATEWAY_BASE_URL}
            modelHint={agentModels[0]?.id ?? 'general'}
            code={`OPENAI_BASE_URL=${GATEWAY_BASE_URL}
OPENAI_API_KEY=sk-agenticos-...
OPENAI_MODEL=${agentModels[0]?.id ?? 'general'}`}
          />

          <ClientCard
            icon={Terminal}
            name="Claude Code / Anthropic SDK"
            subtitle="用 x-api-key 鉴权，base_url 不带 /v1"
            baseUrl={GATEWAY_BASE_URL.replace(/\/v1$/, '')}
            modelHint={llmModels[0]?.id.replace('llm:', '') ?? 'auto/GLM-5.3-Flash'}
            code={`ANTHROPIC_BASE_URL=${GATEWAY_BASE_URL.replace(/\/v1$/, '')}
ANTHROPIC_API_KEY=sk-agenticos-...
ANTHROPIC_MODEL=${llmModels[0]?.id.replace('llm:', '') ?? 'auto/GLM-5.3-Flash'}`}
          />

          <ClientCard
            icon={Sparkles}
            name="OpenAI Responses（Codex）"
            subtitle="OpenAI 新版主推协议"
            baseUrl={GATEWAY_BASE_URL}
            modelHint={llmModels[0]?.id ?? 'llm:auto/GLM-5.3-Flash'}
            code={`OPENAI_BASE_URL=${GATEWAY_BASE_URL}
OPENAI_API_KEY=sk-agenticos-...
OPENAI_MODEL=${llmModels[0]?.id ?? 'llm:auto/GLM-5.3-Flash'}`}
          />

          <ClientCard
            icon={Cpu}
            name="向量化 / 生图"
            subtitle="独立端点，走 embedding / image 角色"
            baseUrl={GATEWAY_BASE_URL}
            modelHint={models.find((m) => m.id.includes('embedding'))?.id ?? '（未配置）'}
            code={`# 向量化
curl ${GATEWAY_BASE_URL}/embeddings \\
  -H "Authorization: Bearer sk-agenticos-..." \\
  -H "Content-Type: application/json" \\
  -d '{"input":["文本"]}'

# 生图
curl ${GATEWAY_BASE_URL}/images/generations \\
  -H "Authorization: Bearer sk-agenticos-..." \\
  -H "Content-Type: application/json" \\
  -d '{"prompt":"一只猫","size":"1024x1024"}'`}
          />
        </div>
      </AdminPanel>

      {/* ============================================================ 模型清单 */}
      <AdminPanel>
        <div className="flex items-start justify-between gap-3">
          <SectionHeading
            title="可用模型"
            description="model 字段可以填下面任意一个。智能体带工具编排，纯模型只有模型自身能力。"
          />
          <Button
            size="sm"
            variant="ghost"
            onClick={() => providerModelsQuery.refetch()}
            disabled={providerModelsQuery.isFetching}
            className="h-8 shrink-0 gap-1.5 px-2.5 text-[11.5px]"
          >
            {providerModelsQuery.isFetching ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            刷新
          </Button>
        </div>

        {loading ? (
          <div className="mt-3 space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : models.length === 0 ? (
          <p className="mt-3 text-[12px] font-medium text-[var(--muted-foreground)]">
            还没有可用模型。请先到「AI 提供商」页面添加提供商并绑定模型用途。
          </p>
        ) : (
          <div className="mt-3 space-y-4">
            {agentModels.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold text-[var(--muted-foreground)]">
                  <Bot size={12} />
                  智能体（带工具与多步编排）
                </div>
                <div className="space-y-1.5">
                  {agentModels.map((m) => (
                    <ModelRow key={m.id} model={m} kind="agent" />
                  ))}
                </div>
              </div>
            )}

            {llmModels.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold text-[var(--muted-foreground)]">
                  <Sparkles size={12} />
                  纯模型（无系统工具，保留模型自身能力）
                </div>
                <div className="space-y-1.5">
                  {llmModels.map((m) => (
                    <ModelRow key={m.id} model={m} kind="llm" />
                  ))}
                </div>
              </div>
            )}

            {models.some((m) => m.id.includes('embedding') || m.id.includes('dall-e')) && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold text-[var(--muted-foreground)]">
                  <ImageIcon size={12} />
                  向量化 / 生图
                </div>
                <div className="space-y-1.5">
                  {models
                    .filter((m) => m.id.includes('embedding') || m.id.includes('dall-e') || m.id.includes('flux'))
                    .map((m) => (
                      <ModelRow key={m.id} model={m} kind="other" />
                    ))}
                </div>
              </div>
            )}
          </div>
        )}
      </AdminPanel>

      {/* ============================================================ 说明 */}
      <AdminPanel>
        <SectionHeading title="model 字段怎么填" />
        <div className="mt-2 space-y-2 text-[12px] font-medium text-[var(--muted-foreground)]">
          <p>
            <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 text-[11.5px]">general</code>
            {' '}或任意智能体 slug → 走智能体（系统工具 + 多步编排）
          </p>
          <p>
            <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 text-[11.5px]">llm:模型名</code>
            {' '}→ 强制走纯模型（不经过智能体，但保留模型自身的 function calling 与 thinking）
          </p>
          <p>
            <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 text-[11.5px]">模型名</code>
            {' '}→ 未命中智能体时自动走纯模型
          </p>
          <p className="pt-1 text-[11.5px] opacity-80">
            纯模型通道可以透传 tools 定义，模型会自己决定是否发起调用，产出的
            tool_calls 原样返回给你的客户端执行 —— 这是模型能力，不是平台工具。
          </p>
        </div>
      </AdminPanel>
    </div>
  );
}

function ModelRow({ model, kind }: { model: GatewayModel; kind: 'agent' | 'llm' | 'other' }) {
  const badge =
    kind === 'agent'
      ? { label: '智能体', className: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' }
      : kind === 'llm'
        ? { label: '纯模型', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' }
        : { label: '专用', className: 'bg-slate-100 text-slate-600 dark:bg-slate-500/15 dark:text-slate-300' };

  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <code className="truncate text-[12px] font-semibold text-[var(--foreground)]">
            {model.id}
          </code>
          <span
            className={cn(
              'shrink-0 rounded px-1.5 py-0.5 text-[10.5px] font-semibold',
              badge.className,
            )}
          >
            {badge.label}
          </span>
        </div>
        {model.description && (
          <div className="mt-0.5 truncate text-[11px] font-medium text-[var(--muted-foreground)]">
            {model.description}
          </div>
        )}
      </div>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => copyText(model.id, '模型名')}
        className="h-7 shrink-0 gap-1 px-2 text-[11px]"
      >
        <Copy size={11} />
        复制
      </Button>
    </div>
  );
}
