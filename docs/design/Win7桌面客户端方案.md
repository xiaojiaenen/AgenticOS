# 设计决策：兼容 Windows 7 的桌面客户端

> 2026-11-05 · 状态：**方案待评审，未实现**
> 范围：给 AgenticOS 3.2.0 做一个可安装、有独立窗口的桌面客户端，目标机 Windows 7 SP1（x86/x64）
> 结论：**做「瘦壳 + 双构建线」，后端一律留在服务器；Win7 分支锁 Electron 22.3.27，主项目零改动**

---

## 〇、一页结论

**推荐方案**：新建一个独立子工程 `desktop/`，用 **Electron 22.3.27（Chromium 108 / Node 16.17，最后一个支持 Win7 的 Electron）** 做一个**瘦客户端**——它只负责「独立窗口 + 服务器地址配置 + 原生外壳能力」，启动后直接 `loadURL()` 到**现有的 nginx 服务器地址**（如 `http://10.x.x.x:10008`）。页面仍由服务器提供，因此前端的 history 路由、`/assets/` 根绝对路径、localStorage 令牌、CORS 同源假设、SSE 长链路**全部原样成立，主项目不需要为桌面端改任何架构**。

同时把壳拆成**两条构建线**：主线用现代 Electron（Win10/11，可持续升级），Win7 用 profile 派生的冻结分支（只出 NSIS 包、锁死版本、只修致命 bug）。Win7 机器淘汰时删掉这个 profile 即可，不拖累主线。

**为什么不是别的**（详见第三节）：Win7 的浏览器内核天花板是 **Chromium 109**，前端产物实际需要 **≥105**（`:has()`/`@container`），能落在 `[105, 109]` 这个窗口里的成熟方案只有 Electron 22（108）和 NW.js 0.72（109）；Tauri 系（WebView2 111+ → Win10+）、现代 Electron（23+ → Win10+）、CEF 自编译（成本）全部出局。

**一句话风险**：这是一条**冻结在 2023 年的内核**，且官方明确「不再为 Win7 打安全补丁」。可接受的前提是：内网/离线、只加载白名单内的可信服务器、不做通用浏览器、渲染进程完全不接触 Node。这必须写进验收标准，不能含糊。

---

## 一、现状盘点：这个决定为什么几乎是唯一解

### 1.1 生产形态本来就是「浏览器连服务器」

`deploy/DEPLOY.md:3-31`：nginx `:10008` 托管纯静态 `frontend/dist`，`/api/` 反代 FastAPI `:10007`，外部 MySQL + Redis 必填，另有 arq worker 常驻。所有文档的验收方式都是「浏览器打开 `http://<IP>:10008`」（`deploy/OFFLINE-DEPLOY.md:94`、`deploy/install.sh:84-93`）。**没有 localhost 常驻服务，没有桌面壳，仓库全局搜 `electron|tauri|nw.js|pywebview|neutralino|wails` 零命中。**

也就是说，Win7 用户**今天就已经在用 Chrome/Edge 109 打开这个地址了**。桌面客户端的真实增量价值不是「让它能跑」，而是：

| 增量价值 | 现状痛点 |
|---|---|
| 统一内核，消除「每人浏览器版本不同 → 暗色模式/卡片样式花掉」 | `docs/research/调研-Univer办公能力接入.md:89` 已记录 `:where()` 在 Chrome 85 整条失效 |
| 不依赖用户自己找/装浏览器（内网机器可能只有 IE11） | — |
| **运行时可配服务器地址** | `VITE_API_BASE_URL` 是 **Vite 编译期常量**（`frontend/src/services/apiClient.ts:4`），换服务器要重新 `npm run build`；还有 `llmopsService.ts:7` 等若干处硬编码 `/api/v1` |
| 独立图标/窗口/托盘/单实例/开机自启/原生通知/断线重连/下载接管 | 无 |
| 统一分发、版本可控、IT 可批量预置 | 无 |

### 1.2 后端搬到 Win7 本地 = 重写，且无意义

`docs/research/调研-本地电脑Agent化方案.md` 之外，本次又逐条核实了后端本地化的 5 条独立硬阻断（任意一条足以否决）：

| # | 阻断 | 证据 |
|---|---|---|
| 1 | Python 3.13 官方不支持 Win7（Win7 上限 3.8） | `backend/pyproject.toml:6` `requires-python = ">=3.13,<3.14"`；`backend/.python-version`；`uv.lock:3` `==3.13.*`；Dockerfile 全 `python:3.13-slim` |
| 2 | Node ≥20 不支持 Win7（上限 16，已 EOL） | `backend/office-runtime/package.json:7` `"node": ">=20"`；`frontend/.nvmrc` = 22 |
| 3 | 新二进制 wheel 需 SSE4.2/AVX、Win10+ 工具链 | `numpy 2.4.6`（x86-64-v2 基线）、`pandas 3.0.5`、`onnxruntime 1.20.1`、`cryptography 44`、`pypdfium2`；`deploy/Dockerfile.runtime:39-42` 另有 `sentence-transformers`（torch CPU ~800MB）+ `playwright install chromium` |
| 4 | 沙箱是 POSIX 专用，仓库自认 Windows 不可用 | `backend/app/services/sandbox.py:128` `os.killpg/os.getpgid`、`:177-184` `create_subprocess_shell(start_new_session=True)`；`backend/tests/test_website_fixes.py:180` 显式 `skipif(sys.platform=="win32")` |
| 5 | LLM 是唯一不可降级的外部硬依赖 | `backend/app/services/llm_factory.py:22-58` 全站唯一入口；`llm_providers/runtime.py:328-337` 无 Key 抛 `ProviderUnavailable`；仓库**无本地推理引擎**，只有压测用 `LLM_MOCK_ENABLED` |

再叠加「生产要求外部 MySQL + Redis + arq worker + nginx」、`deploy/` 全是 Linux 脚本与 `/app/...` 硬编码路径、完整运行时镜像约 **8GB / 常驻内存 1.5GB+**（`deploy/OFFLINE-DEPLOY.md:6,14-19`）。**「Win7 单机离线版」在当前架构下不成立，且即使重写也仍须连远端 LLM，因此不值得做。**

> 结论：**桌面客户端 = 瘦客户端**，这一条不接受「先做个单机版试试」的折中。

### 1.3 前端内核需求：刚好卡在 Win7 天花板的下沿（重要长期约束）

项目有一条 Chrome 85 兼容门禁（`frontend/vite.config.ts:18,53`、`frontend/package.json:83-97` browserslist、`scripts/verify-css.mjs` + CI 门禁、`theme-palette.css` 用 hex 覆盖 Tailwind v4 的 `oklch`）。但**实测产物**里还有：

| 特性 | 产物出现次数 | 最低 Chrome | Chromium 108/109 |
|---|---|---|---|
| `:where()` | 469 | 88 | ✅ |
| `:has()` | 12 | **105** | ✅ |
| `@container` | 3 | **105** | ✅ |
| `backdrop-filter` | 28 | 76 | ✅ |
| `color-mix()`（`@supports` 内） | 459 | 111 | ❌ → 走 hex fallback |
| `oklch()` | 0（门禁已清零） | 111 | ❌ → 已无 |

**即：真实需要 ≥105，而 Win7 能提供的最后内核是 108（Electron 22）/109（NW.js 0.72 / Edge / Chrome）。刚好够，没有一点余量。**

⇒ **必须写进项目长期约束**：只要 Win7 分支还活着，前端**禁止引入任何 Chrome ≥111 才有的特性且无 `@supports` 兜底**（`oklch`、`color-mix` 无保护直写、CSS Nesting 120+、View Transitions 111+、Popover 114+、`@scope` 118+ 等）。现有 `verify-css.mjs` 门禁应扩一条「新特性最低版本」检查，否则某次前端升级会静默把 Win7 分支打死。

---

## 二、Win7 硬约束（已核实，需写进交付与部署手册）

1. **Electron 23+（Chromium 110+）只支持 Win10+**；**Electron 22（Chromium 108）是最后一个支持 Win7 的大版本**，最后补丁版为 **22.3.27**，22.x 支持周期已于 **2023-10-10** 结束，官方明确「不会为 Win7/8/8.1 追加安全修复」。来源：electronjs.org「Farewell, Windows 7/8/8.1」。
2. **WebView2 / Edge 109 是 Win7 最后一版**；WebView2 SDK **1.0.1519.0+ 不再支持 Win7**；Evergreen 在 Win7 上只会停在 109 且不再更新。来源：Microsoft Edge Dev Blog 2022-12-09。⇒ **Tauri v2 需要 WebView2 111+ → 直接出局**。
3. **NW.js 0.72.0（Chromium 109 / Node 19.3）是最后一个支持 Win7 的版本**，0.73+ 不支持。
4. **Win7 系统补丁链（客户端部署前置，顺序不能乱）**：
   - `KB4490628`（服务栈，前置）→ `KB4474419`（SHA-2 代码签名与证书支持）→ `KB3140245`（WinHTTP/WinINet 支持 TLS 1.1/1.2）
   - `KB3140245` **装完不等于开启**，还须设注册表 `SCHANNEL\Protocols\TLS 1.2\Client\DisabledByDefault=0`、`WinHttp\DefaultSecureProtocols=0xAA0`（32 位看 Wow6432Node）
   - `KB2670838`（DirectWrite / 高 DPI 文本渲染）、`KB2533623`（API Set）、VC++ 2015-2022 运行库、.NET Framework 4.8
   - 缺 `KB4474419` 会表现为 Electron 启动 `0xc0000142` / `Failed to load module 'electron.dll'`
5. **TLS**：服务器必须允许 **TLS 1.2**（不能只开 TLS 1.3），证书链要能被 Win7 根证书库验证（SHA-2 签名 + 时间戳）；内网自签 CA 需 IT 预先导入。
6. **代码签名**：安装包与 exe 用 SHA-256 证书 + RFC3161 时间戳；Win7 未打 SHA-2 补丁时无法验签。
7. **架构**：存量机可能有 32 位 → 出 `ia32` + `x64` 两份 NSIS 包。
8. **老显卡驱动**：准备 `--disable-gpu` / `app.disableHardwareAcceleration()` 开关作为兜底。
9. **构建机 ≠ 目标机**：在 Win10/11 + Node 20+ 上打包，产物拿给 Win7 跑；**不要在 Win7 上 `npm install`**（现代 electron-builder 自身也跑不动）。

---

## 三、方案横评

| 方案 | Win7 | 内核 | 主项目改动 | 原生能力 | 维护风险 | 判定 |
|---|---|---|---|---|---|---|
| **A. Electron 22.3.27 瘦壳 + 双构建线** | ✅ | Chromium 108 | **≈0** | 完整（托盘/单实例/自启/升级/文件/通知） | 内核 EOL，但生态成熟、有现成双分支工程实践 | **✅ 推荐** |
| B. NW.js 0.72.0 瘦壳 | ✅ | Chromium 109 | ≈0 | 完整 | 内核同为 EOL；DOM 可直接调 Node，默认安全模型更弱；打包/升级生态远小于 Electron；0.72 后无 Win7 版 | ⚠️ 备选（仅当 Electron 22 在目标机实机跑不通） |
| C. Tauri v1 + WebView2 Fixed 109 | ⚠️ | Chromium 109 | ≈0 | 完整（Rust 侧） | v1 已 EOL；SDK ≥1.0.1519 不支持 Win7 需锁老 SDK；Fixed Runtime 109 官方已不下发；Rust 对 Win7 target 支持在退 | ❌ |
| D. Tauri v2 | ❌ | WebView2 111+ → Win10+ | — | — | — | ❌ 直接出局 |
| E. 现代 Electron（23+ / 4x） | ❌ | Chromium ≥110 → Win10+ | — | — | — | ❌ 直接出局（但作**主线**） |
| F. CEF / Qt WebEngine 自编译 109 | ✅ | 自持 | 中 | 完整 | 需自建 Chromium 109 分支与补丁，成本最高，2026 年工具链几乎不可复现 | ❌ |
| G. 系统 Chrome/Edge 109 `--app=` 快捷方式 | ✅ | 109 | 0 | 几乎无（无托盘/单实例/配置/升级） | 无壳可维护 | ⚠️ 仅适合「只要一个桌面图标」的极简诉求，可作为 P-1 过渡 |
| H. 本地打包后端（PyInstaller / 单机版） | ❌ | — | 重写级 | — | 第 1.2 节 5 条硬阻断 | ❌ 否决 |

**选 A 的决定性理由**：
- Chromium 108 恰好覆盖前端需要的 `:has()`/`@container`（105+），又避开 `oklch`/`color-mix`（111+，已有 fallback）——**与项目现有 Chrome 85 门禁是同一套兼容策略的延续**；
- Electron 22 是 Win7 上**唯一有成熟 `electron-builder` + NSIS + 32/64 位 + 双分支派生工程实践**的路线（社区已有「主线 Electron 4x + `profiles/win7.json` 锁 22.3.27 + 仅 NSIS + `dist:win7` 脚本」的可复现范式）；
- 安全模型可控（`contextIsolation` + `sandbox` + 无 `nodeIntegration`），比 NW.js 的「DOM 直接调 Node」更适合跑一个会渲染 AI 生成 HTML 的系统。

---

## 四、推荐方案详述

### 4.1 架构

```
┌──────────────── Win7 SP1 客户机 ────────────────┐
│  AgenticOS.exe  (Electron 22.3.27 / Chromium 108) │
│  ┌────────────────────────────────────────────┐  │
│  │ Main 进程 (Node 16)：单实例 / 托盘 / 配置 /  │  │
│  │ URL 白名单 / 窗口打开拦截 / 失败页 / 版本    │  │
│  └───────────────┬────────────────────────────┘  │
│                  │ loadURL(配置的服务器地址)       │
│  ┌───────────────▼────────────────────────────┐  │
│  │ Renderer：直接加载 http(s)://server:10008    │  │
│  │ nodeIntegration=false / sandbox=true /       │  │
│  │ contextIsolation=true / 无地址栏             │  │
│  └────────────────────────────────────────────┘  │
│  userData/config.json（服务器地址、GPU 开关）      │
│  本地仅内置 offline.html（连接失败页）            │
└──────────────────────┬──────────────────────────┘
                       │ HTTP(S) / TLS 1.2  (内网)
                       ▼
┌──────────── 现有服务器（完全不改） ────────────┐
│ nginx :10008  → frontend/dist (SPA + history fallback)
│        └ /api/ → FastAPI :10007（SSE 已配 buffering off）
│ 外部 MySQL / Redis / arq worker / LLM 网关       │
└────────────────────────────────────────────────┘
```

**关键取舍：直接 `loadURL(serverUrl)`，不在本地托管 `frontend/dist`，也不做本地反代。**

这一步让主项目零改动：`/assets/` 根绝对路径、SPA history fallback、localStorage origin、Bearer token、CORS 同源、SSE 全部照旧。若改为「本地静态 + 本地反代」，则要处理 `base`/`basename`、`VITE_API_BASE_URL` 编译期常量、约 20 处 service 拼接 + 若干硬编码 `/api/v1`、SSE 反代的 `proxy_buffering off` / 300s 超时、以及 `file://` 下 origin 为 `null` 的问题——**用 5 倍工作量换一个「离线能开壳」的伪收益（后端连不上时壳本来也用不了）**。

本地只放一个 `offline.html`：断网/`did-fail-load` 时显示「无法连接服务器 + 当前地址 + 重试 / 修改地址」，避免白屏。

### 4.2 目录结构（新增，与现有依赖树完全隔离）

```
desktop/                          # 独立 package.json，不进 frontend/backend
├─ package.json                   # 主线：electron 现代版 + electron-builder
├─ profiles/
│  └─ win7.json                   # 覆盖：electron=22.3.27, win.target=["nsis"],
│                                 # artifactName 带 -win7, 关闭 autoUpdater
├─ scripts/
│  └─ build-win7.mjs              # 复制受控源码到 .win7-stage/ → 装 22.3.27 → 出 ia32/x64 NSIS
├─ src/
│  ├─ main.js                     # 单实例 / 窗口 / 托盘 / 导航白名单 / 失败页
│  ├─ config.js                   # 服务器地址读写（userData + 安装目录预置 + 命令行）
│  ├─ setup.html + setup-preload.js  # 首次启动的服务器地址配置窗口
│  ├─ offline.html                # 连接失败页
│  └─ preload.js                  # contextBridge 暴露极小的 shell API
├─ build/                         # 图标、NSIS 脚本（可选：预置 server.conf）
└─ README.md                      # 构建机要求、Win7 补丁链、IT 批量分发说明
```

`.gitignore` 追加 `desktop/.win7-stage/`、`desktop/dist/`、`desktop/node_modules/`。

### 4.3 主进程关键约束（验收即按此逐条核对）

```js
// src/main.js（骨架，Electron 22 API）
const { app, BrowserWindow, Tray, Menu, shell, session } = require('electron');
const { loadConfig, saveConfig } = require('./config');

if (!app.requestSingleInstanceLock()) { app.quit(); }        // 单实例
else {
  app.on('second-instance', () => focusMain());

  app.whenReady().then(() => {
    const cfg = loadConfig();                                // serverUrl / disableGpu
    if (cfg.disableGpu) app.disableHardwareAcceleration();  // 老显卡兜底

    session.defaultSession.setPermissionRequestHandler((_, p, cb) => cb(false));
    session.defaultSession.webRequest.onHeadersReceived((d, cb) => {
      // 补一层 CSP（nginx 当前未下发 CSP）：只连自家源，禁 object/base-uri
      cb({ responseHeaders: { ...d.responseHeaders,
        'Content-Security-Policy': ["default-src 'self' ...; object-src 'none'; base-uri 'self'"] } });
    });

    const win = new BrowserWindow({
      width: 1440, height: 900, show: false, autoHideMenuBar: true,
      webPreferences: {
        nodeIntegration: false,          // 必须
        contextIsolation: true,          // 必须
        sandbox: true,                   // 必须
        webSecurity: true,
        webviewTag: false,               // 必须关
        nodeIntegrationInWorker: false,
        preload: path.join(__dirname, 'preload.js'),
      },
    });

    const allowed = new URL(cfg.serverUrl).origin;
    // 企业 SSO（OIDC）会跳到身份平台再跳回来，必须额外放行，否则登录直接卡死
    const ssoOrigins = (cfg.ssoOrigins || []).map((o) => new URL(o).origin);
    const isSafe = (u) => {
      try { const x = new URL(u); return ['http:', 'https:'].includes(x.protocol) && x.origin === allowed; }
      catch { return false; }
    };
    const mayNavigate = (u) => isSafe(u) || (() => {
      try { return ssoOrigins.includes(new URL(u).origin); } catch { return false; }
    })();

    win.webContents.on('will-navigate', (e, u) => { if (!mayNavigate(u)) e.preventDefault(); });
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (isSafe(url)) shell.openExternal(url);             // 外链交给系统默认浏览器
      return { action: 'deny' };                           // 绝不开新 Electron 窗口
    });
    win.webContents.on('did-fail-load', () => win.loadFile('offline.html'));

    win.loadURL(cfg.serverUrl);                             // ← 唯一加载入口
    buildTray(cfg, win);                                   // 托盘：重连 / 修改服务器地址 / 退出
  });
}
```

要点说明：
- **不做通用浏览器**：地址栏不可输入、导航白名单只允许配置的 origin、`webviewTag:false`、权限请求一律拒绝。这是 EOL 内核可被接受的核心缓解措施。
- `setWindowOpenHandler` 必需：前端 `WebsiteArtifactPanel.tsx:276`、`pages/Gallery.tsx:99` 等用 `window.open(url,'_blank')`，不拦截会在壳里开出一个没有地址栏的 Electron 窗口，用户出不去。
- **服务器地址运行时可配**（本节最大实用价值）：`config.js` 优先级 = 命令行 `--server=` > 安装目录 `server.conf`（IT 批量预置 / 域控下发）> `userData/config.json`（用户上次输入）> 首次启动弹 `setup.html`。校验必须是 `http/https` 且通过一次 `GET /api/v1/health/` 探活再保存。
- **Win7 分支不做自动更新**：`electron-updater` 的 Squirrel/NSIS 差异 + 内网 TLS1.2 + 老机器权限，容易把客户端更死。改为：壳每次启动读服务器 `/api/v1/health/` 里带回来的 `min_client_version`，低于阈值时托盘提示「请联系 IT 升级」，由 IT 用现有软件分发推送新 NSIS 包。主线（Win10+）仍可走 `electron-updater`。
- `localStorage` 令牌落在 `userData/Local Storage/leveldb`，是明文文件。一期接受（与浏览器现状等价，不降低安全性）；若要加强，Phase 3 再由 preload 接管令牌转存 Windows 凭据库——**但这会改主项目，不进一期**。
- **若启用 OIDC 单点登录**：`cfg.ssoOrigins`（由 IT 在 `server.conf` 预置 IdP 地址）必须同时放行到 `will-navigate` 与 CSP 的 `form-action` / `connect-src`，且 OIDC 必须在**同一个窗口内**完成跳转（回调回来还要写 `localStorage`），不能交系统浏览器。当前前端登录页未接 OIDC（见 4.5），但配置口要预留。

### 4.4 双构建线

| | 主线（Win10/11） | Win7 冻结分支 |
|---|---|---|
| Electron | 现代稳定版，跟随升级 | **锁 `22.3.27`，永不升级** |
| 构建 | `npm run dist` | `node scripts/build-win7.mjs` → `desktop/.win7-stage/` 局部安装 22.3.27 → 仅 NSIS |
| 产物 | NSIS / MSI / AppX | `AgenticOS-Setup-<ver>-win7-x64.exe` + `-ia32.exe` |
| 自动更新 | `electron-updater` | 关闭，走 IT 分发 + 版本下限提示 |
| 分支策略 | 持续演进 | 只修致命 bug；Win7 机器淘汰即删 `profiles/win7.json` |

共享同一份 `src/`；`build-win7.mjs` 只做「复制受控源文件 → 覆盖 package.json 的 electron 版本与 win.target → 局部 npm i → electron-builder」。`desktop/package.json` 本身不被 Win7 拖住，这是隔离的全部意义。

### 4.5 登录怎么做：不用重做

**结论：壳完全不碰账号密码，一行登录代码都不用写。** 它只是个「只能打开咱们这一个网址的浏览器窗口」，登录页、密码校验、令牌发放全在服务器和网页里，跟今天用 Chrome 打开一模一样。

现在系统支持的登录方式（由公开端点 `GET /api/v1/auth/login-mode` 下发形态，前端 `pages/Login.tsx` 据此渲染）：

| 方式 | 后端 | 桌面端 |
|---|---|---|
| 邮箱 + 密码 | `POST /auth/login` | 照旧 |
| 邮箱验证码 | `POST /auth/send-code` + `/auth/login-code`（依赖 SMTP） | 照旧 |
| 域账号（LDAP，工号 + 域密码） | 同样走 `POST /auth/login`，后端 `_do_login` 自动分流 | 照旧，**仍要手输密码** |
| OIDC 单点登录 | 后端 `/oidc/*` 全套端点已实现 | **前端登录页目前没有入口**，等于未启用；将来接了要按 4.3 放行 IdP |
| Windows 域免密（IWA/Kerberos） | **没有** | 想要得另做，见下 |

用户实际会经历的流程：

1. 第一次装好，弹一次「服务器地址」（如 `http://10.0.0.8:10008`）。**这是设置，不是登录**；IT 可用 `server.conf` 预置，用户根本不用填。
2. 出现原来的登录页，输账号密码 → 服务器校验 → 在 `auth_sessions` 表建一条会话（`auth_service.py:47-60`）→ 发回一张带 `sid` 的 JWT。
3. 网页自己把令牌和用户信息存进 `localStorage`（`authTokenStore.ts:93`），存在**壳自己的用户目录**里。之后每次打开壳自动带上 `Authorization: Bearer`，**不用重复登录**。
4. 令牌有效期：开发默认 1440 分钟（24h），生产/离线部署 `AUTH_TOKEN_EXPIRE_MINUTES=10080`（7 天）。后端每次请求还会查 `auth_sessions` 是否仍有效（`api/deps.py:44-47`）。过期/被撤销 → 前端 401 清会话并跳 `/login`（`apiClient.ts:44-51`）。
5. 点「退出登录」→ 网页先删本地令牌，再 `POST /auth/logout` 把服务端 `sid` 标记撤销（`auth.py:510-527`），退出是真的失效。

**桌面端要额外做的只有两件小事**：
- 托盘加一个「清除登录状态并重启」（`session.defaultSession.clearStorageData()` + 重载）。因为壳没有地址栏，用户没法像浏览器那样手动清缓存；切换账号、令牌卡住、换人用同一台机器时靠这个兜底。
- 服务器地址变化时**不要去保留登录态**：不同地址是不同 origin，`localStorage` 天然隔离，会自动要求重新登录，这是正确行为。

**几个要提前说清的坑**：
- **壳和 Chrome 是两套独立抽屉**：浏览器里登过，壳里还要登一次，反之亦然。想「只登一次」需要另做（设备证书 / 一次性换票 / 系统浏览器拉起），不进一期。
- **令牌是明文文件**（`userData/Local Storage/leveldb`），和 Chrome 现状等价。别装在多人共用的公共机器；要更安全就得改前端把令牌挪到 Windows 凭据库（Phase 3 可选）。
- **不支持「开机进了 Windows 域就自动登录」**：LDAP 只是拿域账号密码去服务器校验，仍要手输。企业若要求免输，是另一套安全设计（Windows 集成认证 / 客户端证书 / 设备令牌 + 后端换票），别塞进这个 EOL 内核壳里做。

---

## 五、主项目需要配合的改动（很少，但有一处必须改）

### 5.1 【必须】iframe 预览的 sandbox 组合

`frontend/src/components/website/WebsiteArtifactPanel.tsx:303-315`：

```jsx
<iframe src={liveUrl || undefined} srcDoc={liveUrl ? undefined : previewDoc}
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups" ... />
```

`allow-scripts` + `allow-same-origin` 同时给，等于让 sandbox 失效；`srcDoc` 继承父页面 origin，其中若含 AI 生成的第三方 HTML，就能读到父页面的 DOM 与 `localStorage` 里的 `auth_token`。浏览器里已有此风险，**在 Electron 里后果更重**（渲染进程被 XSS 后的横向面更大）。

**修复（选一）**：
1. 推荐：`srcDoc` 回退分支改为 `sandbox="allow-scripts allow-forms allow-popups"`（去掉 `allow-same-origin`）；签名 `liveUrl` 路径保持现状（跨源静态托管，本来就不同源）。
2. 若预览页确实需要同源：改用独立 `BrowserWindow` + 独立 `session.partition` 打开签名 URL，壳里 `setWindowOpenHandler` 放行到该窗口。

同类检查：`components/email/EmailArtifactPanel.tsx:129`、`pages/Gallery.tsx:67`、`lib/safePreview.ts:3`（后者已有 CSP `connect-src 'none'`，可直接复用其策略）。

### 5.2 【建议，非阻塞】前端兼容门禁加一条「新特性下限」

`frontend/scripts/verify-css.mjs` 现在只禁 `oklch/lab/color-mix(未保护)`。建议增加对 `CSS Nesting`、`@scope`、Popover/View Transitions、`text-wrap: balance` 等 Chrome ≥111 特性的扫描（或至少在 CI 里对 Win7 分支跑一次 Chromium 108 的冒烟截图）。**这是 Win7 分支能否长期活着的保险丝**，见 1.3 节。

### 5.3 【壳内处理，主项目无需改】

- `window.open(...)` / 下载链接 → `setWindowOpenHandler` 交系统浏览器；
- `navigator.clipboard` 在 `http://` 下不是 secure context，`GatewayEndpointsPanel.tsx:43-47` 已有降级 → 内网建议上 HTTPS，或 Phase 3 由 preload 提供剪贴板桥；
- `nginx.conf:45` 的 `X-Frame-Options: SAMEORIGIN` 不影响（壳是顶层窗口，不嵌 iframe）；
- 后端 `CORSMiddleware` 白名单（`config.py:15`）不用改：页面与 API 同源。

---

## 六、能力矩阵：桌面客户端能得到什么、得不到什么

| 类别 | 内容 |
|---|---|
| **完整保留（零损失）** | 对话/Agent 编排、审批与 Plan mode、知识库与混合检索、PPT 生成、Univer 文档/表格、网站智能体与部署审批、MCP 工具、LLM 提供商管理、权限/审计/用量看板、LDAP/OIDC 登录、SSE 流式输出——因为页面就是服务器提供的那一份 |
| **新增（壳给）** | 独立图标与窗口、单实例、托盘、开机自启、原生通知、服务器地址运行时配置与探活、断线失败页与一键重连、外链/下载交系统浏览器、GPU 兜底开关、统一版本与批量分发、统一内核消除终端浏览器差异 |
| **明确不做** | ① 本地跑后端（第 1.2 节 5 条硬阻断）；② 完全离线单机（连不上 LLM 就没有核心功能）；③ 把壳做成通用浏览器；④ 在壳里塞本地 Agent 能力（见第七节） |
| **已知退化** | `http://` 内网下 `navigator.clipboard` 走降级；EOL 内核无安全补丁（靠网络隔离与白名单缓解）；Win7 分支前端特性永久停在 Chrome ≤109 的能力集 |

---

## 七、与既有「本地电脑 Agent 化」调研的关系（别混为一谈）

`docs/research/调研-本地电脑Agent化方案.md` 的目标是「**让 AI 操作用户电脑**」（装软件、跑脚本、读文件），其 P0 组合 C 是「纯 WebSocket + 自研本地 agent」，状态是「仅调研，本次不实现」。

本次「桌面客户端」的目标是「**给现有 Web 应用一个可安装的桌面入口**」。两者不是同一件事，**不要把本地 agent 塞进这个 Electron 壳**：
- 塞进去会把一个「只渲染可信页面的 EOL 内核」变成「持有本地文件/进程执行权的 EOL 内核」，安全模型直接崩塌；
- 该调研也明确建议 Win7 agent 用 **Go/Rust 静态编译或 .NET 4.7.2**，以避开 Win7 缺 `api-ms-win-*` DLL 的坑——与 Electron 壳的技术栈不同。

**正确的衔接**：壳只作为**分发与身份载体**——未来若启动组合 C，可复用壳的安装通道、设备标识与升级机制，但 agent 是独立进程、独立权限边界、独立审计（`docs/research/调研-本地电脑Agent化方案.md:138-159` 的设备级只读 + 客户端原生确认框必须保留）。

---

## 八、安全风险与缓解（EOL 内核是本次唯一重大风险，必须明文接受）

| 风险 | 缓解 | 验收方式 |
|---|---|---|
| Chromium 108 自 2023-10 起无安全补丁，已知 CVE 不再修 | ① 只在内网/离线使用，不暴露公网；② 导航白名单只允许配置的服务器 origin；③ 无地址栏、无 `webview`、外链一律交系统浏览器；④ `nodeIntegration:false` + `contextIsolation:true` + `sandbox:true` + 权限全拒绝 + CSP；⑤ 壳不解析任意本地 HTML，不做通用浏览器 | 渗透/代码审计逐条核对；构造恶意页面验证无法导航到外部域、无法触达 Node |
| AI 生成 HTML 预览 XSS → 读 token | 第 5.1 节修复 iframe sandbox；`safePreview.ts` 的 CSP 复用 | 构造带 `parent.localStorage` 读取的 srcdoc 用例，断言取不到 |
| localStorage 令牌明文落盘 | 一期接受（与浏览器等价）；磁盘加密/受控用户目录由 IT 保障；Phase 3 可选转存凭据库 | 记录在交付说明 |
| 服务器地址被篡改成恶意站点 | 配置写入校验 `http/https` + 探活；企业版可由 `server.conf` + 组策略锁定为只读（隐藏「修改地址」菜单） | 配置文件只读策略实测 |
| Win7 自身 EOL + 补丁缺失导致启动失败 | 第 2 节补丁链作为部署前置，安装包启动前自检并给出可读提示 | 干净 Win7 SP1 虚机 + 打补丁/不打补丁两组实测 |
| TLS 1.2 / SHA-2 证书链 | 服务器开 TLS1.2、内网 CA 预导入、签名带时间戳 | Win7 实机 `https://` 握手实测 |
| 安装包供应链 | 锁定 `electron@22.3.27` 与全部 `devDependencies` 精确版本 + 校验和；构建产物签名；离线保存该版本二进制与其 SHASUMS | `npm ci` 可复现构建 |

> **决策项**：需业务方/安全方书面接受「在 Win7 上使用 2023 年冻结的浏览器内核」。若无法接受，唯一替代是**方案 G（Chrome/Edge 109 `--app` 快捷方式）**——把内核补丁责任交给 IT 统一管理的 109（同样 EOL，但少了自持二进制），代价是没有托盘/配置/单实例/升级能力。

---

## 九、分期实施与验收

### P0 — 可用壳（先验证内核，再谈功能）
1. 建 `desktop/` 骨架 + `profiles/win7.json` + `build-win7.mjs`，产出可安装的 NSIS x64/ia32 包。
2. `main.js` 实现第 4.3 节全部约束；`config.js` + 首次启动配置窗口 + `offline.html`。
3. **在干净 Win7 SP1 虚机上按第 2 节补丁链实测启动**，跑一遍前端冒烟：登录 → 深色模式 → 卡片 `:has()` 布局 → `@container` 聊天输入 → Univer 文档 → SSE 流式对话 → 网站预览 iframe。
4. 主项目配合完成第 5.1 节修复 + 回归。

**验收线**：Win7 x64/x86 实机能装、能连、能完整跑一次带工具调用的 Agent 对话；`will-navigate` 白名单拦截生效；无 Node 能力泄露；断网显示失败页而非白屏。

> 建议把 **P0 第 3 步提前做成一个 1 天的「Electron 22.3.27 空壳 + loadURL 现有服务器」尖刀验证**：如果老机器 DirectWrite/GPU/补丁链跑不通，立刻切备选 B（NW.js 0.72）或 G，避免后面白做。

### P1 — 原生外壳能力
托盘与单实例完善、开机自启开关、原生通知、失败自动重连与探活、外链/下载接管、GPU 开关、服务器地址只读策略、IT 分发文档（含补丁链与组策略模板）。

### P2 — 工程化
Win7 与主线两条构建线接入 CI（Win10/11 构建机）、产物签名与校验和、`verify-css.mjs` 增加 Chrome ≥111 特性门禁、`/api/v1/health/` 下发 `min_client_version`、桌面版本台账与下线预案。

**粗略工作量**（不含 IT 铺补丁与批量分发）：P0 约 6–9 人日（含实机验证）、P1 约 3–5 人日、P2 约 3–5 人日；主项目配合约 1–2 人日。

---

## 十、长期约束与退出策略

1. **前端冻结线**：Win7 分支存活期间，前端禁止引入无 `@supports` 兜底的 Chrome ≥111 特性（1.3 节）。这条应写进 `AGENTS.md` 或前端 CI 门禁，而不是只写在本文档。
2. **Win7 内核永不动**：`22.3.27` 不升级、不打第三方补丁、不引新原生模块；主线升级 Electron 时不得顺带改 `desktop/src/` 里被 Win7 分支共用的 API 用法。
3. **退出**：Win7 存量机清零后，删 `profiles/win7.json` + `build-win7.mjs` + ia32 产物与补丁链文档，`desktop/src/` 与主线合流；前端 Chrome 85/109 兼容门禁届时可另行评估是否放宽。
4. **不要把 Windows 7 支持扩散到后端**：`backend/` 的 POSIX 沙箱、Python 3.13、Node 20 均为当前架构的既定事实，本次不为桌面端做任何后端 Windows 化改造。

---

## 十一、待验证清单（P0 阶段必须闭环）

| 项 | 为什么 |
|---|---|
| Electron 22.3.27 二进制在**目标企业真实 Win7 镜像**上能否启动 | 补丁组合、DirectWrite、老显卡驱动差异大，官方声明 ≠ 实机可用 |
| Chromium 108 下 `:has()`/`@container`/`:where()` 的实际渲染 | 静态分析只能给版本下限，需真实截图比对（参考 `docs/research/调研-Univer办公能力接入.md:72-93` 的实测方法） |
| 内网服务器 TLS 1.2 握手与证书链 | Win7 根证书库与 SHA-2 补丁 |
| 32 位 Win7 实机 | 存量老机器可能是 x86 |
| `electron-builder` 26.x 生成的 NSIS 在 Win7 上安装/卸载 | 安装包自身也要过 SHA-2 与权限关 |
| iframe sandbox 修复后网站预览是否仍正常 | 去掉 `allow-same-origin` 可能影响内联预览脚本 |
| SSE 在 Electron 22 下的长连接稳定性 | `fetchEventSource` + 60s 空闲超时 + `openWhenHidden`，壳切后台行为需实测 |
| 三种登录方式在壳内完整往返（密码 / 验证码 / LDAP） | 表单提交、401 清会话跳 `/login`、令牌持久化、退出后真失效 |
| 启用 OIDC 时同窗口跳 IdP 并回调 | `will-navigate` 白名单 + CSP `form-action`，最容易把登录卡死 |
| 切换服务器地址 / 托盘「清除登录状态」 | 确认旧令牌不会串到新地址、重载后回到登录页 |

---

## 参考（一手资料）

- Electron 官方：`Farewell, Windows 7/8/8.1`（Electron 22 = Chromium 108 = 最后支持 Win7；2023-10-10 EOL；不为 Win7 追加安全修复）
- Microsoft Edge Dev Blog 2022-12-09：Edge 109 / WebView2 109 为 Win7 最后一版，SDK 1.0.1519.0+ 不支持 Win7
- NW.js 版本指南：0.72.0（Chromium 109）为最后支持 Win7 的版本
- CSS 特性下限：`:where()` 88 / `:has()` 105 / `@container` 105 / `color-mix()`·`oklch()` 111
- 本仓库：`docs/research/调研-本地电脑Agent化方案.md`、`docs/research/调研-Univer办公能力接入.md`、`deploy/DEPLOY.md`、`deploy/OFFLINE-DEPLOY.md`、`AGENTS.md`
