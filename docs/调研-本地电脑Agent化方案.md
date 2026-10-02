# 调研:让 AgenticOS 能操作用户的电脑(兼容 Windows 7)

> 2026-10 · **状态:仅调研,本次不实现**
> 目标:用户在电脑上装轻量客户端,之后由 AgenticOS 上的 AI 帮他在本机做事(装软件、改配置、跑脚本、传文件、截图分析)
> 硬约束:Windows 7 必须支持(企业存量机器多)

---

## 一、三条硬约束(已核实)

1. **Win7 支持已于 2020-01-14 结束**(ESU 已于 2023-01-11 结束)。来源:Microsoft Lifecycle 官方页。
2. **Win7 上的浏览器也死了**:Chrome/Edge **109** 是最后支持 Win7/8.1 的版本,2023-02 起要求 Win10+。→ **任何依赖浏览器扩展 + 新版 Web API 的方案在 Win7 上不可行**。
3. **Win7 的 RDP 缺 CredSSP 补丁**:Microsoft 文档明确,Win7 SP1 装 CredSSP 更新后 `TSpkg.dll` 为 6.1.7601.24117,对应 **KB4103718 / KB4103712**。这是远程桌面最常见的翻车点。

---

## 二、方案横评

| 方案 | Win7 支持 | 开源 | 完全私有化 | 无人值守 | 开销 | 授权 |
|---|---|---|---|---|---|---|
| **RustDesk** | **支持**,官方持续发布 32 位 sciter 包(最新 1.4.9)。注意:**官方包可用,自编译版在 Win7 SP1 上会崩**(issue #14387),必须用官方包 | 是(AGPL-3.0) | **是**(hbbs ID + hbbr 中继,Docker 一条命令) | 是(永久密码/配置串/部署脚本) | 中,打洞失败走中继时办公场景约 100 KB/s | AGPL-3.0,自部署免费 |
| **AnyDesk** | **明确支持**("XP SP2 and later, including Windows 7") | 否 | 企业版需采购 | 是 | 中 | 免费版仅个人;企业必须付费 |
| **Apache Guacamole** | **无客户端依赖** → Win7 只需能连 RDP,用什么连都行 | 是(Apache-2.0) | **完全私有**(Java + guacd + DB) | 是 | **最大**(全部像素流经服务器做编解码) | Apache-2.0 |
| **MeshCentral** | issue 侧面证明可跑,**官方最低版本需验证** | 是(Apache-2.0) | 完全私有 | 是 | 中高 | Apache-2.0 |
| **Chrome Remote Desktop** | **推断不支持**(依赖浏览器+在线账号,Win7 浏览器已死),需实测 | 否 | 否 | 是 | 低 | 免费 |
| **TeamViewer / ToDesk / 向日葵** | **需验证**(官网未列具体版本;业界普遍认知新版已放弃 Win7,但未取得一手证据) | 否 | 部分支持 | 是 | 中 | 商业 |
| **自研(WebSocket + 本地 agent)** | **完全可控 → 必然支持** | 自有 | 完全私有 | 可 | **最低**(只传结构化指令与文本结果,不传像素流) | 自有 |

---

## 三、RDP 在 Win7 上的坑:为什么 Guacamole 反而更稳

1. **CredSSP/NLA 是最大的雷**。微软的 "Encryption Oracle Remediation" 策略会在**两端补丁版本不匹配时直接拒绝连接**(报 `An authentication error has occurred`)。官方行为矩阵:一端装一端没装 → Block。企业存量 Win7 大概率是"几个月没打补丁"的机器。
2. **TLS 版本**:Win7 原生不支持 TLS 1.2,现代 RDP 普遍要求 1.2+。
3. **受限管理(Restricted Admin)** 会改变凭据流路径,与 CredSSP 交互行为不同。
4. **性能与特效**吃带宽和 CPU(Guacamole 的 `enable-wallpaper`/`disable-gfx`/`disable-bitmap-caching` 就是为此准备的)。

**Guacamole 更稳的原因**:
- **Win7 端零客户端**:不用装 mstsc、不用升浏览器、不用装证书,所有协议适配都在服务端 guacd 完成
- **凭据集中化**:支持 LDAP/AD 认证,用户不接触 Win7 机器密码(企业环境的决定性优势)
- **可绕过 CredSSP 地狱**:RDP 安全模式可选 `security=rdp`(legacy),走不依赖 NLA 的老式加密
- **安全侧齐全**:暴力破解封禁、MFA、SSO、Session Recording 回放

**代价**:所有像素流经服务器,带宽与 CPU 是真瓶颈。

---

## 四、三个推荐组合

### 组合 A(主方案):RustDesk 自建 + 自研轻量 Agent
**定位:AI 操作 + 必要时人工接管**。AI 走自研 agent 协议(不走像素流),人需要看屏幕时才用 RustDesk。

```
[Win7 客户端]  rustdesk.exe(32位官方包) + agenticos-agent.exe
      │                    │
      │ WSS(WebSocket)     │ TCP 21114-21119 + UDP 21116
      ▼                    ▼
[AgenticOS 后端]      [RustDesk hbbs(ID) + hbbr(中继)]   ← 全部部署在企业内网
   agent-gateway:8443
      ├─ 指令下发 / 事件回传
      ├─ 设备-用户授权映射
      └─ 审计日志
[反向代理 Nginx] :443 → 静态前端 + API + WSS
```
- 中继必须**只允许 Nginx 访问 21118/21119**(官方文档警告 X-Forwarded-For 伪造可绕过 IP 限流)
- Win7 客户端 agent 建议 **.NET Framework 4.7.2 或更早**,或直接用 Go/Rust 静态编译(避开 Win7 缺 `api-ms-win-*` DLL 的坑)

### 组合 B(最省事):组合 A + Guacamole 兜底
当 agent 不具备某能力(装软件、看图形界面),让人介入:Win7 RDP → Guacamole → iframe 内嵌进 AgenticOS。连接串存 DB,认证走 AD/LDAP。对连 CredSSP 补丁都没打的 Win7,用 `security=rdp` 绕过。还能用 `custom-auth` 扩展做"**AI 申请临时远程连接 → 弹出审批 → 通过才建会话**"的闭环。

### 组合 C(最轻,建议 P0):纯 WebSocket + 自研 Agent,不带远程桌面
只做 AI 能做的事:文件读写、脚本执行、系统信息采集、剪贴板、软件安装、进程管理。服务端复用现有 FastAPI + SSE,不必新起服务。
- 优点:开销最低、攻击面最小、无远程桌面合规风险、完全可控
- 缺点:做不了"AI 看到屏幕上有个报错弹窗并点掉"这类 GUI 操作(需另补截图 + UIA/Win32 自动化)

> **建议节奏:组合 C 是 P0,组合 A 的 RustDesk 部分是 P1,组合 B 是 P2。**

---

## 五、AI 结合路径:指令下发接口设计

**为什么不直接复用 MCP**:MCP(尤其 stdio)要求本地进程存在,与"远端 AI 下发指令"模型不匹配。
**建议:REST/WebSocket 做传输,MCP 做工具描述**——后端把"这台电脑能干什么"用 MCP tool schema 暴露,AI 用标准 tool call 表达意图,gateway 翻译成本地协议。

### 三层设计

**传输层(WebSocket 主 + REST 辅)**
```
GET  /api/v1/agents/register              → 一次性注册,返回 agent_id + agent_token
WS   /api/v1/agents/{agent_id}/channel    → 长连接,双向
GET  /api/v1/agents/{agent_id}/tasks      → 断线时的降级轮询
```
消息信封:
```json
{
  "type": "task.dispatch | task.progress | task.result | task.approval_required | task.cancel | agent.heartbeat",
  "task_id": "t_8f3a...",
  "ts": "2026-10-02T09:15:22Z",
  "payload": {}
}
```
- `agent.heartbeat` 每 15s,含 `os_version`、`agent_version`、CPU/内存/磁盘、pending/running 任务。**Win7 上务必上报 os_version**,后端据此决定下发哪套命令集
- 断线指数退避(1/2/4s…上限 60s);**服务端持有 pending 队列,重连后补发**

**能力描述层(MCP tool schema 兼容)**
```json
{"tools": [
  {"name": "fs_read",     "inputSchema": {}, "risk": "read"},
  {"name": "fs_write",    "inputSchema": {}, "risk": "write"},
  {"name": "shell_exec",  "inputSchema": {}, "risk": "execute"},
  {"name": "sys_info",    "inputSchema": {}, "risk": "read"}
]}
```
后端据此渲染工具列表,并按 `risk` 自动套用审批策略。好处:本地 agent 加新能力 = 加一个 tool,后端零改动;也能顺带支持第三方 MCP server 作为工具来源。

**执行语义层**:能力分级 + 幂等;agent 侧独立执行一遍策略(策略从后端下发,便于集中调整)。

**CLI 兜底**:`agenticos-agent.exe status | install | uninstall | run-task <task.json> | logs`,便于 IT 在无 AI 参与时排障。

> 不选 HTTP REST-only(轮询延迟高、事件推送难,仅作降级);不选 SSH/WinRM(Win7 需额外装组件与账号体系,反而更重)。

---

## 六、典型场景清单

**只读(可自动放行)**:采集系统信息/软件清单生成资产报告;扫目录找大文件;读日志筛选异常;读 Excel/CSV 做统计;软件安装与版本合规巡检;读注册表/服务/端口;跨多客户端汇总报表。

**低风险写(auto 档仍需确认一次)**:在指定工作目录内创建/改文件;按模板生成文档;限定目录内批量重命名;内网共享拷文件;格式转换(xlsx→csv、pdf→md)。

**需逐次确认**:执行任意 shell;装卸软件;改注册表;启停服务/改启动类型;改防火墙/网络配置;建改系统账号(**尤其提权到管理员组**);操作浏览器(登录、提交表单);发邮件/提交审批等对外副作用操作。

**高危(二次确认 + 审计 + 可回滚)**:格式化分区、删目录;改 BIOS/重启/关机;改管理员密码;批量脚本下发多机;涉及生产数据库/ERP/核心业务系统。

**GUI 类(需组合 A/B 支持)**:截图→识别报错弹窗→确认后关闭;打开软件填表;远程协助 IT 看现场;抓屏录像留证。

---

## 七、安全与合规(落地前必须设计进去)

**授权三重绑定**
- **设备**:注册时生成设备证书(Ed25519/X.509),私钥只在客户端;后端存公钥,每条指令带 nonce 防重放
- **用户**:`user_id ↔ agent_id` 由管理员显式授权(可按部门/组批量)。**AI 不能碰未授权设备**
- **时间**:授权可设有效期(如工作日 9:00–18:00)。**"AI 半夜动我的电脑"是最敏感的合规点**

**审计**:每条指令落库(task_id / 谁让 AI 做的 / 设备 / 工具 / 脱敏参数 / risk / 审批记录 / 结果 / 时长 / exit_code),只增不改,前端可按人/设备/工具/时间筛选。

**只读模式(双层)**
1. 会话级:三档审批(`ask`/`auto`/`full`)
2. **设备级:管理员可为某设备打 read-only 标记,agent 在本地拒绝一切写/执行类工具——即使后端被攻破下发指令也拦得住**(防"后端沦陷→终端全沦陷"的关键兜底)
3. Plan mode:剥掉写工具只调研出计划

**危险操作三层确认(逐层递进)**
1. **生成期**:渲染卡片(工具名 + 目标路径/命令全文 + 影响范围),用户点执行
2. **执行期**:多步/递归操作拆成 **预览(dry-run) → 确认 → 执行**,预览结果一并展示("将删除 137 个文件,涉及 3 个目录")
3. **客户端期**:agent 弹**本地原生确认框**(不是网页弹窗),由坐在电脑前的人确认。**这一层不能省**——网页弹窗挡不住物理接触机器的人
- 超时不响应 → 任务失败,**不降级为自动执行**
- 命令必须用参数数组传参,杜绝 shell 拼接注入

**其他**:WSS(TLS 1.2+);敏感字段上报前本地脱敏;**agent 默认以当前登录用户权限运行,Win7 上尤其不要让 agent 常驻 LocalSystem**;需要证据时结合 Guacamole Session Recording;对员工明确告知操作范围与记录位置,并提供**一键断开**——这是国内企业落地的必要条件。

---

## 八、待人工验证清单

| 项 | 原因 |
|---|---|
| TeamViewer / ToDesk / 向日葵 的 Win7 支持 | 官网只写平台名不写版本 |
| Chrome Remote Desktop 是否支持 Win7 | Google 支持页多次超时;依 Microsoft 生命周期页推断不支持 |
| MeshCentral meshagent 官方最低 Windows 版本 | 未找到官方声明,仅 issue 侧面证明 |
| Win7 SP1 + 特定补丁组合下 mstsc 的实际 TLS 栈 | 未实测 |
| FreeRDP(x86_64) 连 Win7 目标端的兼容性 | 未实测 |
| Guacamole 与 mstsc 的逐项功能差异 | 官方 FAQ 页 404 |

---

## 九、一页结论

- **AI 操作用户电脑技术上完全可行**,且不需要远程桌面:RustDesk 自建解决"人要看屏幕",自研 WebSocket agent 解决"AI 做事",两者职责分离
- **Win7 的最大坑不是远程控制软件本身,而是 RDP 的 CredSSP 补丁地狱**;Guacamole 的 `security=rdp` legacy 模式能绕过,但代价是像素流全走服务器
- **第一步应该做最轻的组合 C**(纯指令 + 只读能力),因为它攻击面最小、开销最低、且不需要碰任何 Win7 兼容性问题;等验证了价值再叠加 RustDesk
- **安全设计的重心在"授权与本地兜底"**:设备级只读、客户端原生确认框、时间窗授权、三层审计——这些比远程控制能力本身更重要