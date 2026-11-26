/**
 * 把工作区 html 产物里的**相对路径资源**内联进 HTML，供 `srcDoc` iframe 渲染。
 *
 * 背景：工作区 html 用 `<link href="style.css">` 引用同目录资源，但
 * - 预览走带鉴权的 `/outputs/{filename}` 端点（工作区不在静态目录下）；
 * - iframe 用 `srcDoc` + sandbox（无 allow-same-origin），相对 URL 会解析到父页面、
 *   且 iframe 内 fetch 带不了 Authorization header。
 * 因此必须在父页面用 apiFetch 把资源抓回来，再改写成内联形式：
 *   <link rel=stylesheet href="style.css"> → <style>...css 文本...</style>
 *   <img src="logo.png">                  → <img src="data:image/png;base64,...">
 *
 * 安全：只处理相对路径（跳过 http(s)/data/blob//# 等），只改有限标签与属性，
 * 限制资源数量与大小，抓取失败时保留原引用（退化为加载不到，不影响主文档）。
 */
export type FetchResource = (filename: string) => Promise<{ text?: string; blob?: Blob }>;

const MAX_RESOURCES = 20;

/** 是否是可内联的相对路径资源引用。 */
export function isInlineableRelative(href: string): boolean {
  const value = href.trim();
  if (!value || value.startsWith('#')) return false;
  // 绝对 URL / 协议相对 // / data / blob / javascript 一律跳过
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) return false;
  if (value.startsWith('//')) return false;
  if (value.includes('..')) return false; // 路径穿越不处理
  return true;
}

function mediaTypeOf(filename: string, blob: Blob): string {
  if (blob.type) return blob.type;
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
    gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml',
  };
  return map[ext] ?? 'application/octet-stream';
}

function blobToDataUrl(blob: Blob, filename: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(`data:${mediaTypeOf(filename, blob)};base64,${String(reader.result).split(',').pop() ?? ''}`);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/**
 * 抓取并内联 html 里的相对路径 CSS / 图片 / 脚本。
 *
 * @param html 原始 html 文本
 * @param fetchResource 按文件名抓取资源的函数（调用方用 apiFetch 实现，带鉴权）
 * @returns 内联后的 html（抓取失败的资源保留原样）
 */
export async function inlineHtmlResources(
  html: string,
  fetchResource: FetchResource,
): Promise<string> {
  const cssRefs = [...html.matchAll(/<link\b[^>]*\brel=["']?stylesheet["']?[^>]*\bhref=["']([^"']+)["'][^>]*>/gi)];
  const imgRefs = [...html.matchAll(/<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi)];
  const jobs: Array<{ full: string; href: string; kind: 'css' | 'img' }> = [];
  for (const m of cssRefs) jobs.push({ full: m[0], href: m[1], kind: 'css' });
  for (const m of imgRefs) jobs.push({ full: m[0], href: m[1], kind: 'img' });
  if (jobs.length === 0) return html;

  let result = html;
  let count = 0;
  for (const job of jobs) {
    if (count >= MAX_RESOURCES) break;
    if (!isInlineableRelative(job.href)) continue;
    const filename = job.href.split('/').pop() ?? job.href;
    count += 1;
    try {
      const res = await fetchResource(filename);
      if (job.kind === 'css' && res.text != null) {
        // 防止资源内容里出现 </style> 提前闭合（模型生成内容不可信）
        const safe = res.text.replace(/<\/style/gi, '<\\/style');
        result = result.replace(job.full, `<style data-inline-src="${filename}">\n${safe}\n</style>`);
      } else if (job.kind === 'img' && res.blob != null) {
        const dataUrl = await blobToDataUrl(res.blob, filename);
        result = result.replace(job.full, job.full.replace(job.href, dataUrl));
      }
    } catch {
      // 抓取失败：保留原引用，让浏览器按原样尝试（通常加载不到，但不破坏主文档）
    }
  }
  return result;
}

/**
 * 判断一份 html 是否引用了同目录工作区文件（用于决定是否尝试内联）。
 * 只做字符串检测，不解析 DOM。
 */
export function hasRelativeResourceRefs(html: string): boolean {
  return /<link\b[^>]*\brel=["']?stylesheet["']?/i.test(html) || /<img\b[^>]*\bsrc=["']/i.test(html);
}

/** 供 UI 展示：html 引用了哪些同目录资源文件名（去重）。 */
export function referencedResourceNames(html: string): string[] {
  const names = new Set<string>();
  for (const m of html.matchAll(/<link\b[^>]*\brel=["']?stylesheet["']?[^>]*\bhref=["']([^"']+)["'][^>]*>/gi)) {
    if (isInlineableRelative(m[1])) names.add(m[1].split('/').pop() ?? m[1]);
  }
  for (const m of html.matchAll(/<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi)) {
    if (isInlineableRelative(m[1])) names.add(m[1].split('/').pop() ?? m[1]);
  }
  return [...names];
}
