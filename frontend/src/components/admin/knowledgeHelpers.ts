/**
 * 知识库管理：共享 zod schema、类型与小型工具函数。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { z } from 'zod';

// ---------------------------------------------------------------------------
// zod schema（对齐后端 KnowledgeBasePayload）
// ---------------------------------------------------------------------------

export const kbFormSchema = z.object({
  name: z.string().min(1, '请填写知识库名称'),
  description: z.string(),
  purpose: z.string(),
  scope: z.enum(['org', 'team', 'personal']),
  visibility: z.enum(['public', 'restricted', 'private']),
});

export type KBFormValues = z.infer<typeof kbFormSchema>;

export type DetailTab = 'documents' | 'wiki' | 'search' | 'reviews' | 'graph';

export function scopeLabel(scope: string): string {
  const map: Record<string, string> = { org: '组织级', team: '团队级', personal: '个人级' };
  return map[scope] || scope;
}

export function docStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待编译',
    compiling: '编译中',
    compiled: '已编译',
    failed: '失败',
  };
  return map[status] || status;
}

export function docStatusTone(status: string): 'active' | 'inactive' | 'warning' | 'info' {
  switch (status) {
    case 'compiled':
      return 'active';
    case 'failed':
      return 'inactive';
    case 'pending':
      return 'warning';
    default:
      return 'info';
  }
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
