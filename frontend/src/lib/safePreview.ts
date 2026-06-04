const HTML_PREVIEW_CSP =
  "default-src 'none'; img-src data: blob: https: http:; media-src data: blob: https: http:; style-src 'unsafe-inline' https: http:; script-src 'unsafe-inline' 'unsafe-eval' https: http:; font-src data: https: http:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

const CHART_JS_CDN = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js';

function hasHtmlShell(source: string): boolean {
  return /<html[\s>]|<!doctype/i.test(source);
}

function needsChartJs(source: string): boolean {
  return /\bnew\s+Chart\s*\(|\bChart\s*\./.test(source) && !/chart(?:\.umd)?(?:\.min)?\.js/i.test(source);
}

function injectChartJsIfNeeded(source: string): string {
  if (!needsChartJs(source)) return source;

  const script = `<script src="${CHART_JS_CDN}"></script>`;
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
