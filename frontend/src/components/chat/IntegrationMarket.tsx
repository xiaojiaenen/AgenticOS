import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { AlertCircle, CheckCircle, ExternalLink, Globe, Key, Loader2, Plug, Shield, Unplug, X } from "lucide-react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";
import { listIntegrations, connectIntegration, disconnectIntegration, listMyConnections, IntegrationSystem, UserConnection, CredentialField } from "../../services/integrationService";

interface IntegrationMarketProps {
  open: boolean;
  onClose: () => void;
}

function authTypeIcon(t: string) {
  switch (t) { case "api_key": return Key; case "bearer": case "oauth2": return Shield; default: return Globe; }
}

function authTypeLabel(t: string) {
  const map: Record<string, string> = { api_key: "API Key", bearer: "Bearer Token", basic: "Basic Auth", oauth2: "OAuth 2.0", custom: "自定义" };
  return map[t] || t;
}

function getCredentialFields(system: IntegrationSystem): CredentialField[] {
  const tpl = system.credential_template;
  if (tpl && Array.isArray((tpl as any).fields)) return (tpl as any).fields as CredentialField[];
  if (tpl && typeof tpl === "object") {
    return Object.entries(tpl).map(([key, val]) => {
      if (typeof val === "object" && val !== null) return { key, ...(val as Record<string, unknown>) } as CredentialField;
      return { key, label: key, type: "text", required: true } as CredentialField;
    });
  }
  switch (system.auth_type) {
    case "api_key": return [{ key: "key", label: "API Key", type: "password", required: true }];
    case "bearer": return [{ key: "token", label: "Token", type: "password", required: true }];
    case "basic": return [{ key: "username", label: "用户名", type: "text", required: true }, { key: "password", label: "密码", type: "password", required: true }];
    default: return [{ key: "token", label: "凭据", type: "password", required: true }];
  }
}

export const IntegrationMarket: React.FC<IntegrationMarketProps> = ({ open, onClose }) => {
  const [systems, setSystems] = useState<IntegrationSystem[]>([]);
  const [connections, setConnections] = useState<Map<number, UserConnection>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectingSystem, setConnectingSystem] = useState<IntegrationSystem | null>(null);
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
  const [isConnecting, setIsConnecting] = useState(false);

  const loadData = async () => {
    setIsLoading(true); setError(null);
    try {
      const [sysResp, connResp] = await Promise.all([listIntegrations(), listMyConnections()]);
      setSystems(sysResp.items);
      const connMap = new Map<number, UserConnection>();
      connResp.items.forEach((c) => connMap.set(c.system_id, c));
      setConnections(connMap);
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setIsLoading(false); }
  };

  useEffect(() => { if (open) loadData(); }, [open]);

  const handleConnect = async () => {
    if (!connectingSystem) return;
    setIsConnecting(true); setError(null);
    try {
      const conn = await connectIntegration(connectingSystem.id, credentialValues);
      setConnections((prev) => new Map(prev).set(connectingSystem.id, conn));
      setConnectingSystem(null); setCredentialValues({});
    } catch (e) { setError(e instanceof Error ? e.message : "连接失败"); } finally { setIsConnecting(false); }
  };

  const handleDisconnect = async (systemId: number) => {
    try {
      await disconnectIntegration(systemId);
      setConnections((prev) => { const m = new Map(prev); m.delete(systemId); return m; });
    } catch (e) { setError(e instanceof Error ? e.message : "断开失败"); }
  };

  const openConnect = (sys: IntegrationSystem) => { setConnectingSystem(sys); setCredentialValues({}); setError(null); };

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} onClick={(e) => e.stopPropagation()} className="relative flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-white/60 bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <div><h2 className="text-lg font-black text-slate-900">集成市场</h2><p className="text-sm text-slate-500">连接第三方服务，扩展智能体能力</p></div>
            <Button variant="ghost" size="icon" onClick={onClose}><X size={18} /></Button>
          </div>

          {error && <div className="mx-6 mt-4 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700"><AlertCircle size={16} /> {error}</div>}

          <div className="flex-1 overflow-y-auto p-6">
            {isLoading ? <div className="flex h-40 items-center justify-center gap-3 text-sm font-bold text-slate-500"><Loader2 size={18} className="animate-spin" /> 加载中</div>
            : systems.length === 0 ? <div className="flex h-40 flex-col items-center justify-center gap-3 text-sm text-slate-500"><Plug size={32} className="text-slate-300" /><p className="font-bold">暂无可用集成</p><p>管理员尚未发布任何集成</p></div>
            : (
              <div className="grid gap-4 sm:grid-cols-2">
                {systems.map((sys) => {
                  const conn = connections.get(sys.id);
                  const Icon = authTypeIcon(sys.auth_type);
                  const isConnected = conn?.connection_status === "connected";
                  const isError = conn?.connection_status === "auth_error" || conn?.connection_status === "expired";
                  return (
                    <motion.div key={sys.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-all hover:shadow-md">
                      <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-600"><Icon size={20} /></div>
                        <div className="flex-1 min-w-0"><p className="font-black text-slate-900">{sys.name}</p><p className="mt-0.5 text-xs text-slate-500 line-clamp-2">{sys.description || sys.base_url}</p></div>
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-2"><span className="rounded-lg bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">{authTypeLabel(sys.auth_type)}</span><span className="text-[10px] text-slate-400">{sys.api_count} 个接口</span></div>
                        {isConnected ? (
                          <div className="flex items-center gap-1"><span className="flex items-center gap-1 rounded-lg bg-emerald-50 px-2 py-1 text-xs font-bold text-emerald-700"><CheckCircle size={12} /> 已连接</span><Button variant="ghost" size="sm" onClick={() => handleDisconnect(sys.id)} className="text-xs text-slate-400 hover:text-rose-500"><Unplug size={14} /></Button></div>
                        ) : isError ? (
                          <Button variant="outline" size="sm" onClick={() => openConnect(sys)} className="gap-1 text-xs text-amber-600 border-amber-300"><AlertCircle size={14} /> 重新连接</Button>
                        ) : (
                          <Button variant="primary" size="sm" onClick={() => openConnect(sys)} className="gap-1 text-xs"><Plug size={14} /> 连接</Button>
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>

      {connectingSystem && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onClick={() => setConnectingSystem(null)}>
          <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-3xl border border-white/60 bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-black text-slate-900">连接 {connectingSystem.name}</h3>
            <p className="mt-1 text-sm text-slate-500">{connectingSystem.description}</p>
            <div className="mt-5 space-y-3">
              {getCredentialFields(connectingSystem).map((field) => (
                <div key={field.key}>
                  <label className="mb-1 block text-sm font-bold text-slate-700">{field.label} {field.required && <span className="text-rose-500">*</span>}</label>
                  <input className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm transition-all focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/20" type={field.type === "password" ? "password" : "text"} value={credentialValues[field.key] || ""} onChange={(e) => setCredentialValues((prev) => ({ ...prev, [field.key]: e.target.value }))} placeholder={field.placeholder || ""} />
                  {field.help_text && <p className="mt-1 text-xs text-slate-400">{field.help_text}</p>}
                  {field.help_url && <a href={field.help_url} target="_blank" rel="noopener" className="mt-1 inline-flex items-center gap-1 text-xs text-sky-600 hover:underline"><ExternalLink size={10} /> 获取帮助</a>}
                </div>
              ))}
            </div>
            <div className="mt-6 flex justify-end gap-3"><Button variant="secondary" onClick={() => setConnectingSystem(null)}>取消</Button><Button variant="primary" onClick={handleConnect} disabled={isConnecting} className="gap-2">{isConnecting ? <Loader2 size={16} className="animate-spin" /> : <Plug size={16} />}连接</Button></div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
