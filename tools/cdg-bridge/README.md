# cdg-bridge

在内网透明加密（亿赛通 CDG / 类似 DLP）环境下，让**你自己开发的程序**能原生读写
xlsx / docx / pptx / pdf，且**排版与原始文件一模一样**。

---

## 它解决什么问题

透明加密驱动按「**发起 I/O 的进程是谁**」决定返回明文还是密文：

```
你的程序 CreateFileW("排班表.xlsx")
        ↓
  驱动挂钩 IRP_MJ_READ
        ↓
  查发起进程在不在白名单
        ├── 在  → 返回明文（透明解密）
        └── 不在 → 返回密文（自定义魔数）
```

你的程序加不进白名单 → 那就**借一个已在白名单的进程**执行 I/O。

`rundll32.exe` 是 Windows 自带的 DLL 宿主，DLP 厂商必须把它加白（否则系统功能会崩）。
本项目把一段 DLL 加载进 rundll32，所有 `CreateFileW/ReadFile/WriteFile` 都在 rundll32
的进程上下文里执行 → 驱动透明解密 → 拿到**完整原始文件字节**。

字节级搬运 = 排版零损失。字体、颜色、合并单元格、列宽、图表、PPT 母版、PDF 布局，
全部原样。

---

## 目录

```
cdg-bridge/
  src/bridge.cpp          常驻桥 DLL（管道服务）
  src/probe.cpp           最小验证 DLL（3 行核心逻辑，先跑这个）
  build.cmd               编译（VS 2022 MSVC x64）
  start-bridge.cmd        启动常驻桥
  stop-bridge.cmd         停止
  gateway.py              HTTP 网关（给其他主机/其他语言调用）
  python/cdgfs/           Python 客户端包
  examples/diagnose.py    批量判定明文/密文
  examples/schedule.py    排班表读写示例
  bin/                    编译产物
```

---

## 快速开始

### 1. 编译

```cmd
cd tools\cdg-bridge
build.cmd
```

需要 VS 2022（MSVC 14.4x）。产物在 `bin\bridge.dll`、`bin\probe.dll`。

### 2. 先验证「借进程」是否成立

```powershell
rundll32.exe "$PWD\bin\probe.dll,Probe" "D:\Data\排班表.xlsx|D:\Work\dump.xlsx"
Get-Content D:\Work\dump.xlsx.probe.txt
```

看 `src_head` / `dst_head`：

| 输出 | 含义 |
|---|---|
| `50 4B 03 04` | ✅ 成立：宿主拿到明文，写出的也是明文 |
| `D0 CF 11 E0` | ✅ xls/doc/ppt 明文 |
| `25 50 44 46` | ✅ PDF 明文 |
| 其他魔数 | ❌ 宿主不在白名单，换宿主（见「换宿主」） |

### 3. 启动常驻桥

```cmd
start-bridge.cmd
```

或手动：

```powershell
Start-Process rundll32.exe -ArgumentList '"D:\code\AgenticOS\tools\cdg-bridge\bin\bridge.dll",Start cdgbridge' -WindowStyle Hidden
```

### 4. 用 Python 读写

```python
import sys; sys.path.insert(0, r'D:\code\AgenticOS\tools\cdg-bridge\python')
import cdgfs

print(cdgfs.ping())          # {'pid': ..., 'exe': 'rundll32.exe'}

raw = cdgfs.read_bytes(r'D:\Data\排班表.xlsx')   # 完整明文原始字节
print(cdgfs.classify(r'D:\Data\排班表.xlsx'))    # ('plain', 'OOXML/zip plain ...')
```

---

## 平台接入：三种方式，按你的架构选

### 方式一：同机同进程（最省事）

平台就跑在这台装了客户端的 Windows 机器上，直接把 `open()/save()` 换成 `cdgfs`：

```python
import io, openpyxl, cdgfs

raw = cdgfs.read_bytes(path)
wb  = openpyxl.load_workbook(io.BytesIO(raw))
ws  = wb.active
ws['B5'] = '李四'
buf = io.BytesIO(); wb.save(buf)
cdgfs.write_bytes(path, buf.getvalue())     # 落盘自动加密成合法密文
```

或者用文件对象接口，代码几乎不用改：

```python
with cdgfs.File(path, 'rb') as f:
    raw = f.read()

with cdgfs.File(path, 'wb') as f:
    f.write(buf.getvalue())
```

### 方式二：HTTP 网关（跨进程 / 跨主机 / 跨语言，推荐）

平台跑在别的机器、别的语言、容器里，就在**装了客户端的那台 Windows** 上开网关：

```cmd
python gateway.py --port 8765 --bind 0.0.0.0 --token YOUR_TOKEN
```

之后任何地方都能调：

```bash
# 下载明文原始字节
curl -H "X-Token: YOUR_TOKEN" \
     "http://WIN_HOST:8765/file?path=D:/Data/排班表.xlsx" -o 排班表.xlsx

# 上传写回（body 是字节流）
curl -X PUT -H "X-Token: YOUR_TOKEN" --data-binary @排班表.xlsx \
     "http://WIN_HOST:8765/file?path=D:/Data/排班表.xlsx"

# 判定明文/密文
curl -H "X-Token: YOUR_TOKEN" \
     "http://WIN_HOST:8765/classify?path=D:/Data/排班表.xlsx"

# 目录列表
curl -H "X-Token: YOUR_TOKEN" \
     "http://WIN_HOST:8765/list?dir=D:/Data&pattern=*.xlsx"
```

| 接口 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 服务与桥状态（无需 token） |
| `/file?path=` | GET | 下载明文原始字节 |
| `/file?path=` | PUT | 上传并写回（body 为字节） |
| `/head?path=&n=16` | GET | 文件头 hex |
| `/classify?path=` | GET | `plain` / `cipher` / `unknown` |
| `/stat?path=` | GET | 大小、时间、属性 |
| `/list?dir=&pattern=` | GET | 目录列表 JSON |
| `/copy?src=&dst=` | POST | 服务端复制（明文字节直通） |
| `/mkdir?path=` | POST | 建目录 |
| `/file?path=` | DELETE | 删除 |

已实测通过的客户端：

```csharp
// C# (.NET Framework 也可，用 WebClient)
var wc = new WebClient();
wc.Headers.Add("X-Token", "YOUR_TOKEN");
var b = wc.DownloadData("http://WIN_HOST:8765/file?path=D:/Data/a.xlsx");
File.WriteAllBytes("a.xlsx", b);
```

```javascript
// Node.js
const http = require('http');
http.get({ host:'WIN_HOST', port:8765,
  path:'/file?path='+encodeURIComponent('D:/Data/a.xlsx'),
  headers:{'X-Token':'YOUR_TOKEN'} }, res => {
    const chunks=[]; res.on('data',c=>chunks.push(c));
    res.on('end',()=>fs.writeFileSync('a.xlsx', Buffer.concat(chunks)));
});
```

```go
// Go
req, _ := http.NewRequest("GET", "http://WIN_HOST:8765/file?path="+url.QueryEscape("D:/Data/a.xlsx"), nil)
req.Header.Set("X-Token", "YOUR_TOKEN")
resp, _ := http.DefaultClient.Do(req)
b, _ := io.ReadAll(resp.Body)
```

```java
// Java
HttpClient c = HttpClient.newHttpClient();
HttpRequest r = HttpRequest.newBuilder(URI.create("http://WIN_HOST:8765/file?path=D:/Data/a.xlsx"))
    .header("X-Token","YOUR_TOKEN").build();
byte[] b = c.send(r, HttpResponse.BodyHandlers.ofByteArray()).body();
```

```bash
# PHP
curl -H "X-Token: YOUR_TOKEN" "http://WIN_HOST:8765/file?path=D:/Data/a.xlsx" -o a.xlsx
```

### 方式三：直接走命名管道（不装 HTTP，延迟最低）

管道协议是纯文本行头 + 裸字节，任何语言都能实现：

```
请求：  READ\t<path>\n
响应：  OK\t<size>\n<bytes>

请求：  WRITE\t<path>\t<size>\n<bytes>
响应：  OK\n

请求：  PING\n
响应：  OK\tpong\t<pid>\t<exe>\n

失败统一：ERR\t<winerror>\t<msg>\n
```

完整命令集：

| 命令 | 响应 |
|---|---|
| `PING` | `OK\tpong\t<pid>\t<exe>` |
| `INFO` | `OK\tpid=..\texe=..\tuser=..\tpipe=..` |
| `READ\t<path>` | `OK\t<size>\n<bytes>` |
| `READCHUNK\t<path>\t<off>\t<len>` | `OK\t<len>\n<bytes>` |
| `HEAD\t<path>\t<n>` | `OK\t<hex>` |
| `WRITE\t<path>\t<size>\n<bytes>` | `OK` |
| `STAT\t<path>` | `OK\t<size>\t<atime>\t<mtime>\t<ctime>\t<attr>` |
| `LIST\t<dir>\t<pattern>` | `OK\t<count>\n<name>\t<size>\t<mtime>\t<attr>\n...` |
| `COPY\t<src>\t<dst>` | `OK` |
| `DEL\t<path>` | `OK` |
| `MKDIR\t<path>` | `OK` |
| `QUIT` | `OK`（随后宿主进程退出） |

管道路径：`\\.\pipe\cdgbridge`（可用启动参数改，见下）。

---

## 必须 Windows 吗

**桥本身必须 Windows，客户端不必。**

```
┌───────────────────┐        HTTP / 管道        ┌──────────────────────────────┐
│  你的平台          │  ───────────────────────> │  Windows（装了加密客户端）     │
│  Linux / 容器 /    │  <─────────────────────── │  rundll32.exe + bridge.dll   │
│  另一台 Windows    │      明文原始字节          │  真正的文件 I/O 在这里发生     │
└───────────────────┘                            └──────────────────────────────┘
```

- **必须 Windows 的部分**：`rundll32.exe` + `bridge.dll`，因为透明加密驱动只存在于
  Windows 客户端，白名单也只在这台机器上生效。
- **不必 Windows 的部分**：你的平台、你的业务代码、任何调用方。走 HTTP 网关时，
  Linux 容器、macOS、另一台 Windows 都能调，语言随便选。
- 同一个内网里有多台装了客户端的 Windows，可以每台开一个网关，平台按机器路由。

---

## 换宿主（rundll32 不在白名单时）

DLP 策略各不相同，白名单可能是别的系统进程。逐个试，看 `classify` 是否返回 `plain`：

```powershell
# 候选宿主
$hosts = 'rundll32.exe','dllhost.exe','explorer.exe','svchost.exe','SearchProtocolHost.exe','spoolsv.exe'

foreach ($h in $hosts) {
  Start-Process $h -ArgumentList '"D:\code\AgenticOS\tools\cdg-bridge\bin\bridge.dll",Start testpipe' -WindowStyle Hidden
  Start-Sleep -Milliseconds 700
  $env:PYTHONPATH='D:\code\AgenticOS\tools\cdg-bridge\python'
  python -c "import cdgfs; print('$h', cdgfs.classify(r'D:\Data\排班表.xlsx', 'testpipe'))"
}
```

> 注意：`explorer.exe` / `svchost.exe` 不能直接用 rundll32 参数形式加载任意 DLL，
> 它们需要注入或 DLL 劫持。`rundll32.exe` 和 `dllhost.exe`（COM 宿主）最省事。

全部系统进程都不在白名单时（策略只加了 Office/WPS/浏览器），走 **DLL 劫持**：
在 Office 安装目录放一个同名劫持 DLL（`version.dll` / `msimg32.dll` / `winmm.dll`），
Office 一启动你的 `Server` 线程就活在白名单里，管道逻辑一行不改。

---

## 写回合法性（必须验证）

不同策略对「非白名单进程写入」有三种行为：

```powershell
# 用桥写一个测试文件，再用桥读头判定
python -c "
import cdgfs
cdgfs.write_bytes(r'D:\Data\write_test.xlsx', b'PK\x03\x04test')
print(cdgfs.classify(r'D:\Data\write_test.xlsx'))
"
```

| 结果 | 含义 | 处理 |
|---|---|---|
| `plain` | 该目录不加密，写进去是明文 | 换加密目录，或确认业务是否允许 |
| `cipher` | ✅ 驱动已加密，别人装客户端的机器能正常打开 | 正确 |
| 报错/空 | 写入被拒 | 换目录，或走 UNC 共享 |

再用 Office 打开一次做最终确认：

```powershell
$xl = New-Object -ComObject Excel.Application; $xl.Visible=$false
try { $wb=$xl.Workbooks.Open('D:\Data\write_test.xlsx'); "OPEN OK  sheets=$($wb.Sheets.Count)"; $wb.Close($false) }
catch { "OPEN FAIL :: $($_.Exception.Message)" }
$xl.Quit()
```

---

## 多实例

不同管道名可并存（同一管道名只有一实例）：

```powershell
Start-Process rundll32.exe -ArgumentList '"...\bridge.dll",Start cdgbridge"  -WindowStyle Hidden
Start-Process rundll32.exe -ArgumentList '"...\bridge.dll",Start cdgbridge2" -WindowStyle Hidden
```

```python
cdgfs.PIPE_NAME = 'cdgbridge2'
# 或每次调用传 name= 参数
cdgfs.read_bytes(path, name='cdgbridge2')
```

```cmd
python gateway.py --port 8766 --pipe cdgbridge2 --token T2
```

---

## 已验证项

| 项目 | 结果 |
|---|---|
| probe 借进程读明文 | ✅ `50 4B 03 04` |
| 字节一致性（桥 vs 直读） | ✅ sha256 相同 |
| xlsx 读写（openpyxl） | ✅ 改值后重读正确 |
| docx 读写（python-docx） | ✅ |
| pptx 读写（python-pptx） | ✅ |
| pdf 读写（pikepdf） | ✅ `25 50 44 46` |
| 50MB 大文件往返 | ✅ 51,200,000 字节一致 |
| 200 并发读 | ✅ 0.28s |
| 中文路径 / 中文文件名 | ✅ |
| 多实例并存 + QUIT | ✅ |
| HTTP 下载上传往返 | ✅ sha256 一致 |
| C# / Node / Go / curl 调用 | ✅ |

---

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 连不上管道 | 桥没启动 / 管道名不符 | `start-bridge.cmd`；检查 `Get-CimInstance Win32_Process -Filter "Name='rundll32.exe'"` |
| `classify` 返回 `cipher` | 宿主不在白名单 | 换宿主，或走 DLL 劫持 |
| rundll32 报「找不到入口」 | 32/64 位不匹配 | 统一 x64 编译（`build.cmd` 已固定 `/MACHINE:X64`） |
| 管道被策略拦 | 部分策略禁命名管道 | 用 HTTP 网关（本地回环 TCP），或改 WM_COPYDATA |
| EDR 拦 rundll32 | 行为检测 | 换 `dllhost.exe`，或走 COM 服务器注册（`regsvr32`） |
| 写入后 Office 打不开 | 写入路径不加密 / 写失败 | 按「写回合法性」验证 |
| 中文乱码 | 源文件不是 UTF-8 | 编译加 `/utf-8`（`build.cmd` 已加） |

---

## 排版零损失的边界

桥搬运的是**完整原始文件字节**，所以版式本身不会丢。但**用什么库改**决定剩余保真度：

| 处理方式 | 保真度 |
|---|---|
| 只搬字节（读→写，不修改） | 100%，逐字节相同 |
| openpyxl 改单元格 | 高（样式/合并/列宽保留；条件格式、图表可能被重写） |
| python-docx 改段落 | 高（页眉页脚、域、修订可能丢失） |
| python-pptx 改文本 | 高（动画、部分 SmartArt 可能丢失） |
| pikepdf 改 PDF | 高（原始布局保留） |
| **直接改 OOXML zip 部件** | **100%**（只替换目标 XML，其余字节不动） |

要绝对 100%（含图表、条件格式、PPT 动画），用最后一行的做法：

```python
import io, zipfile, cdgfs

raw = cdgfs.read_bytes(path)
src = zipfile.ZipFile(io.BytesIO(raw))
out = io.BytesIO()
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
    for item in src.infolist():
        data = src.read(item.filename)
        if item.filename == 'xl/worksheets/sheet1.xml':
            data = data.replace(b'<t>Hello</t>', b'<t>Hello Bridge</t>')
        dst.writestr(item, data)          # 其余部件原样写回
cdgfs.write_bytes(path, out.getvalue())
```

---

## 安全与合规

- 网关默认绑 `127.0.0.1`，对外服务才用 `0.0.0.0` + `--token`
- 管道 `PIPE_UNLIMITED_INSTANCES`，无鉴权，本机任意进程可读写 → 生产环境建议
  只在本机用，或加一层 ACL（`CreateNamedPipeW` 的 `lpSecurityAttributes`）
- 明文只在本机内存与管道里流转，不出内网
