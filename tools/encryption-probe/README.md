# 透明加密上传：方案与成本核算

## 你的场景

```
用户电脑（装了亿赛通客户端，文件是透明加密的）
        ↓  浏览器上传
Linux Docker 容器（你的网站后端）
```

关键事实：**Linux 容器物理上读不到用户磁盘**。明文只能由用户电脑上的某个进程读出来，
再通过网络送到服务器。所以问题不是"Linux 怎么解密"，而是：

> **用户电脑上，谁去读那个文件？它读到的到底是明文还是密文？**

答案由透明加密驱动的白名单决定。驱动按"发起 I/O 的进程"判断：

```
浏览器读文件 → 驱动查 Chrome/Edge 在不在白名单
                 ├── 在  → 返回明文 → HTTP 传明文 → Linux 收到明文  ✅ 零开发
                 └── 不在 → 返回密文 → HTTP 传密文 → Linux 收到密文  ❌ 需要辅助
```

---

## 先做决定性判断（5 分钟，零成本）

### 方法 A：浏览器内直接判定（最快）

```cmd
cd tools\encryption-probe
python -m http.server 8899
```

浏览器打开 `http://127.0.0.1:8899/probe.html`，拖入一个**真实业务文件**
（排班表、报表、合同，不要用新建的空文件）。

页面会直接告诉你：

| 显示 | 含义 |
|---|---|
| ✅ 明文 | 浏览器在白名单，**零开发** |
| ❌ 密文 | 浏览器不在白名单，需要客户端辅助 |

### 方法 B：走真实上传链路

后端已加诊断端点 `/api/v1/files/probe`（不落盘，只看文件头）。前端也已加
`probeEncryption()` / `probeLocally()`。在诊断页填上你的上传地址，点"发送验证"，
就能同时验证"浏览器读明文"和"服务端收明文"两段。

### 方法 C：命令行对照（排除干扰）

```powershell
# 1. 资源管理器复制同一文件到不加密目录（如 D:\Public）
# 2. 比较文件头
$b1 = [IO.File]::ReadAllBytes('D:\加密目录\排班表.xlsx')
$b2 = [IO.File]::ReadAllBytes('D:\Public\排班表.xlsx')
"原目录 : " + (($b1[0..3] | % {'{0:X2}' -f $_}) -join ' ')
"明文目录: " + (($b2[0..3] | % {'{0:X2}' -f $_}) -join ' ')
```

- 原目录 = 自定义魔数、明文目录 = `50 4B 03 04` → 目录加密，浏览器读原目录是密文
- 两边都是 `50 4B 03 04` → 该目录本来就不加密，需换真正加密的目录测

---

## 场景一：浏览器在白名单（最可能，成本 ≈ 0）

**判断依据**：DLP 厂商必须把浏览器加白，否则用户在任何一个 Web 系统（OA、邮箱、
钉钉、企业微信、任何内网系统）都无法上传附件，业务直接瘫痪。这是行业默认配置。

### 你要做的事

**什么都不用做。** 现有的 `/api/v1/files/upload` 收到的就是明文原始字节：

```python
# backend/app/api/v1/endpoints/files.py 现有逻辑
content = await file.read()          # ← 这里已经是明文
stored_path.write_bytes(content)     # 原样落盘，排版 100% 保留
```

后端处理时直接用标准库：

```python
import io, openpyxl
wb = openpyxl.load_workbook(io.BytesIO(content))     # xlsx，样式/合并/列宽全在
from docx import Document
doc = Document(io.BytesIO(content))                   # docx
from pptx import Presentation
prs = Presentation(io.BytesIO(content))               # pptx
import pikepdf
pdf = pikepdf.open(io.BytesIO(content))               # pdf
```

### 成本

| 项 | 工作量 |
|---|---|
| 后端改动 | **0 行**（现有上传逻辑已正确） |
| 前端改动 | 0 行（可选：加一个明文/密文提示，已提供 `probeLocally()`） |
| 运维改动 | 0 |
| 上线周期 | 0 |
| 新增依赖 | 0 |

**唯一要做的事**：跑一次诊断确认，然后正常开发业务。

### 建议顺手加的一道保险

上传时判定一次，密文直接拒收并提示用户，避免脏数据进库：

```python
# files.py 里加
kind, detail = _classify_bytes(content)
if kind == "cipher":
    raise HTTPException(
        status_code=422,
        detail="文件为加密格式，请先解密后再上传，或联系管理员把本站加入受信站点。",
    )
```

已实现，见 `_classify_bytes`。前端也有对应提示。

---

## 场景二：浏览器不在白名单（少数情况）

**触发原因**（任一即可）：

1. DLP 策略只加了 Office / WPS / PDF 阅读器，没加浏览器
2. 有"受信站点"白名单，你的站点不在里面 → 上传到非受信站点时文件保持加密
3. 网络侧 DLP 网关加密了上传报文（浏览器读明文，但出网时被加密）

### 2.1 先试最省成本的：申请受信站点

亿赛通这类产品都有"受信站点 / 上传白名单 / Web 应用白名单"配置，正是为
"内网 Web 系统要处理用户上传的加密文档"设计的。

**申请材料**：

| 项 | 内容 |
|---|---|
| 站点域名 / IP:端口 | 你的平台地址 |
| 用途 | 内部系统，接收用户上传的办公文档做业务处理 |
| 生效范围 | 全体用户 或 指定部门 |
| 期望行为 | 上传到该站点时，浏览器读取的文件以明文发送 |

**这是最划算的路径**：管理员改一条策略，你零开发。成本 = 一次沟通。

### 2.2 申请不到时：客户端辅助（有开发量）

在用户电脑上跑一个常驻小程序，它读明文后直接传给服务器。三种形态：

| 形态 | 用户操作 | 开发量 | 部署难度 |
|---|---|---|---|
| **A. 本地小工具（推荐）** | 拖文件到工具窗口，工具自动上传 | 中 | 中（要分发安装） |
| **B. 浏览器插件 + 本地服务** | 正常用网页，插件拦上传并替换字节 | 高 | 高（插件签名+策略） |
| **C. 厂商 SDK** | 无感，用户正常上传 | 低（只调 SDK） | 低（要商务采购） |

#### 形态 A：本地小工具

复用已有的 `tools/cdg-bridge`（已编译验证）：

```
用户电脑：
  uploader.exe（小工具）
    ├─ 加载 bridge.dll（借 rundll32 白名单身份读明文）
    ├─ 拖入文件 → 读明文原始字节
    └─ POST 到你的 Linux 平台 /api/v1/files/upload

Linux 平台：
  收到明文，与场景一完全一样
```

开发量估算：

| 模块 | 人天 |
|---|---|
| 复用 bridge.dll（已完成） | 0 |
| uploader.exe 界面（拖拽+进度+多文件） | 3~5 |
| 登录态打通（token 获取/保存） | 1~2 |
| 打包分发（含 bridge.dll、启动脚本） | 1~2 |
| 测试（多版本客户端兼容） | 2~3 |
| **合计** | **7~12 人天** |

运维成本：每台用户机器要装一次，或走域控/组策略下发。

#### 形态 B：浏览器插件

技术上可行但性价比低：需要拦 `File` 对象并替换为明文字节，插件要企业签名，
还要过 DLP 的"浏览器扩展白名单"。**不推荐**。

#### 形态 C：厂商 SDK

亿赛通 CDG 有客户端集成 SDK（`DecryptFile` / `GetPlainStream` / `IsEncrypted`），
授权后你的程序可直接调。但 SDK 跑在 **Windows 客户端**上，不能跑在 Linux 容器里。
所以仍需一个客户端侧的小程序，只是加解密交给 SDK，不用自己搞 bridge。

| 项 | 说明 |
|---|---|
| 开发量 | 3~5 人天（只写上传逻辑，加解密调 SDK） |
| 成本 | 商务采购（厂商报价，通常按点数/年费） |
| 优点 | 官方支持，版本升级不用重做 |
| 缺点 | 要采购，要厂商配合 |

### 2.3 网络侧 DLP 加密报文

症状：浏览器读明文，但服务端收到密文。这时问题在**网络出口**，不在客户端。

处理：
- 申请把**目标服务器 IP** 加入"免加密传输"名单（比加站点更容易批）
- 或走 HTTPS（部分 DLP 只处理明文 HTTP）
- 或用白名单端口（如 443 常被排除在 DLP 处理之外）

先跑诊断确认属于这一类，再找管理员，不用开发。

---

## 三种方案成本对比

| 方案 | 开发量 | 商务/运维 | 用户体验 | 适用 |
|---|---|---|---|---|
| **场景一：浏览器已白名单** | **0** | **0** | 正常网页上传 | **最可能，先验证** |
| 2.1 申请受信站点 | 0 | 一次沟通 | 正常网页上传 | 管理员能改策略 |
| 2.2A 本地小工具 | 7~12 人天 | 每台装一次 | 要开工具，稍麻烦 | 策略改不了 |
| 2.2C 厂商 SDK | 3~5 人天 | 采购 + 厂商配合 | 无感 | 有预算 |
| 2.2B 浏览器插件 | 15+ 人天 | 插件签名下发 | 无感 | 不推荐 |
| 2.3 网络侧豁免 | 0 | 一次沟通 | 无感 | 报文被加密时 |

---

## 我的建议（按顺序执行）

### 第一步：跑诊断（今天，5 分钟）

```cmd
cd tools\encryption-probe
python -m http.server 8899
```

打开 `http://127.0.0.1:8899/probe.html`，拖入真实业务文件。

**大概率结果：明文。** 那就结束了 —— 你的 Linux 平台收上传即明文，零开发，
排版 100% 保留，正常写业务代码就行。

### 第二步：如果是密文，按这个顺序试

1. **先问管理员能不能加受信站点**（零开发，最划算）
2. 不行 → 问能不能给服务器 IP 加"免加密传输"（零开发）
3. 都不行 → 才考虑客户端小工具（7~12 人天）
4. 有预算 → 问厂商 SDK（3~5 人天 + 采购）

**不要一上来就开发客户端工具**，先确认策略能不能改。很多情况下一条策略就解决。

---

## 已交付的代码

| 文件 | 作用 |
|---|---|
| `tools/encryption-probe/probe.html` | 浏览器内诊断页，拖文件即判定 |
| `backend/app/api/v1/endpoints/files.py` | 新增 `/files/probe` 端点 + `_classify_bytes()` |
| `backend/tests/test_files_probe.py` | 6 个测试，全部通过 |
| `frontend/src/services/fileService.ts` | 新增 `probeEncryption()` / `probeLocally()` |
| `tools/cdg-bridge/` | 完整桥工程（仅在需要客户端辅助时用） |

### 诊断端点用法

```bash
curl -X POST http://your-host:8001/api/v1/files/probe \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@排班表.xlsx"
```

返回：

```json
{
  "filename": "排班表.xlsx",
  "size": 4693,
  "kind": "plain",
  "detail": "OOXML/zip 明文（xlsx/docx/pptx）",
  "head": "50 4B 03 04 14 00 00 00 08 00 19 73 62 5D BD 5C",
  "advice": "链路正常，服务端已拿到明文原始字节，可直接用 openpyxl 等处理。"
}
```

`kind` 三值：`plain`（明文）/ `cipher`（密文）/ `empty`（空文件）。

---

## 关于排版

只要走普通上传，服务端拿到的就是**完整原始文件字节**，排版天然 100% 保留。

后端处理时注意用"字节进出"的库：

| 库 | 保真度 |
|---|---|
| 只存不解析 | 100% |
| `openpyxl` 改单元格 | 高（条件格式、图表可能被重写） |
| `python-docx` 改段落 | 高（页眉页脚、域、修订可能丢） |
| `python-pptx` 改文本 | 高（动画、部分 SmartArt 可能丢） |
| `pikepdf` 改 PDF | 高 |
| 直接改 OOXML zip 部件 | 100%（只替换目标 XML） |

要绝对 100%：解压 xlsx/docx/pptx，只改目标 XML，其余部件原样重新打包。

```python
import io, zipfile

src = zipfile.ZipFile(io.BytesIO(content))
out = io.BytesIO()
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
    for item in src.infolist():
        data = src.read(item.filename)
        if item.filename == 'xl/worksheets/sheet1.xml':
            data = data.replace(b'<t>旧值</t>', b'<t>新值</t>')
        dst.writestr(item, data)      # 其余字节原封不动
new_content = out.getvalue()
```
