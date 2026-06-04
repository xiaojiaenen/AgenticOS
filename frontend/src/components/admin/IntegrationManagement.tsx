import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, ChevronLeft, ExternalLink, Globe, Key, Loader2, Pencil, Plug, Plus, Save, Shield, TestTube, Trash2, Upload, X } from "lucide-react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";
import { createSystem, updateSystem, deleteSystem, listSystems, listApis, createApi, updateApi, deleteApi, testApi, IntegrationSystem, IntegrationApi, IntegrationSystemPayload, IntegrationApiPayload, IntegrationApiParam, IntegrationTestResult, CredentialField } from "../../services/integrationService";
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
  const openEditSystem = (sys: IntegrationSystem) => { setSystemDraft({id:sys.id,name:sys.name,description:sys.description,base_url:sys.base_url,auth_type:sys.auth_type,credential_template:sys.credential_template,oauth_auth_url:sys.oauth_auth_url||undefined,oauth_token_url:sys.oauth_token_url||undefined,oauth_scope:sys.oauth_scope||undefined,oauth_refresh_token_url:(sys as any).oauth_refresh_token_url||undefined,jwt_login_url:sys.jwt_login_url||undefined,jwt_refresh_url:sys.jwt_refresh_url||undefined,jwt_refresh_body_template:sys.jwt_refresh_body_template||undefined,jwt_refresh_token_path:sys.jwt_refresh_token_path||undefined,jwt_request_body_template:sys.jwt_request_body_template||undefined,jwt_response_token_path:sys.jwt_response_token_path||undefined,jwt_response_expires_path:sys.jwt_response_expires_path||undefined,published:sys.published,headers:sys.headers,advanced_auth:sys.advanced_auth||{}}); setIsSystemModalOpen(true); };
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
            <div className="overflow-x-auto"><table className="w-full text-left text-sm">
              <thead><tr className="border-b border-slate-200 text-xs font-black uppercase tracking-wider text-slate-400"><th className="px-5 py-3">名称</th><th className="px-5 py-3">描述</th><th className="px-5 py-3">鉴权</th><th className="px-5 py-3 text-center">接口</th><th className="px-5 py-3 text-center">状态</th><th className="px-5 py-3 text-right">操作</th></tr></thead>
              <tbody>{systems.map(sys=>{const Icon=authTypeIcon(sys.auth_type);return(
                <motion.tr key={sys.id} initial={{opacity:0}} animate={{opacity:1}} className="cursor-pointer border-b border-slate-100 transition-colors hover:bg-white/60" onClick={()=>setSelectedSystem(sys)}>
                  <td className="px-5 py-3.5"><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/70 bg-white/70 text-slate-600 shadow-sm"><Icon size={18}/></div><div><p className="font-black text-slate-900">{sys.name}</p><p className="text-xs text-slate-400">{sys.base_url}</p></div></div></td>
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
          <div className="admin-modal-shell" onMouseDown={() => setOpenApiModal(false)}>
            <motion.div initial={{opacity:0,y:24,scale:0.96}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:24,scale:0.96}} transition={{duration:0.22}} onMouseDown={e=>e.stopPropagation()} className="admin-solid-panel admin-modal-panel flex max-h-[min(88vh,900px)] w-full max-w-2xl flex-col overflow-hidden">
              <div className="flex items-center justify-between px-6 pt-5 pb-0">
                <div><p className="admin-section-kicker">快速导入</p><h3 className="mt-1.5 text-xl font-black tracking-tight text-slate-900">从 OpenAPI 导入</h3></div>
                <button type="button" onClick={() => setOpenApiModal(false)} className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600"><X size={19}/></button>
              </div>
              <div className="flex-1 overflow-y-auto px-6 pt-5 pb-6 space-y-4">
                <Field label="OpenAPI JSON 或 URL"><textarea className="admin-input min-h-[120px] resize-y font-mono text-xs" value={openApiInput} onChange={e => setOpenApiInput(e.target.value)} placeholder="粘贴 OpenAPI JSON 内容或输入 URL..." /></Field>
                <Button variant="primary" onClick={handlePreviewOpenApi} disabled={openApiLoading || !openApiInput.trim()} className="gap-2 w-full">{openApiLoading ? <Loader2 size={16} className="animate-spin"/> : <Upload size={16}/>}解析预览</Button>
                {openApiPreview && (
                  <div className="rounded-2xl border border-sky-100 bg-sky-50/50 p-4 space-y-2">
                    <p className="font-black text-slate-900">{openApiPreview.system_name}</p>
                    <p className="text-sm text-slate-500">{openApiPreview.system_description}</p>
                    <div className="flex items-center gap-4 text-xs text-slate-600">
                      <span>Base URL: <span className="font-mono">{openApiPreview.base_url}</span></span>
                      <span>鉴权: {openApiPreview.auth_type}</span>
                    </div>
                    <p className="text-sm font-bold text-slate-700">{openApiPreview.apis.length} 个接口将被导入:</p>
                    <div className="max-h-[200px] overflow-y-auto space-y-1">
                      {openApiPreview.apis.map((a: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className={cn("rounded-lg px-1.5 py-0.5 font-black", methodBadgeColor(a.method))}>{a.method}</span>
                          <span className="font-mono text-slate-600">{a.path}</span>
                          <span className="text-slate-400">{a.display_name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {openApiPreview && (
                <div className="flex items-center justify-end gap-3 border-t border-slate-100 px-6 py-4">
                  <Button variant="secondary" onClick={() => setOpenApiModal(false)}>取消</Button>
                  <Button variant="primary" onClick={handleConfirmOpenApi} disabled={isSaving} className="gap-2">{isSaving ? <Loader2 size={16} className="animate-spin"/> : <Save size={16}/>}确认导入</Button>
                </div>
              )}
            </motion.div>
          </div>,
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
  // credential_template 可视化编辑
  const credFields = useMemo(() => {
    const fields = draft.credential_template?.fields;
    return Array.isArray(fields) ? fields as CredentialField[] : [];
  }, [draft.credential_template]);
  const updateCredField = (i: number, key: keyof CredentialField, val: string | boolean) => {
    const fields = [...credFields]; fields[i] = { ...fields[i], [key]: val };
    setDraft({ ...draft, credential_template: { fields } });
  };
  const addCredField = () => setDraft({ ...draft, credential_template: { fields: [...credFields, { key: "", label: "", type: "text", required: true, placeholder: "" }] } });
  const removeCredField = (i: number) => { const f = credFields.filter((_, x) => x !== i); setDraft({ ...draft, credential_template: { fields: f } }); };

  // jwt_request_body_template key-value 编辑
  const jwtPairs = useMemo(() => {
    try { return Object.entries(JSON.parse(draft.jwt_request_body_template || "{}")).map(([k, v]) => ({ key: k, value: String(v) })); } catch { return []; }
  }, [draft.jwt_request_body_template]);
  const updateJwtPair = (i: number, field: "key" | "value", val: string) => {
    const pairs = [...jwtPairs]; pairs[i] = { ...pairs[i], [field]: val };
    setDraft({ ...draft, jwt_request_body_template: JSON.stringify(Object.fromEntries(pairs.map(p => [p.key, p.value]))) });
  };
  const addJwtPair = () => { const pairs = [...jwtPairs, { key: "", value: "" }]; setDraft({ ...draft, jwt_request_body_template: JSON.stringify(Object.fromEntries(pairs.map(p => [p.key, p.value]))) }); };
  const removeJwtPair = (i: number) => { const pairs = jwtPairs.filter((_, x) => x !== i); setDraft({ ...draft, jwt_request_body_template: JSON.stringify(Object.fromEntries(pairs.map(p => [p.key, p.value]))) }); };

  return createPortal(
    <div className="admin-modal-shell" onMouseDown={onClose}>
      <motion.div initial={{opacity:0,y:24,scale:0.96}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:24,scale:0.96}} transition={{duration:0.22}} onMouseDown={e=>e.stopPropagation()} className="admin-solid-panel admin-modal-panel flex max-h-[min(88vh,900px)] w-full max-w-xl flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 pt-5 pb-0">
          <div><p className="admin-section-kicker">集成配置</p><h3 className="mt-1.5 text-xl font-black tracking-tight text-slate-900">{draft.id?"编辑集成":"新增集成"}</h3></div>
          <button type="button" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600"><X size={19}/></button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 pt-5 pb-6 space-y-5">
          <SectionTitle title="基本信息"/>
          <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
            <Field label="名称" required><input className="admin-input" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder="如 Jira、GitHub"/></Field>
            <Field label="Base URL" required><input className="admin-input font-mono text-sm" value={draft.base_url} onChange={e=>setDraft({...draft,base_url:e.target.value})} placeholder="https://api.example.com"/></Field>
          </div>
          <Field label="描述"><textarea className="admin-input min-h-[56px] resize-y" value={draft.description} onChange={e=>setDraft({...draft,description:e.target.value})} placeholder="简要描述该系统的用途"/></Field>

          <SectionTitle title="鉴权方式"/>
          <Field label="鉴权类型"><select className="admin-input" value={draft.auth_type} onChange={e=>setDraft({...draft,auth_type:e.target.value})}>{AUTH_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></Field>

          {draft.auth_type==="oauth2"&&(
            <div className="rounded-2xl border border-sky-100 bg-sky-50/50 p-4 space-y-3">
              <p className="text-xs font-black tracking-wider text-sky-500 uppercase">OAuth 2.0 配置</p>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Field label="Client ID" required><input className="admin-input font-mono text-sm" value={draft.oauth_client_id||""} onChange={e=>setDraft({...draft,oauth_client_id:e.target.value})} placeholder="应用 Client ID"/></Field>
                <Field label="Client Secret" required><input className="admin-input font-mono text-sm" type="password" value={draft.oauth_client_secret||""} onChange={e=>setDraft({...draft,oauth_client_secret:e.target.value})} placeholder="应用 Client Secret"/></Field>
              </div>
              <Field label="授权 URL" required><input className="admin-input font-mono text-sm" value={draft.oauth_auth_url||""} onChange={e=>setDraft({...draft,oauth_auth_url:e.target.value})} placeholder="https://.../authorize"/></Field>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Field label="Token URL" required><input className="admin-input font-mono text-sm" value={draft.oauth_token_url||""} onChange={e=>setDraft({...draft,oauth_token_url:e.target.value})} placeholder="https://.../token"/></Field>
                <Field label="Refresh Token URL"><input className="admin-input font-mono text-sm" value={draft.oauth_refresh_token_url||""} onChange={e=>setDraft({...draft,oauth_refresh_token_url:e.target.value})} placeholder="留空则使用 Token URL"/></Field>
              </div>
              <Field label="Scope"><input className="admin-input" value={draft.oauth_scope||""} onChange={e=>setDraft({...draft,oauth_scope:e.target.value})} placeholder="read write"/></Field>
            </div>
          )}

          {draft.auth_type==="jwt_login"&&(
            <div className="rounded-2xl border border-violet-100 bg-violet-50/50 p-4 space-y-3">
              <p className="text-xs font-black tracking-wider text-violet-500 uppercase">JWT 登录配置</p>
              <Field label="登录地址" required><input className="admin-input font-mono text-sm" value={draft.jwt_login_url||""} onChange={e=>setDraft({...draft,jwt_login_url:e.target.value})} placeholder="https://api.internal.com/auth/login"/></Field>
              <Field label="刷新地址"><input className="admin-input font-mono text-sm" value={draft.jwt_refresh_url||""} onChange={e=>setDraft({...draft,jwt_refresh_url:e.target.value})} placeholder="https://api.internal.com/auth/refresh (可选)"/></Field>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Field label="刷新请求体模板"><input className="admin-input font-mono text-xs" value={draft.jwt_refresh_body_template||""} onChange={e=>setDraft({...draft,jwt_refresh_body_template:e.target.value})} placeholder='{"grant_type":"refresh_token","refresh_token":"{refresh_token}"}' /></Field>
                <Field label="Refresh Token 路径"><input className="admin-input font-mono text-xs" value={draft.jwt_refresh_token_path||""} onChange={e=>setDraft({...draft,jwt_refresh_token_path:e.target.value})} placeholder="refresh_token (默认)"/></Field>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-sm font-bold text-slate-700">请求体字段</label>
                  <button type="button" onClick={addJwtPair} className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-sky-600 transition-colors hover:bg-sky-50"><Plus size={13}/>添加字段</button>
                </div>
                {jwtPairs.length===0 && <p className="text-xs text-slate-400">暂无字段，点击「添加字段」定义登录请求体</p>}
                {jwtPairs.map((p,i)=>(
                  <div key={i} className="mb-2 flex items-center gap-2">
                    <input className="admin-input flex-1 font-mono text-sm" placeholder="字段名 (如 username)" value={p.key} onChange={e=>updateJwtPair(i,"key",e.target.value)}/>
                    <input className="admin-input flex-1 font-mono text-sm" placeholder="值模板 (如 {username})" value={p.value} onChange={e=>updateJwtPair(i,"value",e.target.value)}/>
                    <button type="button" onClick={()=>removeJwtPair(i)} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"><Trash2 size={15}/></button>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Field label="Token 路径"><input className="admin-input font-mono text-xs" value={draft.jwt_response_token_path||""} onChange={e=>setDraft({...draft,jwt_response_token_path:e.target.value})} placeholder="data.access_token"/></Field>
                <Field label="过期时间路径"><input className="admin-input font-mono text-xs" value={draft.jwt_response_expires_path||""} onChange={e=>setDraft({...draft,jwt_response_expires_path:e.target.value})} placeholder="data.expires_in (可选)"/></Field>
              </div>
            </div>
          )}

          <SectionTitle title="用户凭据"/>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-bold text-slate-700">凭据字段</label>
              <button type="button" onClick={addCredField} className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-sky-600 transition-colors hover:bg-sky-50"><Plus size={13}/>添加字段</button>
            </div>
            <p className="mb-3 text-xs text-slate-400">定义用户连接此系统时需要填写的凭据信息</p>
            {credFields.length===0 && <p className="rounded-xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-400">暂无凭据字段</p>}
            {credFields.map((f,i)=>(
              <div key={i} className="mb-2 rounded-2xl border border-slate-200 bg-white/60 p-3">
                <div className="grid grid-cols-4 gap-2">
                  <input className="admin-input text-sm" placeholder="字段标识 (key)" value={f.key} onChange={e=>updateCredField(i,"key",e.target.value)}/>
                  <input className="admin-input text-sm" placeholder="显示名称" value={f.label} onChange={e=>updateCredField(i,"label",e.target.value)}/>
                  <select className="admin-input text-sm" value={f.type} onChange={e=>updateCredField(i,"type",e.target.value)}><option value="text">文本</option><option value="password">密码</option><option value="url">URL</option><option value="email">邮箱</option></select>
                  <div className="flex items-center gap-2"><label className="flex items-center gap-1 text-xs text-slate-600"><input type="checkbox" checked={f.required} onChange={e=>updateCredField(i,"required",e.target.checked)} className="rounded"/>必填</label><button type="button" onClick={()=>removeCredField(i)} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"><Trash2 size={14}/></button></div>
                </div>
                <input className="admin-input mt-2 text-xs" placeholder="占位提示文字" value={f.placeholder||""} onChange={e=>updateCredField(i,"placeholder",e.target.value)}/>
              </div>
            ))}
          </div>

          <SectionTitle title="高级安全设置"/>
          <AdvancedAuthPanel aa={draft.advanced_auth||{}} onChange={(aa)=>setDraft({...draft,advanced_auth:aa})}/>

          <label className="flex items-center gap-2.5 text-sm font-bold text-slate-700">
            <input type="checkbox" checked={draft.published} onChange={e=>setDraft({...draft,published:e.target.checked})} className="h-4 w-4 rounded border-slate-300 text-sky-500 focus:ring-sky-400"/>
            发布（用户可见）
          </label>
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={onSave} disabled={isSaving||!draft.name||!draft.base_url} className="gap-2">{isSaving?<Loader2 size={16} className="animate-spin"/>:<Save size={16}/>}{draft.id?"更新":"创建"}</Button>
        </div>
      </motion.div>
    </div>,
    document.body
  );
}

function ApiModal({draft,setDraft,onSave,onClose,isSaving}:{draft:ApiDraft;setDraft:(d:ApiDraft)=>void;onSave:()=>void;onClose:()=>void;isSaving:boolean}){
  const updateParam=(i:number,f:keyof IntegrationApiParam,v:string|boolean)=>{const p=[...draft.params];p[i]={...p[i],[f]:v};setDraft({...draft,params:p});};
  const addParam=()=>setDraft({...draft,params:[...draft.params,{name:"",param_type:"query",data_type:"string",required:false,description:"",default_value:null}]});
  const removeParam=(i:number)=>setDraft({...draft,params:draft.params.filter((_,x)=>x!==i)});
  return createPortal(
    <div className="admin-modal-shell" onMouseDown={onClose}>
      <motion.div initial={{opacity:0,y:24,scale:0.96}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:24,scale:0.96}} transition={{duration:0.22}} onMouseDown={e=>e.stopPropagation()} className="admin-solid-panel admin-modal-panel flex max-h-[min(88vh,900px)] w-full max-w-2xl flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 pt-5 pb-0">
          <div><p className="admin-section-kicker">接口配置</p><h3 className="mt-1.5 text-xl font-black tracking-tight text-slate-900">{draft.id?"编辑接口":"新增接口"}</h3></div>
          <button type="button" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600"><X size={19}/></button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 pt-5 pb-6 space-y-5">
          <SectionTitle title="基本信息"/>
          <div className="grid grid-cols-2 gap-3.5">
            <Field label="接口名称" required><input className="admin-input font-mono text-sm" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})} placeholder="search_issues"/></Field>
            <Field label="展示名" required><input className="admin-input" value={draft.display_name} onChange={e=>setDraft({...draft,display_name:e.target.value})} placeholder="搜索工单"/></Field>
          </div>
          <Field label="描述"><textarea className="admin-input min-h-[56px] resize-y" value={draft.description} onChange={e=>setDraft({...draft,description:e.target.value})} placeholder="接口功能描述"/></Field>

          <SectionTitle title="请求配置"/>
          <div className="grid grid-cols-2 gap-3.5">
            <Field label="方法"><select className="admin-input" value={draft.method} onChange={e=>setDraft({...draft,method:e.target.value})}>{METHODS.map(m=><option key={m} value={m}>{m}</option>)}</select></Field>
            <Field label="路径" required><input className="admin-input font-mono text-sm" value={draft.path} onChange={e=>setDraft({...draft,path:e.target.value})} placeholder="/rest/api/2/issue/{id}"/></Field>
          </div>
          <div className="grid grid-cols-2 gap-3.5">
            <Field label="超时 (秒)"><input className="admin-input" type="number" value={draft.timeout_seconds} onChange={e=>setDraft({...draft,timeout_seconds:Number(e.target.value)})}/></Field>
            <div className="flex items-end pb-1"><label className="flex items-center gap-2.5 text-sm font-bold text-slate-700"><input type="checkbox" checked={draft.requires_approval} onChange={e=>setDraft({...draft,requires_approval:e.target.checked})} className="h-4 w-4 rounded border-slate-300 text-sky-500 focus:ring-sky-400"/>需要审批</label></div>
          </div>

          <SectionTitle title="参数定义"/>
          <div>
            <div className="mb-2 flex items-center justify-between"><span className="text-sm font-bold text-slate-700">请求参数</span><button type="button" onClick={addParam} className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-sky-600 transition-colors hover:bg-sky-50"><Plus size={13}/>添加</button></div>
            {draft.params.length===0&&<p className="rounded-xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-400">暂无参数</p>}
            {draft.params.map((p,i)=>(
              <div key={i} className="mb-2 rounded-2xl border border-slate-200 bg-white/60 p-3">
                <div className="grid grid-cols-4 gap-2">
                  <input className="admin-input text-sm" placeholder="参数名" value={p.name} onChange={e=>updateParam(i,"name",e.target.value)}/>
                  <select className="admin-input text-sm" value={p.param_type} onChange={e=>updateParam(i,"param_type",e.target.value)}><option value="path">path</option><option value="query">query</option><option value="body">body</option></select>
                  <select className="admin-input text-sm" value={p.data_type} onChange={e=>updateParam(i,"data_type",e.target.value)}><option value="string">string</option><option value="integer">integer</option><option value="boolean">boolean</option><option value="object">object</option></select>
                  <div className="flex items-center gap-2"><label className="flex items-center gap-1 text-xs text-slate-600"><input type="checkbox" checked={p.required} onChange={e=>updateParam(i,"required",e.target.checked)} className="rounded"/>必填</label><button type="button" onClick={()=>removeParam(i)} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"><Trash2 size={14}/></button></div>
                </div>
                <input className="admin-input mt-2 text-xs" placeholder="参数说明" value={p.description} onChange={e=>updateParam(i,"description",e.target.value)}/>
              </div>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={onSave} disabled={isSaving||!draft.name||!draft.path} className="gap-2">{isSaving?<Loader2 size={16} className="animate-spin"/>:<Save size={16}/>}{draft.id?"更新":"创建"}</Button>
        </div>
      </motion.div>
    </div>,
    document.body
  );
}

function TestDrawer({state,api,onClose,onParamChange,onRun}:{state:TestState;api:IntegrationApi|undefined;onClose:()=>void;onParamChange:(n:string,v:string)=>void;onRun:()=>void}){
  if(!state||!api)return null;
  return(
    <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-50 flex justify-end bg-black/20">
      <motion.div initial={{x:400}} animate={{x:0}} className="h-full w-full max-w-md overflow-y-auto border-l border-white/60 bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between"><h3 className="text-lg font-black text-slate-900">测试: {api.display_name}</h3><Button variant="ghost" size="icon" onClick={onClose}><X size={18}/></Button></div>
        <div className="mt-5 space-y-3">
          {api.params.map(p=>(<Field key={p.name} label={p.name} required={p.required}><input className="admin-input text-sm" value={state.params[p.name]||""} onChange={e=>onParamChange(p.name,e.target.value)} placeholder={p.description||p.name}/></Field>))}
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
function SectionTitle({title}:{title:string}){return(<div className="flex items-center gap-3"><span className="text-xs font-black tracking-[0.2em] uppercase text-slate-400">{title}</span><div className="flex-1 border-t border-slate-100"/></div>);}

function AdvancedAuthPanel({aa,onChange}:{aa:Record<string,any>,onChange:(v:Record<string,any>)=>void}){
  const [open,setOpen]=useState(false);
  const sign=aa.sign||{};
  const enc=aa.request_encrypt||{};
  const dec=aa.response_decrypt||{};
  const common=aa.common||{};
  const set=(section:string,key:string,val:string)=>onChange({...aa,[section]:{...(aa[section]||{}),[key]:val}});
  const SIGN_ALGOS=[{v:"none",l:"无"},{v:"hmac_sha256",l:"HMAC-SHA256"},{v:"hmac_sha512",l:"HMAC-SHA512"},{v:"hmac_md5",l:"HMAC-MD5"},{v:"sha256_with_rsa",l:"SHA256WithRSA"},{v:"sha1_with_rsa",l:"SHA1WithRSA"},{v:"md5_with_rsa",l:"MD5WithRSA"}];
  const AES_ALGOS=[{v:"none",l:"无"},{v:"aes_128_cbc",l:"AES-128-CBC"},{v:"aes_256_cbc",l:"AES-256-CBC"},{v:"aes_256_gcm",l:"AES-256-GCM"},{v:"aes_ecb",l:"AES-ECB"}];
  const hasSign=sign.algorithm&&sign.algorithm!=="none";
  const hasEnc=enc.algorithm&&enc.algorithm!=="none";
  const hasDec=dec.algorithm&&dec.algorithm!=="none";
  return(
    <div className="rounded-2xl border border-slate-200 overflow-hidden">
      <button type="button" onClick={()=>setOpen(!open)} className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-slate-50">
        <span className="text-sm font-bold text-slate-700">🔒 签名 / 加密 / 解密</span>
        <span className="text-xs text-slate-400">{open?"收起":"展开"}{hasSign||hasEnc||hasDec?" · 已配置":""}</span>
      </button>
      {open&&(
      <div className="space-y-5 border-t border-slate-100 px-4 py-4">
        {/* ── Signing ── */}
        <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-3.5 space-y-3">
          <p className="text-xs font-black tracking-wider text-amber-600 uppercase">请求签名</p>
          <Field label="签名算法"><select className="admin-input text-sm" value={sign.algorithm||"none"} onChange={e=>set("sign","algorithm",e.target.value)}>{SIGN_ALGOS.map(a=><option key={a.v} value={a.v}>{a.l}</option>)}</select></Field>
          {hasSign&&(<>
            <Field label={sign.algorithm?.startsWith("rsa")?"RSA 私钥 (PEM)":"签名密钥"}><textarea className="admin-input min-h-[56px] resize-y font-mono text-xs" value={sign.secret||""} onChange={e=>set("sign","secret",e.target.value)} placeholder={sign.algorithm?.startsWith("rsa")?"-----BEGIN PRIVATE KEY-----\n...":"输入密钥"}/></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="签名位置"><select className="admin-input text-sm" value={sign.placement||"header"} onChange={e=>set("sign","placement",e.target.value)}><option value="header">Header</option><option value="query">Query Param</option></select></Field>
              <Field label="字段名"><input className="admin-input text-sm" value={sign.field_name||""} onChange={e=>set("sign","field_name",e.target.value)} placeholder="X-Signature"/></Field>
            </div>
            <Field label="签名内容模板"><input className="admin-input font-mono text-xs" value={sign.content_template||""} onChange={e=>set("sign","content_template",e.target.value)} placeholder="{timestamp}{nonce}{body}"/></Field>
            <Field label="编码"><select className="admin-input text-sm" value={sign.encoding||"base64"} onChange={e=>set("sign","encoding",e.target.value)}><option value="base64">Base64</option><option value="hex">Hex</option></select></Field>
          </>)}
        </div>
        {/* ── Request Encryption ── */}
        <div className="rounded-xl border border-sky-100 bg-sky-50/40 p-3.5 space-y-3">
          <p className="text-xs font-black tracking-wider text-sky-600 uppercase">请求加密</p>
          <Field label="加密算法"><select className="admin-input text-sm" value={enc.algorithm||"none"} onChange={e=>set("request_encrypt","algorithm",e.target.value)}>{AES_ALGOS.map(a=><option key={a.v} value={a.v}>{a.l}</option>)}</select></Field>
          {hasEnc&&(<>
            <div className="grid grid-cols-2 gap-3">
              <Field label="密钥"><input className="admin-input font-mono text-xs" type="password" value={enc.key||""} onChange={e=>set("request_encrypt","key",e.target.value)} placeholder="16/24/32 字节"/></Field>
              <Field label="IV"><input className="admin-input font-mono text-xs" type="password" value={enc.iv||""} onChange={e=>set("request_encrypt","iv",e.target.value)} placeholder="16 字节 (ECB 留空)"/></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="加密范围"><select className="admin-input text-sm" value={enc.scope||"body"} onChange={e=>set("request_encrypt","scope",e.target.value)}><option value="body">整个 Body</option></select></Field>
              <Field label="编码"><select className="admin-input text-sm" value={enc.encoding||"base64"} onChange={e=>set("request_encrypt","encoding",e.target.value)}><option value="base64">Base64</option><option value="hex">Hex</option></select></Field>
            </div>
          </>)}
        </div>
        {/* ── Response Decryption ── */}
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-3.5 space-y-3">
          <p className="text-xs font-black tracking-wider text-emerald-600 uppercase">响应解密</p>
          <Field label="解密算法"><select className="admin-input text-sm" value={dec.algorithm||"none"} onChange={e=>set("response_decrypt","algorithm",e.target.value)}>{AES_ALGOS.map(a=><option key={a.v} value={a.v}>{a.l}</option>)}</select></Field>
          {hasDec&&(<>
            <div className="grid grid-cols-2 gap-3">
              <Field label="密钥"><input className="admin-input font-mono text-xs" type="password" value={dec.key||enc.key||""} onChange={e=>set("response_decrypt","key",e.target.value)} placeholder="复用请求加密密钥"/></Field>
              <Field label="IV"><input className="admin-input font-mono text-xs" type="password" value={dec.iv||enc.iv||""} onChange={e=>set("response_decrypt","iv",e.target.value)} placeholder="复用请求加密 IV"/></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="密文路径"><input className="admin-input font-mono text-xs" value={dec.path||""} onChange={e=>set("response_decrypt","path",e.target.value)} placeholder="data.encrypted"/></Field>
              <Field label="编码"><select className="admin-input text-sm" value={dec.encoding||"base64"} onChange={e=>set("response_decrypt","encoding",e.target.value)}><option value="base64">Base64</option><option value="hex">Hex</option></select></Field>
            </div>
          </>)}
        </div>
        {/* ── Common Params ── */}
        {(hasSign||hasEnc)&&(
        <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-3.5 space-y-3">
          <p className="text-xs font-black tracking-wider text-slate-500 uppercase">公共参数</p>
          <div className="grid grid-cols-3 gap-3">
            <Field label="时间戳字段名"><input className="admin-input text-sm" value={common.timestamp_field||""} onChange={e=>set("common","timestamp_field",e.target.value)} placeholder="timestamp"/></Field>
            <Field label="时间戳格式"><select className="admin-input text-sm" value={common.timestamp_format||"unix"} onChange={e=>set("common","timestamp_format",e.target.value)}><option value="unix">Unix 时间戳</option><option value="iso8601">ISO 8601</option></select></Field>
            <Field label="随机数字段名"><input className="admin-input text-sm" value={common.nonce_field||""} onChange={e=>set("common","nonce_field",e.target.value)} placeholder="nonce"/></Field>
          </div>
        </div>
        )}
      </div>
      )}
    </div>
  );
}
