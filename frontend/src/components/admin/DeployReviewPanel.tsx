/**
 * 部署审阅面板（管理员）。
 *
 * 一屏给齐管理员做判断所需的全部信息：
 *
 * - **网站说明**：用户填的一句话（审批时最该先看的东西）；
 * - **完整对话**：这个站点是怎么一步步长出来的（用户在会话里说了什么、
 *   AI 调了什么工具）—— 只看成品无法判断"是不是用户要的"；
 * - **实时预览**：iframe 直接渲染站点首屏；
 * - **源码扫描**：危险构造（eval / innerHTML / 外部请求…）与外部域名；
 * - **AI 评审意见**：模型给出的风险等级与建议（可参考，非裁决）。
 */
import * as React from 'react';
import {
  AlertTriangle,
  Bot,
  ExternalLink,
  FileCode2,
  Globe,
  Loader2,
  MessageSquare,
  ShieldCheck,
  X,
} from 'lucide-react';

import { motion } from 'motion/react';

import { apiFetch } from '@/services/apiClient';
import { getDeployReview, type DeployReviewPacket } from '@/services/websiteService';
import { buildSandboxedHtmlDocument } from '@/lib/safePreview';
import { Button } from '@/components/shadcn/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/shadcn/tabs';

const SEVERITY_TONE: Record<string, string> = {
  high: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-400',
  medium: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-400',
  low: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--muted-foreground)]',
};

const RISK_TONE: Record<string, string> = {
  low: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-400',
  medium: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-400',
  high: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-400',
};

const RISK_LABEL: Record<string, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
};

const RECOMMENDATION_LABEL: Record<string, string> = {
  approve: '建议通过',
  review: '建议人工复核',
  reject: '建议拒绝',
};

/** 字节数显示。小文件不该显示成「0 KB」—— 那看着像扫了个空目录。 */
function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const DeployReviewPanel: React.FC<{
  deployId: number;
  projectSlug: string;
  onClose: () => void;
}> = ({ deployId, projectSlug, onClose }) => {
  const [packet, setPacket] = React.useState<DeployReviewPacket | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [aiLoading, setAiLoading] = React.useState(false);
  const [previewHtml, setPreviewHtml] = React.useState<string>('');

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDeployReview(deployId, false)
      .then((data) => {
        if (cancelled) return;
        setPacket(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '获取审阅信息失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deployId]);

  // 预览 HTML 与审阅包并行取（预览端点只回 HTML，不带对话）
  React.useEffect(() => {
    let cancelled = false;
    apiFetch<{ preview_html: string }>(
      `/api/v1/admin/website/deploys/${deployId}/preview`,
      {},
      '获取预览失败',
    )
      .then((data) => {
        if (!cancelled) setPreviewHtml(data.preview_html || '');
      })
      .catch(() => {
        // 预览拿不到不阻塞审阅（对话与扫描仍在）
      });
    return () => {
      cancelled = true;
    };
  }, [deployId]);

  const runAiReview = async () => {
    setAiLoading(true);
    try {
      const data = await getDeployReview(deployId, true);
      setPacket((prev) => (prev ? { ...prev, ai: data.ai } : prev));
    } catch {
      // 错误由 toast 呈现
    } finally {
      setAiLoading(false);
    }
  };

  const previewDoc = React.useMemo(
    () => (previewHtml ? buildSandboxedHtmlDocument(previewHtml) : ''),
    [previewHtml],
  );

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/40 backdrop-blur-sm">
      <motion.aside
        initial={{ x: 40, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
        className="flex h-full w-full max-w-3xl flex-col overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-2xl"
      >
        {/* Header */}
        <header className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <ShieldCheck size={16} className="text-[var(--muted-foreground)]" />
              审阅 · {packet?.deploy.title || projectSlug}
            </h2>
            {packet?.deploy.description && (
              <p className="mt-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs leading-relaxed text-[var(--foreground)]">
                {packet.deploy.description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭审阅"
            className="shrink-0 rounded-lg p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          >
            <X size={16} />
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="animate-spin text-[var(--muted-foreground)]" />
            </div>
          ) : error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-400">
              {error}
            </div>
          ) : (
            <Tabs defaultValue="preview" className="w-full">
              <TabsList className="w-full sm:w-auto">
                <TabsTrigger value="preview" className="gap-1.5">
                  <Globe size={13} /> 预览
                </TabsTrigger>
                <TabsTrigger value="conversation" className="gap-1.5">
                  <MessageSquare size={13} /> 对话
                  {packet?.conversation.length ? (
                    <span className="rounded-full bg-[var(--surface-2)] px-1.5 text-[10px] font-semibold tabular-nums">
                      {packet.conversation.length}
                    </span>
                  ) : null}
                </TabsTrigger>
                <TabsTrigger value="source" className="gap-1.5">
                  <FileCode2 size={13} /> 源码
                  {packet?.analysis.hits?.length ? (
                    <span className="rounded-full bg-amber-100 px-1.5 text-[10px] font-semibold tabular-nums text-amber-800">
                      {packet.analysis.hits.length}
                    </span>
                  ) : null}
                </TabsTrigger>
                <TabsTrigger value="ai" className="gap-1.5">
                  <Bot size={13} /> AI 评审
                </TabsTrigger>
              </TabsList>

              {/* ── 预览 ── */}
              <TabsContent value="preview" className="m-0 pt-3">
                {previewHtml ? (
                  <iframe
                    title="deploy-preview"
                    srcDoc={previewDoc}
                    className="h-[60vh] w-full rounded-xl border border-[var(--border-subtle)] bg-white"
                    sandbox="allow-scripts"
                  />
                ) : (
                  <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] text-xs text-[var(--muted-foreground)]">
                    暂无预览内容
                  </div>
                )}
              </TabsContent>

              {/* ── 对话 ── */}
              <TabsContent value="conversation" className="m-0 pt-3">
                {packet?.conversation.length ? (
                  <div className="space-y-2.5">
                    {packet.conversation.map((turn, index) => (
                      <div
                        key={index}
                        className={`rounded-xl border px-3 py-2 ${
                          turn.role === 'user'
                            ? 'border-[var(--border-subtle)] bg-[var(--surface-2)]'
                            : 'border-transparent bg-[var(--surface-1)]'
                        }`}
                      >
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                          {turn.role === 'user' ? '用户' : turn.role === 'assistant' ? 'AI' : turn.role}
                        </p>
                        <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-[var(--foreground)]">
                          {turn.text}
                        </p>
                        {turn.tool_calls?.length ? (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {turn.tool_calls.map((tool, ti) => (
                              <span
                                key={ti}
                                className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)]"
                              >
                                {tool.name}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="py-10 text-center text-xs text-[var(--muted-foreground)]">
                    没有可展示的对话记录
                  </p>
                )}
              </TabsContent>

              {/* ── 源码扫描 ── */}
              <TabsContent value="source" className="m-0 pt-3">
                {!packet?.analysis.available ? (
                  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
                    {packet?.analysis.reason || '源码不可读（可能尚未构建）'}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-2 text-[11px]">
                      <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 text-[var(--muted-foreground)]">
                        {packet.analysis.file_count ?? 0} 个文件
                      </span>
                      <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 text-[var(--muted-foreground)]">
                        {formatBytes(packet.analysis.total_bytes ?? 0)}
                      </span>
                      {(packet.analysis.external_hosts ?? []).length > 0 && (
                        <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-400">
                          外部域名：{packet.analysis.external_hosts?.join('、')}
                        </span>
                      )}
                    </div>

                    {packet.analysis.hits?.length ? (
                      <div className="space-y-1.5">
                        {packet.analysis.hits.map((hit, index) => (
                          <div
                            key={index}
                            className={`rounded-lg border px-3 py-2 text-[11px] ${SEVERITY_TONE[hit.severity] ?? SEVERITY_TONE.low}`}
                          >
                            <div className="flex items-center gap-1.5 font-semibold">
                              <AlertTriangle size={12} />
                              <span className="truncate">{hit.pattern}</span>
                              <span className="ml-auto shrink-0 opacity-70">{hit.file}</span>
                            </div>
                            {hit.sample && (
                              <code className="mt-1 block truncate font-mono opacity-80">{hit.sample}</code>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-400">
                        未发现危险构造
                      </p>
                    )}

                    {packet.analysis.files?.length ? (
                      <details className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2">
                        <summary className="cursor-pointer text-xs font-semibold text-[var(--foreground)]">
                          文件清单（{packet.analysis.files.length}）
                        </summary>
                        <ul className="mt-2 space-y-1">
                          {packet.analysis.files.slice(0, 60).map((file, index) => (
                            <li
                              key={index}
                              className="flex justify-between gap-3 font-mono text-[10.5px] text-[var(--muted-foreground)]"
                            >
                              <span className="truncate">{file.path}</span>
                              <span className="shrink-0 tabular-nums">{file.size} B</span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </div>
                )}
              </TabsContent>

              {/* ── AI 评审 ── */}
              <TabsContent value="ai" className="m-0 pt-3">
                <div className="space-y-3">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => void runAiReview()}
                    disabled={aiLoading}
                  >
                    {aiLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Bot size={14} />
                    )}
                    {packet?.ai?.available ? '重新分析' : '运行 AI 源码与风险分析'}
                  </Button>

                  {packet?.ai?.available && (
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                            RISK_TONE[packet.ai.risk ?? 'low'] ?? RISK_TONE.low
                          }`}
                        >
                          {RISK_LABEL[packet.ai.risk ?? 'low'] ?? packet.ai.risk}
                        </span>
                        {packet.ai.recommendation && (
                          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted-foreground)]">
                            {RECOMMENDATION_LABEL[packet.ai.recommendation] ?? packet.ai.recommendation}
                          </span>
                        )}
                      </div>

                      {packet.ai.reasons?.length ? (
                        <ul className="space-y-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs leading-relaxed text-[var(--foreground)]">
                          {packet.ai.reasons.map((reason, index) => (
                            <li key={index} className="flex gap-1.5">
                              <span className="text-[var(--muted-foreground)]">·</span>
                              <span>{reason}</span>
                            </li>
                          ))}
                        </ul>
                      ) : null}

                      {packet.ai.notes && (
                        <p className="whitespace-pre-wrap rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs leading-relaxed text-[var(--foreground)]">
                          {packet.ai.notes}
                        </p>
                      )}
                    </div>
                  )}

                  {packet?.ai && !packet.ai.available && (
                    <p className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
                      {packet.ai.reason || 'AI 分析不可用'}
                    </p>
                  )}

                  <p className="text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    AI 意见仅供参考，不构成审批依据 —— 请结合预览、对话与源码扫描自行判断。
                  </p>
                </div>
              </TabsContent>
            </Tabs>
          )}
        </div>

        {/* Footer */}
        <footer className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] px-5 py-3">
          <a
            href={packet?.deploy.short_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <ExternalLink size={12} />
            打开短链
          </a>
          <Button variant="outline" size="sm" onClick={onClose}>
            关闭
          </Button>
        </footer>
      </motion.aside>
    </div>
  );
};

export default DeployReviewPanel;
