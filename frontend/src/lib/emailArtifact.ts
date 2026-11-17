/**
 * 邮件审批 → 制品面板数据的等价判断。
 *
 * ## 为什么单独抽出来
 *
 * Chat 页里有个 effect：`pendingApprovals` 里出现 send_email 时把邮件内容塞进
 * artifact 面板。原实现每次都 `setArtifact({...})` 新建对象，而该 effect 又
 * 依赖 `artifact` —— 于是：
 *
 *   setArtifact(新对象) → artifact 引用变化 → effect 重跑 → setArtifact → …
 *
 * React 直接抛 **error #185（Maximum update depth exceeded）**，发邮件时必现。
 *
 * 修法是在写入前比较内容。这个文件只做那一件事，所以能被单测覆盖 ——
 * 埋回 Chat.tsx 里就只能靠"发一封邮件看看"来验证了。
 */
import type { Artifact } from '@/types';

/** 从 send_email 的参数里取出面板需要的数据（参数缺失时返回 null）。 */
export function emailArtifactFromApproval(
  argumentsRaw: unknown,
  approvalId: string,
): Extract<Artifact, { language: 'email' }> | null {
  let args: Record<string, unknown> = {};
  if (typeof argumentsRaw === 'string') {
    try {
      args = JSON.parse(argumentsRaw) as Record<string, unknown>;
    } catch {
      return null;
    }
  } else if (argumentsRaw && typeof argumentsRaw === 'object') {
    args = argumentsRaw as Record<string, unknown>;
  }

  // 没有收件人和主题就不值得弹面板（模型可能还在补参数）
  if (!args.to || !args.subject) return null;

  return {
    language: 'email',
    approvalId: approvalId || '',
    to: String(args.to ?? ''),
    subject: String(args.subject ?? ''),
    body: String(args.body ?? ''),
    cc: args.cc ? String(args.cc) : undefined,
    isHtml: Boolean(args.is_html),
  };
}

/**
 * 两个制品是否**内容等价**（用于避免无意义的 setArtifact）。
 *
 * 只比较字段值，不比较引用 —— 这正是修复 #185 的关键：新建的对象只要内容
 * 没变就不该写入 store。
 */
export function isSameArtifact(a: Artifact | null | undefined, b: Artifact | null | undefined): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  // 两类制品字段差异大，先粗筛语言
  if (a.language !== b.language) return false;
  if (a.language === 'email' && b.language === 'email') {
    return (
      a.approvalId === b.approvalId &&
      a.to === b.to &&
      a.subject === b.subject &&
      a.body === b.body &&
      a.cc === b.cc &&
      a.isHtml === b.isHtml
    );
  }
  // 其它制品维持原行为：内容比较不覆盖它们（它们不是这里的问题来源）
  return false;
}
