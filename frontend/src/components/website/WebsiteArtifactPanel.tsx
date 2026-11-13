import React, { useState } from 'react'
import { motion, MotionValue } from 'motion/react'
import { CheckCircle2, ExternalLink, Globe, RefreshCcw, Rocket, X, XCircle } from 'lucide-react'
import { Artifact } from '../../types'
import { buildSandboxedHtmlDocument } from '../../lib/safePreview'
import { ArtifactVersionBar } from '../chat/ArtifactVersionBar'
import { requestDeploy, getDeployByProject, cancelDeploy, issueWebsitePreviewUrl, DeployStatus } from '../../services/websiteService'
import { apiFetch } from '../../services/apiClient'

type WebsiteArtifactPanelProps = {
  artifact: Extract<Artifact, { language: 'website' }>
  onClose: () => void
  borderColor: MotionValue<string>
  /** 当前会话 ID — requestDeploy 首参必须是 sessionId，不是 artifactId */
  sessionId?: string
  /** 切换到历史版本（由版本条调用） */
  onSwitchVersion?: (artifact: Extract<Artifact, { language: 'website' }>) => void
}

export const WebsiteArtifactPanel: React.FC<WebsiteArtifactPanelProps> = ({
  artifact,
  onClose,
  borderColor,
  sessionId,
  onSwitchVersion,
}) => {
  const [isDeploying, setIsDeploying] = React.useState(false)
  // 作品名：部署时由用户填写；留空则由后端回退会话标题/目录名。
  const [deployTitle, setDeployTitle] = useState('')
  // 部署可见性：点「部署」先弹选择（公开 / 私密），明确确认再提交。
  // 私密 = 仅自己在作品库可见（带签名链接）；公开 = 审批后上 /sites/。
  const [visibilityPickerOpen, setVisibilityPickerOpen] = React.useState(false)
  const [deployStatus, setDeployStatus] = React.useState<DeployStatus | null>(null)
  const [deployUrl, setDeployUrl] = React.useState<string | null>(null)
  const [deployError, setDeployError] = React.useState<string | null>(null)
  // 网站说明：给作品库卡片和审批页看的一句话介绍。
  const [deployDescription, setDeployDescription] = useState('')
  // 部署记录 id —— 取消部署需要它（申请返回的记录 id）。
  const [deployId, setDeployId] = React.useState<number | null>(null)
  const [isCancelling, setIsCancelling] = React.useState(false)
  const [refreshNonce, setRefreshNonce] = React.useState(0)
  const projectSlug = artifact.projectSlug

  // 部署是「用户申请 → 管理员审批 → 后端发布」的异步流程：申请接口当场返回的
  // deploy_url 必然为 null（那时还是 pending）。不轮询的话用户会永远停在
  // 「等待管理员审批」，审批通过了也拿不到正式地址。
  React.useEffect(() => {
    if (deployStatus !== 'pending') return
    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const record = await getDeployByProject(projectSlug)
        if (cancelled || !record) return
        setDeployStatus(record.status)
        if (record.deploy_url) setDeployUrl(record.deploy_url)
      } catch {
        // 单次轮询失败不打断，下一拍继续
      }
    }, 5000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [deployStatus, projectSlug])

  // 面板自己持有预览 HTML：artifact.html 是打开面板那一刻的快照，
  // 之后 agent 又改了代码、重建了 dist，父组件的 prop 不会变 —— 用户点
  // 「刷新」看到还是旧页面，误以为预览坏了。这里在刷新时**真的回源**
  // 拉一次最新 dist（按 project_slug 取会话最新 artifact）。
  const [liveHtml, setLiveHtml] = React.useState<string>(artifact.html)
  const [liveUrl, setLiveUrl] = React.useState<string | undefined>(artifact.previewUrl)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [refreshError, setRefreshError] = React.useState<string | null>(null)

  React.useEffect(() => {
    // 切换版本 / 换项目时同步基准
    setLiveHtml(artifact.html)
    setLiveUrl(artifact.previewUrl)
  }, [artifact.html, artifact.projectSlug, artifact.previewUrl])

  // ── srcDoc 劫持防护（vue/react SPA 必须走子路径托管的 preview_url）──
  //
  // srcDoc 文档的相对 URL 与 history.replaceState 都以**父文档**为基准。
  // Vue Router 的 hash 模式启动时 replaceState('#/') 会把 iframe 导航到
  // /chat#/ —— SPA 兜底返回 AgenticOS 自己，用户看到"预览里是当前网站"。
  // （实测：contentWindow.location = /chat#/，正文变成 AgenticOS 对话页。）
  //
  // 所以带 router 的栈（vue/react）绝不退回 srcDoc：挂载时没有 preview_url
  // 就现签一个；签不到显示提示而不是内联 HTML。vanilla 无路由脚本，srcDoc
  // 安全，保留作为兜底。
  const isRouterStack = artifact.stack === 'vue' || artifact.stack === 'react'
  React.useEffect(() => {
    if (!isRouterStack && liveUrl) return
    const sid = sessionId || artifact.sessionId
    if (!sid) return
    let cancelled = false
    ;(async () => {
      try {
        const signed = await issueWebsitePreviewUrl(sid, artifact.projectSlug)
        if (!cancelled && signed?.url) {
          setLiveUrl(signed.url)
        }
      } catch {
        // 签发失败：vue/react 显示提示（不退 srcDoc），vanilla 保持 srcDoc
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isRouterStack, liveUrl, sessionId, artifact.sessionId, artifact.projectSlug])


  // 用 srcDoc 而非 blob URL：blob 在 StrictMode 双调用下会被提前 revoke，
  // 导致 iframe 拿到失效地址而空白。刷新通过 key 强制重挂载实现。
  const previewDoc = React.useMemo(
    () => buildSandboxedHtmlDocument(liveHtml),
    [liveHtml],
  )

  const handleRefresh = React.useCallback(async () => {
    const sid = sessionId || artifact.sessionId
    if (!sid) {
      // 没有会话上下文时只能重挂载（本地预览无法回源）
      setRefreshNonce((n) => n + 1)
      return
    }
    setIsRefreshing(true)
    setRefreshError(null)
    try {
      const data = await apiFetch<{
        website_artifact: {
          preview_html?: string;
          preview_url?: string | null;
          project_slug?: string;
        } | null
      }>(`/api/v1/agent/sessions/${sid}/artifacts`, {}, '刷新预览失败')
      const latest = data.website_artifact
      if (latest?.preview_url || latest?.preview_html) {
        // 换 URL 让浏览器重新请求（新令牌也顺带续期）
        setLiveUrl(latest.preview_url ?? undefined)
        setLiveHtml(latest.preview_html ?? '')
        setRefreshNonce((n) => n + 1)
      } else {
        setRefreshError('后端还没有可预览的构建产物（可能尚未构建完成）')
      }
    } catch (err) {
      setRefreshError(err instanceof Error ? err.message : '刷新预览失败')
    } finally {
      setIsRefreshing(false)
    }
  }, [sessionId, artifact.sessionId])

  const handleDeploy = async (visibility: 'public' | 'private') => {
    // 首参必须是 sessionId（不是 artifactId）
    const deploySessionId = sessionId || artifact.sessionId
    if (!deploySessionId) {
      setDeployError('缺少会话 ID，无法发起部署')
      setDeployStatus('failed')
      return
    }
    setIsDeploying(true)
    setDeployError(null)
    setDeployStatus('pending')
    try {
      const result = await requestDeploy(
        deploySessionId,
        artifact.projectSlug,
        artifact.stack ?? '',
        undefined,
        visibility,
        deployTitle.trim() || undefined,
        deployDescription.trim() || undefined,
      )
      setDeployStatus(result.status)
      setDeployId(result.id)
      if (result.deploy_url) {
        setDeployUrl(result.deploy_url)
      }
    } catch (err) {
      setDeployError(err instanceof Error ? err.message : 'Deploy failed')
      setDeployStatus('failed')
    } finally {
      setIsDeploying(false)
    }
  }

  const handleCancel = async () => {
    if (deployId === null) return
    setIsCancelling(true)
    setDeployError(null)
    try {
      const result = await cancelDeploy(deployId)
      setDeployStatus(result.status as DeployStatus)
      setDeployUrl(null)
    } catch (err) {
      setDeployError(err instanceof Error ? err.message : '取消部署失败')
    } finally {
      setIsCancelling(false)
    }
  }

  const stackLabel =
    artifact.stack === 'react'
      ? 'React'
      : artifact.stack === 'vue'
        ? 'Vue'
        : 'Vanilla'

  const submitVisibility = (visibility: 'public' | 'private') => {
    setVisibilityPickerOpen(false)
    void handleDeploy(visibility)
  }

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '60%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col overflow-hidden border-l bg-[var(--surface-1)]/70 ring-1 ring-[var(--border-subtle)] backdrop-blur-3xl"
      style={{ borderColor }}
    >
      {/* Header */}
      <div className="z-10 flex h-14 flex-shrink-0 items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-6 backdrop-blur-md">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm">
            <Globe size={18} />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold leading-none text-[var(--foreground)]">
              {artifact.title}
            </h2>
            <div className="mt-1 flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-foreground)]">
                {artifact.projectSlug} · {stackLabel}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <ArtifactVersionBar
            sessionId={sessionId || artifact.sessionId}
            currentReference={artifact.version ? `v${artifact.version}` : undefined}
            kind="website"
            onSelect={({ artifact: loaded }) => {
              onSwitchVersion?.({
                language: 'website',
                artifactId: String(loaded.artifact_id ?? ''),
                html: String(loaded.preview_html ?? ''),
                title: String(loaded.title ?? ''),
                projectSlug: String(loaded.project_slug ?? ''),
                stack: loaded.stack as string | undefined,
                fileCount: 0,
              });
            }}
          />
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={isRefreshing}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-3)] disabled:opacity-60"
            title="重新拉取最新构建产物"
            aria-label="刷新预览"
          >
            <RefreshCcw size={13} className={isRefreshing ? 'animate-spin' : undefined} />
            {isRefreshing ? '刷新中' : '刷新'}
          </button>
          <button
            type="button"
            onClick={() => setVisibilityPickerOpen(true)}
            disabled={isDeploying || deployStatus === 'pending'}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-colors hover:opacity-90 disabled:opacity-60"
            title="发布网站到作品库"
            aria-label="发布网站到作品库"
          >
            {isDeploying ? (
              <RefreshCcw size={13} className="animate-spin" />
            ) : (
              <Rocket size={13} />
            )}
            发布
          </button>
          <div className="mx-2 h-4 w-px bg-[var(--border-medium)]" />
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl p-2 text-[var(--muted-foreground)] transition-all hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-500/15"
            aria-label="Close website preview"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Deploy status banner */}
      {deployStatus && (
        <div
          className={`z-10 mx-6 mt-3 rounded-xl px-4 py-2.5 text-xs font-semibold ${
            deployStatus === 'approved' || deployStatus === 'deploying' || deployStatus === 'deployed'
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : deployStatus === 'rejected' || deployStatus === 'failed'
                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                : 'bg-amber-50 text-amber-700 border border-amber-200'
          }`}
        >
          <div className="flex items-center gap-2">
            {deployStatus === 'pending' && (
              <RefreshCcw size={13} className="animate-spin" />
            )}
            {deployStatus === 'approved' || deployStatus === 'deploying' ? (
              <RefreshCcw size={13} className="animate-spin" />
            ) : deployStatus === 'deployed' ? (
              <CheckCircle2 size={13} />
            ) : deployStatus === 'rejected' || deployStatus === 'failed' ? (
              <XCircle size={13} />
            ) : null}
            <span className="min-w-0 flex-1 truncate">
              {deployStatus === 'pending' && '发布申请已提交，等待管理员审批'}
              {deployStatus === 'approved' && '审批已通过，正在发布'}
              {deployStatus === 'deploying' && '正在部署中...'}
              {deployStatus === 'deployed' && (
                <>
                  已发布，正式地址：
                  {deployUrl ? (
                    <a
                      href={deployUrl}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => {
                        // iframe 预览用的 srcDoc 会劫持同窗口导航，链接必须强制顶层打开
                        e.preventDefault()
                        window.open(deployUrl, '_blank', 'noopener')
                      }}
                      className="font-semibold underline underline-offset-2 hover:no-underline"
                    >
                      {deployUrl}
                      <ExternalLink size={12} className="ml-1 inline align-[-1px]" />
                    </a>
                  ) : (
                    '（地址生成中）'
                  )}
                </>
              )}
              {deployStatus === 'rejected' && '发布申请已被拒绝'}
              {deployStatus === 'failed' && `发布失败：${deployError || '未知错误'}`}
            </span>
            {(deployStatus === 'deployed' || deployStatus === 'approved') && deployId !== null && (
              <button
                type="button"
                onClick={() => void handleCancel()}
                disabled={isCancelling}
                className="ml-auto shrink-0 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] font-semibold text-[var(--muted-foreground)] transition-colors hover:border-rose-300 hover:text-rose-600 disabled:opacity-60"
                title="取消发布：站点下线，源码保留，可随时重新发布"
              >
                {isCancelling ? '取消中…' : '取消发布'}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Body — iframe preview */}
      <div className="z-10 flex-1 overflow-auto p-6">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="min-h-full overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-xl"
        >
          <iframe
            key={`website-preview-${refreshNonce}-${liveUrl ? 'url' : 'inline'}`}
            // 优先用带签名的静态托管 URL：浏览器原生加载 JS/CSS（可缓存、
            // 支持相对路径、无「内联 module 不执行」的问题）。只有拿不到
            // URL（签发失败 / 离线）时才退回 srcDoc 内联方案。
            src={liveUrl || undefined}
            srcDoc={!liveUrl && !isRouterStack ? previewDoc : undefined}
            title={artifact.title}
            className="min-h-[calc(100vh-10rem)] w-full border-0"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            allow="fullscreen"
            referrerPolicy="no-referrer"
          />
          {isRouterStack && !liveUrl && (
            <div className="mx-4 mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-400">
              {isRefreshing
                ? '正在签发预览链接…'
                : 'SPA 站点需要通过预览链接访问（内联预览会劫持路由），签发失败请点「刷新」重试。'}
            </div>
          )}
          {refreshError && (
            <div className="mx-4 mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {refreshError}
            </div>
          )}
        </motion.div>
      </div>
      {/* 部署可见性选择：公开（审批后上 /sites/）或私密（仅自己作品库可见） */}
      {visibilityPickerOpen && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="w-[min(92%,380px)] rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-2xl">
            <h3 className="mb-1 text-sm font-semibold text-[var(--foreground)]">选择作品可见性</h3>
            <p className="mb-3 text-xs leading-relaxed text-[var(--muted-foreground)]">
              公开作品需要管理员审批后发布到站点目录；私密作品仅自己可见，可随时重置访问链接。
            </p>
            <label className="mb-4 block">
              <span className="mb-1.5 block text-[11px] font-semibold text-[var(--foreground)]">作品名</span>
              <input
                type="text"
                value={deployTitle}
                onChange={(e) => setDeployTitle(e.target.value)}
                maxLength={200}
                placeholder="留空则由 AI 根据对话自动生成"
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus-visible:border-[var(--ring)]"
              />
            </label>
            <label className="mb-3 block">
              <span className="mb-1.5 block text-[11px] font-semibold text-[var(--foreground)]">
                网站说明
              </span>
              <textarea
                value={deployDescription}
                onChange={(e) => setDeployDescription(e.target.value)}
                maxLength={500}
                rows={3}
                placeholder="一句话介绍这个网站做什么、给谁用。管理员审批时能看到，作品库卡片上也会展示。"
                className="w-full resize-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-sm leading-relaxed outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus-visible:border-[var(--ring)]"
              />
            </label>
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => submitVisibility('private')}
                disabled={isDeploying}
                className="flex w-full items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-3 text-left transition-colors hover:border-[var(--primary)] hover:bg-[var(--surface-3)] disabled:opacity-60"
              >
                <span className="mt-0.5 text-lg">🔒</span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-[var(--foreground)]">私密作品</span>
                  <span className="block text-xs text-[var(--muted-foreground)]">
                    仅自己在作品库可见，访问链接带签名、可随时重置
                  </span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => submitVisibility('public')}
                disabled={isDeploying}
                className="flex w-full items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-3 text-left transition-colors hover:border-[var(--primary)] hover:bg-[var(--surface-3)] disabled:opacity-60"
              >
                <span className="mt-0.5 text-lg">🌐</span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-[var(--foreground)]">公开作品</span>
                  <span className="block text-xs text-[var(--muted-foreground)]">
                    管理员审批后发布到站点目录，所有人可访问
                  </span>
                </span>
              </button>
            </div>
            <button
              type="button"
              onClick={() => setVisibilityPickerOpen(false)}
              className="mt-3 w-full rounded-lg py-1.5 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              取消
            </button>
          </div>
        </div>
      )}
</motion.aside>
  )
}