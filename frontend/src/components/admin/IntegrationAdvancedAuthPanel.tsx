/**
 * 集成管理：高级安全设置面板（签名 / 加密 / 解密）。
 * 从 IntegrationManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import * as React from 'react';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { AES_ALGOS, SIGN_ALGOS, type AdvancedAuth } from './integrationHelpers';

export function AdvancedAuthPanel({
  aa,
  onChange,
}: {
  aa: AdvancedAuth;
  onChange: (v: AdvancedAuth) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const sign = aa.sign ?? {};
  const enc = aa.request_encrypt ?? {};
  const dec = aa.response_decrypt ?? {};
  const common = aa.common ?? {};
  const set = (section: string, key: string, val: string) =>
    onChange({ ...aa, [section]: { ...(aa[section] ?? {}), [key]: val } });
  const hasSign = sign.algorithm !== undefined && sign.algorithm !== 'none' && sign.algorithm !== '';
  const hasEnc = enc.algorithm !== undefined && enc.algorithm !== 'none' && enc.algorithm !== '';
  const hasDec = dec.algorithm !== undefined && dec.algorithm !== 'none' && dec.algorithm !== '';

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-[var(--surface-2)]"
      >
        <span className="text-sm font-semibold text-zinc-700">签名 / 加密 / 解密</span>
        <span className="text-xs font-medium text-[var(--muted-foreground)]">
          {open ? '收起' : '展开'}
          {hasSign || hasEnc || hasDec ? ' · 已配置' : ''}
        </span>
      </button>
      {open && (
        <div className="space-y-5 border-t border-zinc-100 px-4 py-4">
          <div className="space-y-3 rounded-lg border border-amber-100 bg-amber-50/40 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-amber-600">请求签名</p>
            <div className="space-y-1.5">
              <Label>签名算法</Label>
              <Select value={sign.algorithm || 'none'} onValueChange={(v) => set('sign', 'algorithm', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SIGN_ALGOS.map((a) => (
                    <SelectItem key={a.v} value={a.v}>{a.l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasSign && (
              <>
                <div className="space-y-1.5">
                  <Label>{sign.algorithm?.startsWith('rsa') ? 'RSA 私钥 (PEM)' : '签名密钥'}</Label>
                  <textarea
                    rows={2}
                    className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 font-mono text-xs text-[var(--foreground)] outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25"
                    value={sign.secret || ''}
                    onChange={(e) => set('sign', 'secret', e.target.value)}
                    placeholder={sign.algorithm?.startsWith('rsa') ? '-----BEGIN PRIVATE KEY-----\n...' : '输入密钥'}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>签名位置</Label>
                    <Select value={sign.placement || 'header'} onValueChange={(v) => set('sign', 'placement', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="header">Header</SelectItem>
                        <SelectItem value="query">Query Param</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>字段名</Label>
                    <Input value={sign.field_name || ''} onChange={(e) => set('sign', 'field_name', e.target.value)} placeholder="X-Signature" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>签名内容模板</Label>
                  <Input
                    className="font-mono text-xs"
                    value={sign.content_template || ''}
                    onChange={(e) => set('sign', 'content_template', e.target.value)}
                    placeholder="{timestamp}{nonce}{body}"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>编码</Label>
                  <Select value={sign.encoding || 'base64'} onValueChange={(v) => set('sign', 'encoding', v)}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="base64">Base64</SelectItem>
                      <SelectItem value="hex">Hex</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}
          </div>

          <div className="space-y-3 rounded-lg border border-zinc-200 bg-zinc-100/40 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-700">请求加密</p>
            <div className="space-y-1.5">
              <Label>加密算法</Label>
              <Select value={enc.algorithm || 'none'} onValueChange={(v) => set('request_encrypt', 'algorithm', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AES_ALGOS.map((a) => (
                    <SelectItem key={a.v} value={a.v}>{a.l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasEnc && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>密钥</Label>
                    <Input type="password" className="font-mono text-xs" value={enc.key || ''} onChange={(e) => set('request_encrypt', 'key', e.target.value)} placeholder="16/24/32 字节" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>IV</Label>
                    <Input type="password" className="font-mono text-xs" value={enc.iv || ''} onChange={(e) => set('request_encrypt', 'iv', e.target.value)} placeholder="16 字节 (ECB 留空)" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>加密范围</Label>
                    <Select value={enc.scope || 'body'} onValueChange={(v) => set('request_encrypt', 'scope', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="body">整个 Body</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>编码</Label>
                    <Select value={enc.encoding || 'base64'} onValueChange={(v) => set('request_encrypt', 'encoding', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="base64">Base64</SelectItem>
                        <SelectItem value="hex">Hex</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="space-y-3 rounded-lg border border-emerald-100 bg-emerald-50/40 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-emerald-600">响应解密</p>
            <div className="space-y-1.5">
              <Label>解密算法</Label>
              <Select value={dec.algorithm || 'none'} onValueChange={(v) => set('response_decrypt', 'algorithm', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AES_ALGOS.map((a) => (
                    <SelectItem key={a.v} value={a.v}>{a.l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasDec && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>密钥</Label>
                    <Input type="password" className="font-mono text-xs" value={dec.key || enc.key || ''} onChange={(e) => set('response_decrypt', 'key', e.target.value)} placeholder="复用请求加密密钥" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>IV</Label>
                    <Input type="password" className="font-mono text-xs" value={dec.iv || enc.iv || ''} onChange={(e) => set('response_decrypt', 'iv', e.target.value)} placeholder="复用请求加密 IV" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>密文路径</Label>
                    <Input className="font-mono text-xs" value={dec.path || ''} onChange={(e) => set('response_decrypt', 'path', e.target.value)} placeholder="data.encrypted" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>编码</Label>
                    <Select value={dec.encoding || 'base64'} onValueChange={(v) => set('response_decrypt', 'encoding', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="base64">Base64</SelectItem>
                        <SelectItem value="hex">Hex</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </>
            )}
          </div>

          {(hasSign || hasEnc) && (
            <div className="space-y-3 rounded-lg border border-[var(--border-subtle)] bg-zinc-50/40 p-3.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">公共参数</p>
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <Label>时间戳字段名</Label>
                  <Input value={common.timestamp_field || ''} onChange={(e) => set('common', 'timestamp_field', e.target.value)} placeholder="timestamp" />
                </div>
                <div className="space-y-1.5">
                  <Label>时间戳格式</Label>
                  <Select value={common.timestamp_format || 'unix'} onValueChange={(v) => set('common', 'timestamp_format', v)}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="unix">Unix 时间戳</SelectItem>
                      <SelectItem value="iso8601">ISO 8601</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>随机数字段名</Label>
                  <Input value={common.nonce_field || ''} onChange={(e) => set('common', 'nonce_field', e.target.value)} placeholder="nonce" />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
