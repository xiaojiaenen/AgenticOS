import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, ChevronLeft, ExternalLink, Globe, Key, Loader2, Pencil, Plug, Plus, Save, Shield, TestTube, Trash2, Upload, X } from "lucide-react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";
import { createSystem, updateSystem, deleteSystem, listSystems, listApis, createApi, updateApi, deleteApi, testApi, IntegrationSystem, IntegrationApi, IntegrationSystemPayload, IntegrationApiPayload, IntegrationApiParam, IntegrationTestResult } from "../../services/integrationService";
import { useAdminModalBackdrop } from "./useAdminModalBackdrop";

type SystemDraft = IntegrationSystemPayload & { id?: number };
type ApiDraft = IntegrationApiPayload & { id?: number };
type TestState = { apiId: number; params: Record<string, string>; result: IntegrationTestResult | null; loading: boolean } | null;

const AUTH_TYPES = [{value:"api_key",label:"API Key"},{value:"bearer",label:"Bearer Token"},{value:"basic",label:"Basic Auth"},{value:"oauth2",label:"OAuth 2.0"},{value:"custom",label:"自定义"},{value:"jwt_login",label:"JWT 登录"}];
const METHODS = ["GET","POST","PUT","DELETE","PATCH"];
function emptySystemDraft(): SystemDraft { return {name:"",description:"",base_url:"",auth_type:"api_key",credential_template:{},published:true,headers:{}}; }
function emptyApiDraft(): ApiDraft { return {name:"",display_name:"",description:"",method:"GET",path:"/",requires_approval:false,timeout_seconds:30,params:[]}; }
function methodBadgeColor(m:string){switch(m){case"GET":return"bg-emerald-100 text-emerald-700";case"POST":return"bg-sky-100 text-sky-700";case"PUT":return"bg-amber-100 text-amber-700";case"DELETE":return"bg-rose-100 text-rose-700";case"PATCH":return"bg-violet-100 text-violet-700";default:return"bg-slate-100 text-slate-700"}}
function authTypeLabel(t:string){return AUTH_TYPES.find(a=>a.value===t)?.label||t}
function authTypeIcon(t:string){switch(t){case"api_key":return Key;case"bearer":case"oauth2":return Shield;default:return Globe}}

export const IntegrationManagement = () => {
  const [systems, setSystems] = useState<IntegrationSystem[]>([]);
  const [selectedSystem, setSelectedSystem] = useState<IntegrationSystem | null>(null);
  const [apis, setApis] = useState<IntegrationApi[]>([]);
  const [systemDraft, setSystemDraft] = useState<SystemDraft | null>(null);
  const [apiDraft, setApiDraft] = useState<ApiDraft | null>(null);
  const [isSystemModalOpen, setIsSystemModalOpen] = useState(false);
  const [isApiModalOpen, setIsApiModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [testState, setTestState] = useState<TestState>(null);
  const [openApiModal, setOpenApiModal] = useState(false);
  const [openApiInput, setOpenApiInput] = useState("");
  const [openApiPreview, setOpenApiPreview] = useState<any>(null);
  const [openApiLoading, setOpenApiLoading] = useState(false);
  useAdminModalBackdrop(isSystemModalOpen || isApiModalOpen);
  const enabledCount = useMemo(() => systems.filter(s => s.enabled).length, [systems]);

  const loadSystems = async () => { setIsLoading(true); setError(null); try { const r = await listSystems(); setSystems(r.items); } catch(e){setError(e instanceof Error?e.message:"加载失败");} finally{setIsLoading(false);} };
  const loadApis = async (sid: number) => { try { const r = await listApis(sid); setApis(r.items); } catch(e){setError(e instanceof Error?e.message:"加载接口失败");} };
  useEffect(() => { loadSystems(); }, []);
  useEffect(() => { if(selectedSystem) loadApis(selectedSystem.id); }, [selectedSystem?.id]);

  const openCreateSystem = () => { setSystemDraft(emptySystemDraft()); setIsSystemModalOpen(true); };
  const openEditSystem = (sys: IntegrationSystem) => { setSystemDraft({id:sys.id,name:sys.name,description:sys.description,base_url:sys.base_url,auth_type:sys.auth_type,credential_template:sys.credential_template,oauth_auth_url:sys.oauth_auth_url||undefined,oauth_token_url:sys.oauth_token_url||undefined,oauth_scope:sys.oauth_scope||undefined,jwt_login_url:sys.jwt_login_url||undefined,jwt_request_body_template:sys.jwt_request_body_template||undefined,jwt_response_token_path:sys.jwt_response_token_path||undefined,jwt_response_expires_path:sys.jwt_response_expires_path||undefined,published:sys.published,headers:sys.headers}); setIsSystemModalOpen(true); };
  const handleSaveSystem = async () => { if(!systemDraft)return; setIsSaving(true); setError(null); try { if(systemDraft.id){await updateSystem(systemDraft.id,systemDraft);}else{await createSystem(systemDraft);} setIsSystemModalOpen(false); setMessage(systemDraft.id?"集成已更新":"集成已创建"); setTimeout(()=>setMessage(null),3000); await loadSystems(); } catch(e){setError(e instanceof Error?e.message:"保存失败");} finally{setIsSaving(false);} };
  const handleDeleteSystem = async (sys:IntegrationSystem) => { if(!confirm(`确定删除集成 "${sys.name}"？`))return; try{await deleteSystem(sys.id); if(selectedSystem?.id===sys.id){setSelectedSystem(null);setApis([]);} setMessage("集成已删除");setTimeout(()=>setMessage(null),3000);await loadSystems();}catch(e){setError(e instanceof Error?e.message:"删除失败");} };
  const openCreateApi = () => { setApiDraft(emptyApiDraft()); setIsApiModalOpen(true); };
  const openEditApi = (api:IntegrationApi) => { setApiDraft({id:api.id,name:api.name,display_name:api.display_name,description:api.description,method:api.method,path:api.path,request_body_schema:api.request_body_schema||undefined,response_example:api.response_example||undefined,requires_approval:api.requires_approval,timeout_seconds:api.timeout_seconds,params:api.params}); setIsApiModalOpen(true); };
  const handleSaveApi = async () => { if(!apiDraft||!selectedSystem)return; setIsSaving(true); setError(null); try{if(apiDraft.id){await updateApi(selectedSystem.id,apiDraft.id,apiDraft);}else{await createApi(selectedSystem.id,apiDraft);} setIsApiModalOpen(false); setMessage(apiDraft.id?"接口已更新":"接口已创建");setTimeout(()=>setMessage(null),3000);await loadApis(selectedSystem.id);await loadSystems();}catch(e){setError(e instanceof Error?e.message:"保存失败");}finally{setIsSaving(false);} };
  const handleDeleteApi = async (api:IntegrationApi) => { if(!selectedSystem)return; if(!confirm(`确定删除接口 "${api.display_name}"？`))return; try{await deleteApi(selectedSystem.id,api.id);setMessage("接口已删除");setTimeout(()=>setMessage(null),3000);await loadApis(selectedSystem.id);await loadSystems();}catch(e){setError(e instanceof Error?e.message:"删除失败");} };
  const handleTestApi = async (api:IntegrationApi) => { if(!selectedSystem)return; const p:Record<string,string>={}; api.params.forEach(pp=>{p[pp.name]=pp.default_value||"";}); setTestState({apiId:api.id,params:p,result:null,loading:true}); try{const r=await testApi(selectedSystem.id,api.id,p);setTestState(prev=>prev?{...prev,result:r,loading:false}:null);}catch(e){setTestState(prev=>prev?{...prev,result:{success:false,status_code:0,body:String(e),elapsed_ms:0},loading:false}:null);} };
  const openOpenApiImport = () => { setOpenApiModal(true); setOpenApiInput(""); setOpenApiPreview(null); setError(null); };
  const handlePreviewOpenApi = async () => { if (!openApiInput.trim()) return; setOpenApiLoading(true); setError(null); try { const { previewOpenApiImport: previewFn } = await import("../../services/integrationService"); const isUrl = openApiInput.trim().startsWith("http"); const preview = await previewFn(isUrl ? undefined : openApiInput.trim(), isUrl ? openApiInput.trim() : undefined); setOpenApiPreview(preview); } catch(e) { setError(e instanceof Error ? e.message : "解析失败"); } finally { setOpenApiLoading(false); } };
  const handleConfirmOpenApi = async () => { if (!openApiPreview) return; setIsSaving(true); setError(null); try { const { confirmOpenApiImport: confirmFn } = await import("../../services/integrationService"); await confirmFn(openApiPreview); setOpenApiModal(false); setOpenApiPreview(null); setMessage("导入成功"); setTimeout(() => setMessage(null), 3000); await loadSystems(); } catch(e) { setError(e instanceof Error ? e.message : "导入失败"); } finally { setIsSaving(false); } };

  if(!selectedSystem){
    return (
      <div className="admin-page-stage space-y-5">
        <section className="admin-data-panel">
          <div className="flex items-center justify-between px-5 py-4">
            <div><p className="admin-section-kicker">集成管理</p><h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">第三方集成</h2><p className="mt-1 text-sm text-slate-500">{enabledCount} 个已启用 / {systems.length} 个总计</p></div>
            <div className="flex gap-2"><Button variant="secondary" onClick={openOpenApiImport} className="gap-2"><Upload size={16}/>导入 OpenAPI</Button><Button variant="primary" onClick={openCreateSystem} className="gap-2"><Plus size={16}/>新增集成</Button></div>
          </div>
          {error && <div className="mx-5 mb-4 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700"><AlertCircle size={16}/> {error}</div>}
          {message && <div className="mx-5 mb-4 flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-bold text-emerald-700">{message}</div>}
          {isLoading ? <div className="flex h-40 items-center justify-center gap-3 text-sm font-bold text-slate-500"><Loader2 size={18} className="animate-spin"/> 加载中</div>
           : systems.length===0 ? <div className="flex h-40 flex-col items-center justify-center gap-3 text-sm text-slate-500"><Plug size={32} className="text-slate-300"/><p className="font-bold">暂无集成</p><p>点击「新增集成」创建第一个第三方系统连接</p></div>
           : (
            <div className="overflow-x-auto"><div className="px-5 pb-2 text-xs text-slate-400">点击行进入接口管理 →</div><table className="w-full text-left text-sm">
              <thead><tr className="border-b border-slate-200 text-xs font-black uppercase tracking-wider text-slate-400"><th className="px-5 py-3">名称</th><th className="px-5 py-3">描述</th><th className="px-5 py-3">鉴权</th><th className="px-5 py-3 text-center">接口</th><th className="px-5 py-3 text-center">状态</th><th className="px-5 py-3 text-right">操作</th></tr></thead>
              <tbody>{systems.map(sys=>{const Icon=authTypeIcon(sys.auth_type);return(
                <motion.tr key={sys.id} initial={{opacity:0}} animate={{opacity:1}} className="group cursor-pointer border-b border-slate-100 transition-colors hover:bg-white/60" onClick={()=>setSelectedSystem(sys)}>
                  <td className="px-5 py-3.5"><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/70 bg-white/70 text-slate-600 shadow-sm"><Icon size={18}/></div><div><div className="flex items-center gap-1"><p className="font-black text-slate-900">{sys.name}</p><ChevronLeft size={14} className="rotate-180 text-slate-300 group-hover:text-slate-500 transition-colors"/></div><p className="text-xs text-slate-400">{sys.base_url}</p></div></div></td>
                  <td className="max-w-[200px] truncate px-5 py-3.5 text-slate-600">{sys.description||"-"}</td>
                  <td className="px-5 py-3.5"><span className="rounded-lg bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600">{authTypeLabel(sys.auth_type)}</span></td>
                  <td className="px-5 py-3.5 text-center font-bold text-slate-700">{sys.api_count}</td>
                  <td className="px-5 py-3.5 text-center"><span className={cn("rounded-lg px-2 py-1 text-xs font-bold",sys.enabled&&sys.published?"bg-emerald-100 text-emerald-700":"bg-slate-100 text-slate-500")}>{sys.enabled&&sys.published?"已发布":sys.enabled?"未发布":"已禁用"}</span></td>
                  <td className="px-5 py-3.5 text-right"><div className="flex items-center justify-end gap-1"><Button variant="ghost" size="icon" onClick={e=>{e.stopPropagation();openEditSystem(sys);}}><Pencil size={15}/></Button><Button variant="ghost" size="icon" onClick={e=>{e.stopPropagation();handleDeleteSystem(sys);}}><Trash2 size={15} className="text-rose-500"/></Button></div></td>
                </motion.tr>);})}</tbody>
            </table></div>
          )}
        </section>
        {openApiModal && createPortal(
          <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
            <motion.div initial={{scale:0.95,y:20}} animate={{scale:1,y:0}} className="relative max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-white/60 bg-white p-6 shadow-2xl">
              <div className="flex items-center justify-between"><h3 className="text-lg font-black text-slate-900">从 OpenAPI 导入</h3><Button variant="ghost" size="icon" onClick={() => setOpenApiModal(false)}><X size={18}/></Button></div>
              <div className="mt-5 space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-bold text-slate-700">OpenAPI JSON 或 URL</label>
                  <textarea className="w-full min-h-[120px] rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-mono text-xs shadow-sm focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/20" value={openApiInput} onChange={e => setOpenApiInput(e.target.value)} placeholder="粘贴 OpenAPI JSON 或输入 URL..." />
                </div>
                <Button variant="primary" onClick={handlePreviewOpenApi} disabled={openApiLoading || !openApiInput.trim()} className="gap-2 w-full">{openApiLoading ? <Loader2 size={16} className="animate-spin"/> : <Upload size={16}/>}解析预览</Button>
                {openApiPreview && (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="font-black text-slate-900">{openApiPreview.system_name}</p>
                    <p className="text-sm text-slate-500">{openApiPreview.system_description}</p>
                    <p className="mt-2 text-xs text-slate-600">Base URL: <span className="font-mono">{openApiPreview.base_url}</span></p>
                    <p className="text-xs text-slate-600">鉴权: {openApiPreview.auth_type}</p>
                    <p className="mt-2 text-sm font-bold text-slate-700">{openApiPreview.apis.length} 个接口将被导入:</p>
                    <div className="mt-2 max-h-[200px] overflow-y-auto space-y-1">
                      {openApiPreview.apis.map((a: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className="rounded bg-slate-200 px-1.5 py-0.5 font-black">{a.method}</span>
                          <span className="font-mono text-slate-600">{a.path}</span>
                          <span className="text-slate-400">{a.display_name}</span>
                        </div>
                      ))}
                    </div>
                    <Button variant="primary" onClick={handleConfirmOpenApi} disabled={isSaving} className="gap-2 mt-4 w-full">{isSaving ? <Loader2 size={16} className="animate-spin"/> : <Save size={16}/>}确认导入</Button>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>,
          document.body
        )}
        {isSystemModalOpen && systemDraft && createPortal(<SystemModal draft={systemDraft} setDraft={setSystemDraft} onSave={handleSaveSystem} onClose={()=>setIsSystemModalOpen(false)} isSaving={isSaving}/>, document.body)}
      </div>
    );
  }

  return (
    <div className="admin-page-stage space-y-5">
      <section className="admin-data-panel">
        <div className="flex items-center gap-3 px-5 py-4">
          <Button variant="ghost" size="icon" onClick={()=>{setSelectedSystem(null);setApis([]);}}><ChevronLeft size={20}/></Button>
          <div className="flex-1"><p className="admin-section-kicker">集成详情</p><h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">{selectedSystem.name}</h2><p className="mt-0.5 text-sm text-slate-500">{selectedSystem.description||selectedSystem.base_url}</p></div>
          <Button variant="primary" onClick={openCreateApi} className="gap-2"><Plus size={16}/>新增接口</Button>
        </div>
        {error && <div className="mx-5 mb-4 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700"><AlertCircle size={16}/> {error}</div>}
        {apis.length===0 ? <div className="flex h-40 flex-col items-center justify-center gap-3 text-sm text-slate-500"><ExternalLink size={32} className="text-slate-300"/><p className="font-bold">暂无接口</p><p>为 {selectedSystem.name} 定义可用的 API 接口</p></div>
        : (
          <div className="overflow-x-auto"><table className="w-full text-left text-sm">
            <thead><tr className="border-b border-slate-200 text-xs font-black uppercase tracking-wider text-slate-400"><th className="px-5 py-3">接口</th><th className="px-5 py-3">方法</th><th className="px-5 py-3">路径</th><th className="px-5 py-3 text-center">参数</th><th className="px-5 py-3 text-center">审批</th><th className="px-5 py-3 text-right">操作</th></tr></thead>
            <tbody>{apis.map(api=>(
              <motion.tr key={api.id} initial={{opacity:0}} animate={{opacity:1}} className="border-b border-slate-100 transition-colors hover:bg-white/60">
                <td className="px-5 py-3.5"><p className="font-bold text-slate-900">{api.display_name}</p><p className="text-xs text-slate-400">{api.name}</p></td>
                <td className="px-5 py-3.5"><span className={cn("rounded-lg px-2 py-1 text-xs font-black",methodBadgeColor(api.method))}>{api.method}</span></td>
                <td className="max-w-[250px] truncate px-5 py-3.5 font-mono text-xs text-slate-600">{api.path}</td>
                <td className="px-5 py-3.5 text-center font-bold text-slate-700">{api.params.length}</td>
                <td className="px-5 py-3.5 text-center">{api.requires_approval&&<span className="rounded-lg bg-amber-100 px-2 py-1 text-xs font-bold text-amber-700">需审批</span>}</td>
                <td className="px-5 py-3.5 text-right"><div className="flex items-center justify-end gap-1"><Button variant="ghost" size="icon" onClick={()=>handleTestApi(api)} title="测试"><TestTube size={15}/></Button><Button variant="ghost" size="icon" onClick={()=>openEditApi(api)}><Pencil size={15}/></Button><Button variant="ghost" size="icon" onClick={()=>handleDeleteApi(api)}><Trash2 size={15} className="text-rose-500"/></Button></div></td>
              </motion.tr>))}</tbody>
          </table></div>
        )}
      </section>
      {testState && createPortal(<TestDrawer state={testState} api={apis.find(a=>a.id===testState.apiId)} onClose={()=>setTestState(null)} onParamChange={(n,v)=>setTestState(prev=>prev?{...prev,params:{...prev.params,[n]:v}}:null)} onRun={()=>{const a=apis.find(x=>x.id===testState.apiId);if(a)handleTestApi(a);}}/>, document.body)}
      {isApiModalOpen && apiDraft && createPortal(<ApiModal draft={apiDraft} setDraft={setApiDraft} onSave={handleSaveApi} onClose={()=>setIsApiModalOpen(false)} isSaving={isSaving}/>, document.body)}
    </div>
  );
};

function SystemModal({draft,setDraft,onSave,onClose,isSaving}:{draft:SystemDraft;setDraft:(d:SystemDraft)=>void;onSave:()=>void;onClose:()=>void;isSaving:boolean}){
  return(
    <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <motion.div initial={{scale:0.95,y:20}} animate={{scale:1,y:0}} className="relative max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-3xl border border-white/60 bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between"><h3 className="text-lg font-black text-slate-900">{draft.id?"编辑集成":"新增集成"}</h3><Button variant="ghost" size="icon" onClick={onClose}><X size={18}/></Button></div>
        <div className="mt-5 space-y-4">
          <Field label="名称" required><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder="如 Jira、GitHub"/></Field>
          <Field label="描述"><textarea className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 min-h-[60px] resize-y" value={draft.description} onChange={e=>setDraft({...draft,description:e.target.value})}/></Field>
          <Field label="Base URL" required><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.base_url} onChange={e=>setDraft({...draft,base_url:e.target.value})} placeholder="https://api.example.com"/></Field>
          <Field label="鉴权类型"><select className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80" value={draft.auth_type} onChange={e=>setDraft({...draft,auth_type:e.target.value})}>{AUTH_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></Field>
          {draft.auth_type==="oauth2"&&(<>
            <Field label="OAuth Client ID"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.oauth_client_id||""} onChange={e=>setDraft({...draft,oauth_client_id:e.target.value})}/></Field>
            <Field label="OAuth Client Secret"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" type="password" value={draft.oauth_client_secret||""} onChange={e=>setDraft({...draft,oauth_client_secret:e.target.value})}/></Field>
            <Field label="授权 URL"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.oauth_auth_url||""} onChange={e=>setDraft({...draft,oauth_auth_url:e.target.value})} placeholder="https://..."/></Field>
            <Field label="Token URL"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.oauth_token_url||""} onChange={e=>setDraft({...draft,oauth_token_url:e.target.value})} placeholder="https://..."/></Field>
            <Field label="Scope"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80" value={draft.oauth_scope||""} onChange={e=>setDraft({...draft,oauth_scope:e.target.value})}/></Field>
          </>)}
          {draft.auth_type==="jwt_login"&&(<>
            <Field label="登录地址"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.jwt_login_url||""} onChange={e=>setDraft({...draft,jwt_login_url:e.target.value})} placeholder="https://api.internal.com/auth/login"/></Field>
            <Field label="请求体模板"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-xs" value={draft.jwt_request_body_template||""} onChange={e=>setDraft({...draft,jwt_request_body_template:e.target.value})} placeholder='{"username":"{username}","password":"{password}"}'/></Field>
            <Field label="Token 路径"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-xs" value={draft.jwt_response_token_path||""} onChange={e=>setDraft({...draft,jwt_response_token_path:e.target.value})} placeholder="data.access_token"/></Field>
            <Field label="过期时间路径"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-xs" value={draft.jwt_response_expires_path||""} onChange={e=>setDraft({...draft,jwt_response_expires_path:e.target.value})} placeholder="data.expires_in (可选)"/></Field>
          </>)}
          <Field label="凭据模板 (JSON)"><textarea className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 min-h-[100px] resize-y font-mono text-xs" value={JSON.stringify(draft.credential_template,null,2)} onChange={e=>{try{setDraft({...draft,credential_template:JSON.parse(e.target.value)})}catch{}}} placeholder='{"fields": [{"key": "token", "label": "API Token", "type": "password", "required": true}]}'/></Field>
          <label className="flex items-center gap-2 text-sm font-bold text-slate-700"><input type="checkbox" checked={draft.published} onChange={e=>setDraft({...draft,published:e.target.checked})} className="rounded"/>发布（用户可见）</label>
        </div>
        <div className="mt-6 flex justify-end gap-3"><Button variant="secondary" onClick={onClose}>取消</Button><Button variant="primary" onClick={onSave} disabled={isSaving||!draft.name||!draft.base_url} className="gap-2">{isSaving?<Loader2 size={16} className="animate-spin"/>:<Save size={16}/>}{draft.id?"更新":"创建"}</Button></div>
      </motion.div>
    </motion.div>
  );
}

function ApiModal({draft,setDraft,onSave,onClose,isSaving}:{draft:ApiDraft;setDraft:(d:ApiDraft)=>void;onSave:()=>void;onClose:()=>void;isSaving:boolean}){
  const updateParam=(i:number,f:keyof IntegrationApiParam,v:string|boolean)=>{const p=[...draft.params];p[i]={...p[i],[f]:v};setDraft({...draft,params:p});};
  const addParam=()=>setDraft({...draft,params:[...draft.params,{name:"",param_type:"query",data_type:"string",required:false,description:"",default_value:null}]});
  const removeParam=(i:number)=>setDraft({...draft,params:draft.params.filter((_,x)=>x!==i)});
  return(
    <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <motion.div initial={{scale:0.95,y:20}} animate={{scale:1,y:0}} className="relative max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-white/60 bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between"><h3 className="text-lg font-black text-slate-900">{draft.id?"编辑接口":"新增接口"}</h3><Button variant="ghost" size="icon" onClick={onClose}><X size={18}/></Button></div>
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-4"><Field label="名称" required><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder="search_issues"/></Field><Field label="展示名" required><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80" value={draft.display_name} onChange={e=>setDraft({...draft,display_name:e.target.value})} placeholder="搜索工单"/></Field></div>
          <Field label="描述"><textarea className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 min-h-[60px] resize-y" value={draft.description} onChange={e=>setDraft({...draft,description:e.target.value})}/></Field>
          <div className="grid grid-cols-2 gap-4"><Field label="方法"><select className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80" value={draft.method} onChange={e=>setDraft({...draft,method:e.target.value})}>{METHODS.map(m=><option key={m} value={m}>{m}</option>)}</select></Field><Field label="路径" required><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 font-mono text-sm" value={draft.path} onChange={e=>setDraft({...draft,path:e.target.value})} placeholder="/rest/api/2/issue/{id}"/></Field></div>
          <div className="grid grid-cols-2 gap-4"><Field label="超时(秒)"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80" type="number" value={draft.timeout_seconds} onChange={e=>setDraft({...draft,timeout_seconds:Number(e.target.value)})}/></Field><div className="flex items-end pb-1"><label className="flex items-center gap-2 text-sm font-bold text-slate-700"><input type="checkbox" checked={draft.requires_approval} onChange={e=>setDraft({...draft,requires_approval:e.target.checked})} className="rounded"/>需要审批</label></div></div>
          <div>
            <div className="mb-2 flex items-center justify-between"><span className="text-sm font-bold text-slate-700">参数</span><Button variant="ghost" size="sm" onClick={addParam} className="gap-1"><Plus size={14}/>添加</Button></div>
            {draft.params.length===0&&<p className="text-xs text-slate-400">暂无参数</p>}
            {draft.params.map((p,i)=>(
              <div key={i} className="mb-2 rounded-2xl border border-slate-200 bg-white/50 p-3">
                <div className="grid grid-cols-4 gap-2"><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 text-sm" placeholder="参数名" value={p.name} onChange={e=>updateParam(i,"name",e.target.value)}/><select className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 text-sm" value={p.param_type} onChange={e=>updateParam(i,"param_type",e.target.value)}><option value="path">path</option><option value="query">query</option><option value="body">body</option></select><select className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 text-sm" value={p.data_type} onChange={e=>updateParam(i,"data_type",e.target.value)}><option value="string">string</option><option value="integer">integer</option><option value="boolean">boolean</option><option value="object">object</option></select><div className="flex items-center gap-2"><label className="flex items-center gap-1 text-xs text-slate-600"><input type="checkbox" checked={p.required} onChange={e=>updateParam(i,"required",e.target.checked)} className="rounded"/>必填</label><Button variant="ghost" size="icon" onClick={()=>removeParam(i)}><Trash2 size={14} className="text-rose-500"/></Button></div></div>
                <input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 mt-2 text-xs" placeholder="说明" value={p.description} onChange={e=>updateParam(i,"description",e.target.value)}/>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-3"><Button variant="secondary" onClick={onClose}>取消</Button><Button variant="primary" onClick={onSave} disabled={isSaving||!draft.name||!draft.path} className="gap-2">{isSaving?<Loader2 size={16} className="animate-spin"/>:<Save size={16}/>}{draft.id?"更新":"创建"}</Button></div>
      </motion.div>
    </motion.div>
  );
}

function TestDrawer({state,api,onClose,onParamChange,onRun}:{state:TestState;api:IntegrationApi|undefined;onClose:()=>void;onParamChange:(n:string,v:string)=>void;onRun:()=>void}){
  if(!state||!api)return null;
  return(
    <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex justify-end bg-black/20">
      <motion.div initial={{x:400}} animate={{x:0}} className="h-full w-full max-w-md overflow-y-auto border-l border-white/60 bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between"><h3 className="text-lg font-black text-slate-900">测试: {api.display_name}</h3><Button variant="ghost" size="icon" onClick={onClose}><X size={18}/></Button></div>
        <div className="mt-5 space-y-3">
          {api.params.map(p=>(<Field key={p.name} label={p.name} required={p.required}><input className="w-full rounded-2xl border border-white/75 bg-white/72 px-5 py-3.5 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 text-sm" value={state.params[p.name]||""} onChange={e=>onParamChange(p.name,e.target.value)} placeholder={p.description||p.name}/></Field>))}
          <Button variant="primary" onClick={onRun} disabled={state.loading} className="gap-2 w-full">{state.loading?<Loader2 size={16} className="animate-spin"/>:<TestTube size={16}/>}发送请求</Button>
        </div>
        {state.result&&(
          <div className="mt-5">
            <div className={cn("rounded-2xl border p-4",state.result.success?"border-emerald-200 bg-emerald-50":"border-rose-200 bg-rose-50")}>
              <div className="flex items-center justify-between"><span className={cn("text-sm font-black",state.result.success?"text-emerald-700":"text-rose-700")}>{state.result.success?"成功":"失败"} {state.result.status_code>0&&`(${state.result.status_code})`}</span><span className="text-xs text-slate-500">{state.result.elapsed_ms}ms</span></div>
              <pre className="mt-3 max-h-[300px] overflow-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">{state.result.body}</pre>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

function Field({label,required,children}:{label:string;required?:boolean;children:React.ReactNode}){return(<div><label className="mb-1 block text-sm font-bold text-slate-700">{label} {required&&<span className="text-rose-500">*</span>}</label>{children}</div>);}
