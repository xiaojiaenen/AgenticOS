const HTML_PREVIEW_CSP =
  "default-src 'none'; img-src data: blob: https: http:; media-src data: blob: https: http:; style-src 'unsafe-inline'; script-src 'unsafe-inline' 'unsafe-eval'; font-src data: https: http:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

function hasHtmlShell(source: string): boolean {
  return /<html[\s>]|<!doctype/i.test(source);
}

export function buildSandboxedHtmlDocument(source: string): string {
  const cspMeta = `<meta http-equiv="Content-Security-Policy" content="${HTML_PREVIEW_CSP}" />`;
  const charsetMeta = '<meta charset="utf-8" />';
  const normalized = source.trim();

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
