# 内网爬虫的插件形态决策与接入指南

> 面向：**你要自己写爬虫代码**，AgenticOS 负责决定「这个爬虫以什么形态存在」，
> 以及「怎么把它接进来」。
>
> 结论先行：**你的爬虫 = 一个独立进程的 MCP 服务**。AgenticOS 只当客户端，
> 你们两边互不改对方代码。

---

## 一、三个候选形态，以及为什么选第三个

用户的约束很明确：**爬虫代码由用户自己写**，且**内网实现不能污染外网仓库与外网依赖树**。
在这个约束下只剩三种可能：

| 形态 | 爬虫代码放哪 | 你换爬虫要不要改 AgenticOS | 内网依赖会不会污染外网 | 结论 |
|---|---|---|---|---|
| A. 内置工具（tool） | 进主项目 `app/tools/` | **要改**（加/改工具函数） | **会**（Playwright 等进主项目 pyproject） | ✗ |
| B. 主项目里的 HTTP 薄壳 | 薄壳进主项目，真爬虫在内网 | **要改**（`/probe /fetch /browse` 端点契约写死在主项目） | 不会（真爬虫独立） | ✗ |
| C. 独立 MCP 服务 | 完全在内网，AgenticOS 不碰 | **不用改**（重新连接即可） | 不会 | ✓ |

**A 为什么不行**：内网爬虫要用 Playwright、可能有自签 CA、内网 DNS。
只要爬虫代码进主仓库，它依赖的东西就会进主项目的依赖树 —— 外网部署会拖着一堆
内网才用得上的包，CI 与镜像一起变大。而且「用户写代码」这件事本身就和
「代码进主仓库」冲突。

**B 为什么不行**：薄壳把接口契约写死在了主项目（`/probe`、`/fetch`、`/browse`
三个端点、参数形状、返回结构）。你换一套爬虫实现（改成表单登录、加上 JS
渲染、换数据源），主项目就得跟着改代码 —— 这等于把你「自己写爬虫」的自主权
又收回去了。而且它不是标准协议，主项目要自己写客户端、自己处理 SSE、自己做重连。

**C（MCP）为什么行**：MCP 是一份公开的协议规范，不是我们的私有约定。

```
┌─────────────────────────┐        MCP 协议         ┌──────────────────────────┐
│  你的内网环境            │  ───────────────────►   │  AgenticOS（外网/主仓库）  │
│                         │   tools/list           │                          │
│  · 爬虫实现（你写）      │   tools/call           │  · 发现工具、注册给智能体  │
│  · Playwright/requests   │   初始化握手            │  · 注入凭据、追问用户      │
│  · 内网证书 / DNS        │  ◄───────────────────  │  · 审批、日志、审计        │
│  · 你的业务逻辑          │   返回结果/错误         │                          │
└─────────────────────────┘                        └──────────────────────────┘
        独立进程 · 独立依赖 · 独立镜像                    只依赖协议，不依赖你的实现
```

- 你换爬虫实现 → 改你那边的代码 → 主项目**一行不改**，管理后台点一下「重新连接」。
- 你的 Playwright、内网证书、内网 DNS 全在那个进程里 → 主项目依赖树**零污染**。
- 平台侧的凭据注入、用户追问、审批、审计**照常生效**（协议层只是工具调用，
  平台在调用前后包一层）。

> 补充判断：**不需要为了「可插拔」把 Python 内核改写成 Cordis/dsh 那样的插件内核。**
> MCP 协议本身就是那份「标准接缝」，重写内核的收益为零。

---

## 二、借鉴 dsh 的可插拔机制：学什么、不学什么

dsh（DeepSeek Harness）是 MIT 许可、跑在 Cordis 插件内核上的 Agent 框架，
标语是「Everything is a Plugin」。它的内核**没有特权** —— 模型适配器、会话日志、
工具注册表、agent loop 本身都是插件。

它最有价值的是三个概念：

| dsh 概念 | 含义 | AgenticOS 里的对应物 | 本轮落地情况 |
|---|---|---|---|
| **能力接缝**（capability seam） | Service Definition / Provider / Consumer 三方分离，Consumer 只依赖**定义**，不依赖任何具体提供方 | MCP 协议 = 定义；你的服务 = Provider；AgenticOS = Consumer | ✅ 已有（协议级） |
| **按需挂载能力面**（trimmed capability surface） | 不是所有插件都挂到所有消费者上，按需装配 | 「智能体 profile ↔ MCP 服务器授权」 | ✅ **本轮新增**（`agent_profile_mcp_servers` 表） |
| **可逆副作用**（revertible effects） | 注册项在卸载时干净回滚，支持热重载 | MCP 连接的生命周期管理 | ✅ **本轮修复**（`disconnect()` 之前只关从未赋值的 `_session_manager`，每次重连泄漏一批旧连接） |

**不学的部分**：dsh 的内核是 Node.js/TypeScript + Cordis，而我们是 Python + wuwei。
把主项目改写成 Cordis 插件内核，属于「重写一个能跑的系统来换取零增量收益」。
真正值得学的是**接缝设计**，不是运行时。

dsh 的「Consumer 只依赖定义」这一点反过来给了我们一个警告：
**AgenticOS 之前是全局注册所有 MCP 工具到每一个 Agent** —— 相当于把
「内网爬虫」这个能力面挂到了所有智能体上。任何智能体都能调任意内网服务，
这对内网场景不可接受。所以本轮加了 profile 级授权。

---

## 三、wuwei 支持 MCP 吗？—— 支持，而且我们项目里这条通道此前是**死的**

**框架层**：`wuwei/mcp/` 导出全套能力 —— `MCPConfig`、`MCPServerConfig`、
`BaseMCPClient`、`HTTPMCPClient`、`StdioMCPClient`、`MCPToolAdapter`、
`MCPSessionManager`，走官方 `mcp` SDK，支持 stdio / http / sse 三种传输。

**项目层（踩坑）**：wuwei 把 MCP 放在 **optional extra**（`wuwei[mcp]`）里，
而我们的 `pyproject.toml` / `uv.lock` **从来没有声明过这个依赖**。
结果就是：管理后台能配 MCP 服务器、能填地址、能点「连接并发现工具」，
一连就 `ModuleNotFoundError: No module named 'mcp'` —— 通道形同虚设。

已修：`pyproject.toml` 新增 `mcp>=2.2,<3` 作为**生产依赖**（不是可选 extra），
并加了注释说明理由。守护测试：`tests/test_mcp_plugin.py::TestMcpSdkDependency`。

---

## 四、你的爬虫怎么接入：三个约定

### 约定 1：凭据用 `$CREDENTIAL.<字段>` 占位，不要让模型直接填

```python
def fetch_report(url: str, token: str = "$CREDENTIAL.report_token"): ...
```

平台在调用前把它替换成**当前登录用户自己配置的**凭据
（存在 `external_user_credentials`，加密存储）。

- 凭据值**不进模型上下文**、**不进审计日志**、**不写业务日志** —— 它只流向 MCP 服务。
- 没配凭据时，平台返回结构化提示：`{"error": "...请在「集成」页为 xxx 配置凭据...", "missing_credentials": ["report_token"]}`。

**占位符可以放在任意嵌套位置**，平台会递归解析：

```python
headers={"X-Token": "$CREDENTIAL.report_token"}              # dict
fields=[{"name": "user", "value": "$CREDENTIAL.username"}]  # list[dict]
```

**推荐写成参数默认值**（如上 `token: str = "$CREDENTIAL.report_token"`）：

- 模型不会主动填这个参数 → 平台从工具的 inputSchema 里把默认值取出来替换掉；
- 写成必填参数的话，模型反而会**自己编一个值**填进去 —— 那就等于没做凭据隔离。

> 这一条是本轮修掉的真实缺陷：早期实现只解析**顶层字符串**，
> `headers={"X-T": "$CREDENTIAL.token"}` 里的占位符根本没被解析，
> 结果字面量 `$CREDENTIAL.token` 被原样发给了内网站点。

### 约定 2：一次性输入用 `$INPUT.<字段>` 占位

验证码、临时口令这类既不该落库、也不该让模型编造的值：

```python
def submit_code(sms: str = "$INPUT.sms_code"): ...
```

平台会通过 `UserInputBlocker` 阻塞，在前端弹表单问用户，拿到真实值后再继续调用。
值只在内存里，不落库。

### 约定 3：只读工具要声明 `readOnlyHint`

```python
@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
```

平台据此决定是否需要人工审批（上游 `MCPToolAdapter` 会把它映射成
`ToolExecutionPolicy.side_effect` / `requires_approval`）。写操作（提交、审批、
删除）**不要**声明 → 平台会要求人工确认。

### 附：占位符字段名不能带连字符

正则是 `\$(CREDENTIAL|INPUT)\.([A-Za-z0-9_]+)`。
否则 `"$CREDENTIAL.a-$CREDENTIAL.b"` 会被解析成字段 `a-`。

---

## 五、平台侧为内网场景补的能力（都已落地）

| 能力 | 官方 SDK / wuwei 的缺口 | 平台侧做法 |
|---|---|---|
| **自签证书** | `create_mcp_http_client()` 只有 headers/timeout/auth，**没有 verify**；上游 `HTTPMCPClient._open_streams` 直接用它且无替换点 | 动态创建 `HTTPMCPClient` 的子类覆写 `_open_streams`，自建 httpx 客户端传 `verify`（必须**继承**，组合 + `__getattr__` 转发不生效） |
| **出网网段限制** | 无 | 管理后台配 `allowed_cidrs`，平台连 MCP 服务这一跳做 CIDR 校验（复用 `app/services/intranet_policy.py`） |
| **profile 级授权** | 工具全局注册 | `agent_profile_mcp_servers` 表 + `get_tools_for_profile()`；`user_accessible=False` 需显式授权 |
| **凭据注入 / 用户追问** | 上游 `MCPToolAdapter` 只搬 `inputSchema`，handler 直接 `call_tool` | `app/services/mcp_tool_bridge.py` 在调用前包装 handler |
| **单服务故障隔离** | 连不上时抛 `CancelledError`（**BaseException**），上游 `connect()` 只 catch `Exception` → 穿透后**整个** connect 掀翻，健康服务也拿不到工具 | 每服务器在**独立 task** 里连接；父任务用 `cancelling()` 区分「传输层取消」与「外层真取消」 |
| **连接泄漏** | 上游 `disconnect()` 只关自己的 `_session_manager`，而我们走自己的 `_connect_servers` → 从不赋值 | `disconnect()` 显式关闭 `self._clients` 里每个连接 |

---

## 六、实操：跑起来

### 1. 写你的爬虫服务

参考实现：`deploy/intranet/crawler_mcp/crawler_mcp.py` —— **可以直接复制改写**。
它演示了工具定义、SSRF 防护、三个占位约定、只读标注。

依赖只要两个：

```bash
pip install "mcp>=2.2,<3" httpx
```

### 2. 起服务

```bash
python crawler_mcp.py
# 默认监听 127.0.0.1:8931/mcp（streamable http）
```

> `mcp` 2.x 里 `FastMCP` 已改名为 `MCPServer`：
> `from mcp.server.mcpserver import MCPServer`，
> 服务端方法 `run_streamable_http_async(host, port, streamable_http_path="/mcp")`。

### 3. 在 AgenticOS 里登记

**管理后台 → 集成管理 → MCP 服务器 → 新增**：

| 字段 | 填什么 |
|---|---|
| 名称 | `intranet_crawler`（唯一，工具会命名为 `mcp__intranet_crawler__<tool>`） |
| 传输 | `http`（或 `stdio`，此时填启动命令而不是地址） |
| 地址 | `http://127.0.0.1:8931/mcp` |
| 放行自签证书 | 内网自签 CA 时勾上（对应 `verify_tls=false`） |
| 允许所有智能体使用 | 内网服务**建议不勾** —— 改成在具体智能体里显式授权 |
| 允许网段 | 平台连 MCP 服务这一跳允许访问的 CIDR，空=不限制 |
| 关联集成 | 选一个「集成」，用户的凭据从那里取（`$CREDENTIAL.x` 才有来源） |

### 4. 在智能体里授权

**智能体编辑 → MCP 服务** → 勾选要挂载的服务器 → 保存。

只有被授权的智能体能看到这些工具；`user_accessible=true` 的服务器对所有智能体可见。

### 5. 连通性验证

管理后台点「连接并发现工具」→ 应看到工具列表。失败时看**服务端的日志**：
MCP 协议会把工具异常包装成通用文案（`Error executing tool <name>`），
**具体原因不透传**给客户端（协议设计，避免泄漏内部细节），所以拒绝原因在服务端日志里。

---

## 七、已知限制

1. **MCP 传输绑定创建它的任务**。`connect()` 与 `call_tool()` 必须在同一个事件循环里。
   生产环境是单 uvicorn 循环（连接在后台任务建立、调用在同一循环），没有这个问题；
   测试里若用两次 `asyncio.run` 就会报
   `Attempted to exit cancel scope in a different task`。守护测试：`tests/test_mcp_cross_task.py`。
2. **工具异常的具体原因不透传**。协议层设计如此，服务端日志是唯一真相来源。
3. **凭据来源是「集成」级**。一个 MCP 服务器只能关联一个外部系统，
   多个站点需要多份凭据时要拆成多个 MCP 服务器（或在服务侧按参数路由）。
4. **尚未做浏览器实测**：前端 MCP 授权 UI 的真实点击流程还没在浏览器里验证过
   （代码已改、类型已过 lint）。
5. **镜像未实际 `docker build` 验证**：Playwright 的 Chromium 下载在内网可能需要配镜像源。

---

## 附：相关代码位置

| 内容 | 位置 |
|---|---|
| 参考实现（你的爬虫照这个写） | `deploy/intranet/crawler_mcp/crawler_mcp.py` |
| 平台侧包装（凭据/追问/错误归一） | `backend/app/services/mcp_tool_bridge.py` |
| 连接管理（自签证书/网段/隔离/泄漏） | `backend/app/services/mcp_service.py` |
| profile 授权 API | `backend/app/api/v1/endpoints/mcp_admin.py` |
| 表结构与迁移 | `backend/app/db/models.py`、`backend/alembic/versions/0015_mcp_intranet_access.py` |
| 前端 | `frontend/src/services/mcpService.ts`、`frontend/src/components/admin/McpManagementPanel.tsx`、`frontend/src/pages/AgentEditor.tsx` |
| 测试 | `backend/tests/test_mcp_plugin.py`（19）、`test_mcp_crawler_e2e.py`（5，真实起服务）、`test_mcp_cross_task.py`（1） |
| 更大的方案文档 | `docs/内网爬虫与无头浏览器方案.md` |
