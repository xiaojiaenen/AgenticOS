/**
 * 错误消息本地化。
 *
 * 后端已把主要错误中文化，这里做两件兜底的事：
 * 1. 把仍可能出现的英文/框架级错误（网络失败、超时、5xx、第三方 SDK 报错）
 *    转成用户能看懂的中文；
 * 2. 未知错误保留原文但加上「联系管理员」提示，不再把堆栈或英文甩给用户。
 */

const NETWORK_PATTERNS: { test: RegExp; message: string }[] = [
  { test: /failed to fetch|networkerror|network request failed/i, message: '网络连接失败，请检查网络后重试' },
  { test: /load failed/i, message: '网络连接失败，请检查网络后重试' },
  { test: /timeout|timed out|aborted/i, message: '请求超时，请稍后重试' },
  { test: /aborted/i, message: '请求已取消' },
  { test: /rate limit|too many requests|429/i, message: '操作过于频繁，请稍后再试' },
  { test: /permission|forbidden|unauthorized|401|403/i, message: '没有权限执行该操作，请联系管理员' },
  { test: /not found|404/i, message: '请求的内容不存在或已被删除' },
  { test: /500|internal server error/i, message: '服务出错了，请稍后重试' },
  { test: /502|503|504|bad gateway|service unavailable/i, message: '服务暂时不可用，请稍后重试' },
  { test: /invalid email or password/i, message: '邮箱或密码不正确' },
  { test: /email already registered/i, message: '该邮箱已注册，请直接登录' },
  { test: /user is disabled/i, message: '账号已被禁用，请联系管理员' },
  { test: /already exists/i, message: '已存在同名内容，请换一个名称' },
  { test: /validation|invalid input|missing/i, message: '提交的内容不完整或有误，请检查后重试' },
];

/** 英文提示白名单式替换（后端偶发遗漏的固定文案） */
const PHRASES: [RegExp, string][] = [
  [/^Request body too large\.?$/, '内容太长了，请精简后再试'],
  [/^Internal Server Error$/, '服务出错了，请稍后重试'],
  [/^Not Found$/, '请求的内容不存在'],
  [/^Forbidden$/, '没有权限执行该操作'],
  [/^Unauthorized$/, '登录已失效，请重新登录'],
];

export function localizeError(raw: unknown, fallback = '操作失败，请稍后重试'): string {
  if (raw === null || raw === undefined) return fallback;
  const text = typeof raw === 'string' ? raw : raw instanceof Error ? raw.message : String(raw);
  const trimmed = text.trim();
  if (!trimmed) return fallback;

  for (const [pattern, message] of PHRASES) {
    if (pattern.test(trimmed)) return message;
  }
  for (const { test, message } of NETWORK_PATTERNS) {
    if (test.test(trimmed)) return message;
  }
  // 纯英文（不含中文）视为未本地化，加兜底说明而不是原样甩给用户
  if (!/[一-龥]/.test(trimmed)) {
    return `${fallback}（技术信息：${trimmed.slice(0, 80)}）`;
  }
  return trimmed;
}

/** 供 toast 使用的便捷包装 */
export function toastError(raw: unknown, fallback?: string): string {
  return localizeError(raw, fallback);
}
