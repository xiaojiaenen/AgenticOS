/**
 * 集成管理：从 OpenAPI 导入弹窗。
 * 从 IntegrationManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { Loader2, Save, Upload } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
import { cn } from '@/lib/utils';
import { OpenApiPreview } from '@/services/integrationService';
import { methodBadgeColor } from './integrationHelpers';

export function OpenApiImportDialog({
  open,
  input,
  preview,
  previewPending,
  confirmPending,
  onOpenChange,
  onInputChange,
  onPreview,
  onConfirm,
}: {
  open: boolean;
  input: string;
  preview: OpenApiPreview | null;
  previewPending: boolean;
  confirmPending: boolean;
  onOpenChange: (open: boolean) => void;
  onInputChange: (value: string) => void;
  onPreview: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>从 OpenAPI 导入</DialogTitle>
          <DialogDescription>粘贴 OpenAPI JSON 内容或输入 URL</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <textarea
            className="min-h-[120px] w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 font-mono text-xs text-[var(--foreground)] outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="粘贴 OpenAPI JSON 内容或输入 URL..."
          />
          <Button
            className="w-full gap-2"
            onClick={onPreview}
            disabled={previewPending || !input.trim()}
          >
            {previewPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Upload size={16} />
            )}
            解析预览
          </Button>

          {preview && (
            <div className="space-y-2 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
              <p className="font-semibold text-[var(--foreground)]">{preview.system_name}</p>
              <p className="text-sm font-medium text-[var(--muted-foreground)]">{preview.system_description}</p>
              <div className="flex flex-wrap items-center gap-4 text-xs font-medium text-zinc-600">
                <span>
                  Base URL: <span className="font-mono">{preview.base_url}</span>
                </span>
                <span>鉴权: {preview.auth_type}</span>
              </div>
              <p className="text-sm font-semibold text-zinc-700">
                {preview.apis.length} 个接口将被导入:
              </p>
              <div className="max-h-[200px] space-y-1 overflow-y-auto">
                {preview.apis.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className={cn('rounded-lg px-1.5 py-0.5 font-semibold', methodBadgeColor(a.method))}>
                      {a.method}
                    </span>
                    <span className="font-mono text-zinc-600">{a.path}</span>
                    <span className="text-[var(--muted-foreground)]">{a.display_name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={onConfirm}
            disabled={confirmPending || !preview}
            className="gap-2"
          >
            {confirmPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            确认导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
