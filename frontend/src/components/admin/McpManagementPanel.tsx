/**
 * MCP 服务器管理面板（集成管理页内）。
 *
 * MCP（Model Context Protocol）让 Agent 接入外部工具的事实标准协议：
 * 管理员在这里维护服务器地址与鉴权头，连接后发现���工具会以
 * `mcp__<server>__<tool>` 进入工具目录，供智能体勾选。
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Loader2, Plug, Plus, Power, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Badge } from '@/components/ui/Badge';
import {
  deleteMcpServer,
  getMcpServers,
  getMcpTools,
  connectMcpServers,
  upsertMcpServer,
  type MCPServer,
} from '@/services/mcpService';
import { cn } from '@/lib/utils';

const EMPTY_FORM = {
  name: '',
  description: '',
  transport: 'http' as MCPServer['transport'],
  url: '',
  command: '',
  timeout: 60,
};

export function McpManagementPanel() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);

  const serversQuery = useQuery({
    queryKey: ['mcp-servers'],
    queryFn: getMcpServers,
    retry: 1,
  });
  const toolsQuery = useQuery({
    queryKey: ['mcp-tools'],
    queryFn: getMcpTools,
    retry: 1,
  });

  const saveMutation = useMutation({
    mutationFn: upsertMcpServer,
    onSuccess: () => {
      toast.success('MCP 服务器已保存');
      setForm(EMPTY_FORM);
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteMcpServer,
    onSuccess: () => {
      toast.success('已删除');
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
  const connectMutation = useMutation({
    mutationFn: connectMcpServers,
    onSuccess: (res) => {
      if (res.connected) {
        toast.success(`连接成功，发现 ${res.tools.length} 个工具`);
      } else {
        toast.error(`连接失败：${res.error ?? '未知原因'}`);
      }
      queryClient.invalidateQueries({ queryKey: ['mcp-tools'] });
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const servers = serversQuery.data?.items ?? [];
  const tools = toolsQuery.data?.tools ?? [];

  const submit = () => {
    if (!form.name.trim()) {
      toast.error('请填写服务器名称');
      return;
    }
    saveMutation.mutate({
      name: form.name.trim(),
      description: form.description.trim(),
      transport: form.transport,
      url: form.transport === 'stdio' ? null : form.url.trim(),
      command: form.transport === 'stdio' ? form.command.trim() : null,
      timeout: Number(form.timeout) || 60,
      enabled: true,
    });
  };

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]/50 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <Plug className="h-4 w-4 text-violet-500" />
              MCP 服务器
            </h3>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              配置后发现的工具会以 mcp__&lt;server&gt;__&lt;tool&gt; 进入工具目录
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => connectMutation.mutate()}
            disabled={connectMutation.isPending}
          >
            {connectMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Power className="h-4 w-4" />
            )}
            连接并发现工具
          </Button>
        </div>

        {/* 新增表单 */}
        <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="服务器名称，如：company-search"
          />
          <select
            value={form.transport}
            onChange={(e) =>
              setForm({ ...form, transport: e.target.value as MCPServer['transport'] })
            }
            className="h-9 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 text-sm"
            aria-label="传输方式"
          >
            <option value="http">http</option>
            <option value="sse">sse</option>
            <option value="stdio">stdio（本地进程）</option>
          </select>
          <Button onClick={submit} disabled={saveMutation.isPending} size="sm">
            <Plus className="h-4 w-4" />
            添加
          </Button>
        </div>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <Input
            value={form.transport === 'stdio' ? form.command : form.url}
            onChange={(e) =>
              setForm(
                form.transport === 'stdio'
                  ? { ...form, command: e.target.value }
                  : { ...form, url: e.target.value },
              )
            }
            placeholder={
              form.transport === 'stdio' ? '启动命令，如 npx' : '服务地址，如 http://127.0.0.1:8931/mcp'
            }
          />
          <Input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="用途说明（可选）"
          />
        </div>
      </div>

      {/* 服务器列表 */}
      {servers.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--muted-foreground)]">
          尚未配置 MCP 服务器
        </p>
      ) : (
        <div className="space-y-2">
          {servers.map((s) => (
            <div
              key={s.name}
              className="flex items-start justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{s.name}</span>
                  <Badge variant="neutral" size="sm">
                    {s.transport}
                  </Badge>
                  {!s.enabled && (
                    <Badge variant="warning" size="sm">
                      已停用
                    </Badge>
                  )}
                </div>
                <p className="mt-0.5 truncate text-[11px] text-[var(--muted-foreground)]">
                  {s.url || s.command}
                </p>
                {s.last_error && (
                  <p className="mt-1 flex items-center gap-1 text-[11px] text-rose-600">
                    <AlertCircle className="h-3 w-3" />
                    {s.last_error}
                  </p>
                )}
              </div>
              <button
                onClick={() => deleteMutation.mutate(s.name)}
                className="shrink-0 rounded-md p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-rose-50 hover:text-rose-600"
                aria-label={`删除 ${s.name}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 已发现的工具 */}
      {tools.length > 0 && (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]/50 p-4">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            已发现工具（{tools.length}）
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {tools.map((t) => (
              <span
                key={t.name}
                className={cn(
                  'rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2 py-1 text-[11px]',
                )}
                title={t.description}
              >
                {t.label || t.name}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-[var(--muted-foreground)]">
            在智能体编辑器的「工具」里勾选后即可使用
          </p>
        </div>
      )}
    </div>
  );
}