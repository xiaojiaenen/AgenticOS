/**
 * 提供商详情模态框：把「模型目录」与「账号池」从列表内联展开改为弹窗。
 *
 * 之前这两个面板直接在列表行下方展开，有三个问题：
 *   1. 列表里点一下，整行高度暴涨，后面几行被挤出视口，来回滚动；
 *   2. 同时只能开一个（``expanded`` 是单值状态），想对照两个提供商的账号
 *      得反复开关；
 *   3. 面板本身是纵向长内容（账号卡片 + 添加表单 / 模型表格 + 用途绑定），
 *      塞在列表行里没有独立滚动区，页面整体被拉得很长。
 *
 * 现在统一进 Dialog：固定高度、内部滚动、标题栏常驻，切换标签不丢上下文。
 */
import { Button } from '@/components/shadcn/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
import { StatusPill } from './shared';
import { LlmProviderCredentialPanel } from './LlmProviderCredentialPanel';
import { LlmProviderModelPanel } from './LlmProviderModelPanel';
import type { LlmProvider } from '@/services/llmProviderService';

export type ProviderDetailTab = 'accounts' | 'models';

const STATUS_TONE = {
  active: 'active',
  pending: 'inactive',
  expired: 'warning',
  failed: 'warning',
  disabled: 'inactive',
} as const;

const STATUS_LABEL: Record<string, string> = {
  active: '可用',
  pending: '未登录',
  expired: '已失效',
  failed: '登录失败',
  disabled: '已停用',
};

export function LlmProviderDetailDialog({
  provider,
  tab,
  onTabChange,
  onClose,
}: {
  provider: LlmProvider | null;
  tab: ProviderDetailTab;
  onTabChange: (tab: ProviderDetailTab) => void;
  onClose: () => void;
}) {
  const open = provider !== null;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-[min(64rem,calc(100vw-2rem))] flex-col gap-0 overflow-hidden p-0">
        {provider ? (
          <>
            {/* 标题栏常驻：滚动内容时不丢上下文 */}
            <DialogHeader className="shrink-0 gap-1 border-b border-[var(--border-subtle)] px-5 py-4">
              <DialogTitle className="flex flex-wrap items-center gap-2 pr-8">
                <span className="text-base font-semibold text-[var(--foreground)]">
                  {provider.name}
                </span>
                {provider.is_active ? <StatusPill tone="active">生效中</StatusPill> : null}
                {!provider.enabled ? <StatusPill tone="inactive">已停用</StatusPill> : null}
                <StatusPill tone="info">{provider.provider_type_label}</StatusPill>
                {provider.needs_cookie ? (
                  <StatusPill
                    tone={
                      STATUS_TONE[
                        (provider.credential?.status ?? 'pending') as keyof typeof STATUS_TONE
                      ] ?? 'inactive'
                    }
                  >
                    登录态：{STATUS_LABEL[provider.credential?.status ?? 'pending'] ?? '未登录'}
                  </StatusPill>
                ) : null}
              </DialogTitle>
              <DialogDescription className="truncate font-mono text-[11px]">
                {provider.base_url}
                {provider.model ? ` · ${provider.model}` : ''}
                <span className="ml-2 opacity-70">{provider.slug}</span>
              </DialogDescription>

              {/* 标签切换放在标题栏内：切模型/账号不用滚回顶部 */}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {provider.needs_cookie ? (
                  <Button
                    size="sm"
                    variant={tab === 'accounts' ? 'secondary' : 'outline'}
                    className="h-8 px-2.5"
                    onClick={() => onTabChange('accounts')}
                  >
                    账号{provider.account_count ? ` ${provider.account_count}` : ''}
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant={tab === 'models' ? 'secondary' : 'outline'}
                  className="h-8 px-2.5"
                  onClick={() => onTabChange('models')}
                >
                  模型
                </Button>
              </div>
            </DialogHeader>

            {/* 内容区独立滚动：长列表不再把页面拉长 */}
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {tab === 'accounts' ? (
                <LlmProviderCredentialPanel provider={provider} />
              ) : (
                <LlmProviderModelPanel provider={provider} />
              )}
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
