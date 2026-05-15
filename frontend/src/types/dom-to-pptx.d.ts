declare module '@halobiron/dom-to-pptx' {
  // The package is loaded as a UMD bundle from /vendor/dom-to-pptx.js
  // This declaration exists for TypeScript only; the actual JS is loaded at runtime.
  interface ExportOptions {
    fileName?: string;
    width?: number;
    height?: number;
    layout?: 'LAYOUT_4x3' | 'LAYOUT_16x9' | 'LAYOUT_16x10' | 'LAYOUT_WIDE';
    transition?: string;
  }

  export function exportToPptx(
    target: string | Element | Element[] | NodeList,
    options?: ExportOptions,
  ): Promise<void>;
}
