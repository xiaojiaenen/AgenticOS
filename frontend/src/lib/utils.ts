import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export async function copyToClipboard(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
  } else {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
    } finally {
      document.body.removeChild(textArea);
    }
  }
}

// ---------------------------------------------------------------------------
// Dashboard formatting helpers (shared across admin components)
// ---------------------------------------------------------------------------

export function formatNumber(value: number): string {
  return Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

export function formatTokenNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs <= 10000) return `${value}`;
  if (abs >= 1e12) return `${(value / 1e12).toFixed(abs >= 1e13 ? 0 : 1)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(abs >= 1e10 ? 0 : 1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(abs >= 1e4 ? 0 : 1)}K`;
  return `${value}`;
}

export function formatLatency(value: number): string {
  if (!value) return '0 ms';
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${value} ms`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

export function formatDay(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match) {
    return `${Number(match[2])}/${Number(match[3])}`;
  }
  return value.slice(5);
}

export function shortName(name: string, maxLen = 7): string {
  if (!name) return '\u672a\u77e5';
  return name.length > maxLen ? `${name.slice(0, maxLen)}\u2026` : name;
}

export function initials(name: string): string {
  if (!name) return '?';
  return name.slice(0, 1).toUpperCase();
}

export function ratio(value: number, total: number): number {
  if (!total) return 0;
  return Math.max(0, Math.min(100, (value / total) * 100));
}

export const CHART_COLORS = ['#0f172a', '#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#f43f5e', '#14b8a6', '#6366f1'];
