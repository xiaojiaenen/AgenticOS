import DOMPurify from 'dompurify';

const HTML_PREVIEW_CSP =
  "default-src 'none'; img-src data: blob: https: http:; media-src data: blob: https: http:; style-src 'unsafe-inline' https: http:; script-src 'self' 'unsafe-inline' 'unsafe-eval' https: http:; font-src data: https: http: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

/**
 * Chart.js 以本地文件注入预览 iframe（内网部署要求零外网请求）。
 * 源码在 frontend/public/vendor/chart.umd.min.js，随前端产物一起部署。
 */
const CHART_JS_SRC = `${window.location.origin}/vendor/chart.umd.min.js`;

function hasHtmlShell(source: string): boolean {
  return /<html[\s>]|<!doctype/i.test(source);
}

function needsChartJs(source: string): boolean {
  return /\bnew\s+Chart\s*\(|\bChart\s*\./.test(source) && !/chart(?:\.umd)?(?:\.min)?\.js/i.test(source);
}

function injectChartJsIfNeeded(source: string): string {
  if (!needsChartJs(source)) return source;

  const script = `<script src="${CHART_JS_SRC}"></script>`;
  if (/<\/head>/i.test(source)) {
    return source.replace(/<\/head>/i, `${script}</head>`);
  }

  return `${script}${source}`;
}

function stripLocalScriptSrc(html: string): string {
  // Remove <script src="local/path"></script> tags that cannot resolve in
  // a srcdoc iframe.  Relative / absolute paths to local assets would 404.
  // Keep http(s):, data:, and inline scripts untouched.
  return html.replace(
    /<script\s+[^>]*src=["'](?!https?:\/\/|data:)[^"']+["'][^>]*>\s*<\/script>\s*/gi,
    '',
  );
}

export function buildSandboxedHtmlDocument(source: string): string {
  const cspMeta = `<meta http-equiv="Content-Security-Policy" content="${HTML_PREVIEW_CSP}" />`;
  const charsetMeta = '<meta charset="utf-8" />';
  const normalized = stripLocalScriptSrc(injectChartJsIfNeeded(source.trim()));

  if (!normalized) {
    return `<!DOCTYPE html><html><head>${charsetMeta}${cspMeta}</head><body></body></html>`;
  }

  if (!hasHtmlShell(normalized)) {
    return `<!DOCTYPE html><html><head>${charsetMeta}${cspMeta}</head><body>${normalized}</body></html>`;
  }

  if (/<head[\s>]/i.test(normalized)) {
    return normalized.replace(/<head([^>]*)>/i, `<head$1>${charsetMeta}${cspMeta}`);
  }

  if (/<html[\s>]/i.test(normalized)) {
    return normalized.replace(/<html([^>]*)>/i, `<html$1><head>${charsetMeta}${cspMeta}</head>`);
  }

  return `<!DOCTYPE html><html><head>${charsetMeta}${cspMeta}</head><body>${normalized}</body></html>`;
}

export function createObjectUrl(source: string, mimeType: string): string {
  return URL.createObjectURL(new Blob([source], { type: mimeType }));
}

/**
 * HTML sanitizer based on DOMPurify.
 * For announcements rendered via dangerouslySetInnerHTML.
 *
 * Kept deliberately strict (mirrors the previous regex-based behavior):
 * scripts, iframes, embeds, forms and interactive form controls are removed,
 * along with javascript:/data:text/html URLs and event handler attributes.
 */
const SANITIZE_FORBID_TAGS = [
  'script',
  'iframe',
  'object',
  'embed',
  'form',
  'input',
  'button',
  'select',
  'textarea',
];

export function sanitizeHtml(html: string): string {
  if (!html) return '';
  return DOMPurify.sanitize(html, {
    FORBID_TAGS: SANITIZE_FORBID_TAGS,
    FORBID_CONTENTS: ['script', 'style'],
    // Keep for backward compatibility with the legacy regex sanitizer, which
    // did not allow javascript: / data:text/html payloads in href/src.
    ALLOWED_URI_REGEXP:
      /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|data:image):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
  });
}
