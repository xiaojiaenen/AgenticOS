# AgenticOS 内网离线包打包脚本（在有外网的构建机执行）
#
# 产出 agenticos-intranet-<时间戳>.tar（内含镜像 tar + 代码 + 静态资源 + 校验清单），
# 拷到内网后按 OFFLINE-DEPLOY.md 三步导入即可。
#
# 用法（在仓库根目录）：
#   pwsh deploy/package-intranet.ps1                 # 默认含 MySQL 客户端无关
#   pwsh deploy/package-intranet.ps1 -SkipImages     # 只打代码包（镜像已单独传）
#   pwsh deploy/package-intranet.ps1 -FrontendOnly   # 只更新前端
$ErrorActionPreference = "Stop"

param(
    [switch]$SkipImages,
    [switch]$FrontendOnly,
    [string]$OutDir = ""
)

Set-Location (Split-Path $PSScriptRoot)

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$pkgName = "agenticos-intranet-$stamp"
$pkgDir = Join-Path $OutDir $pkgName
if (-not $OutDir) { $pkgDir = $pkgName }

function Step($n, $text) { Write-Host "[$n] $text" -ForegroundColor Cyan }

# ── 1. 前端构建（必须与后端同版本，前端产物进包） ──
if (-not $SkipImages -or $FrontendOnly) {
    Step "1/6" "构建前端 dist（不重建则跳过）"
    if (-not (Test-Path "frontend\dist\index.html")) {
        Push-Location frontend
        npm install
        npm run build
        Pop-Location
    }
    if (-not (Test-Path "frontend\dist\index.html")) { throw "前端构建失败：frontend/dist 缺失" }
}

# ── 2. 镜像构建（关键：只有这一步需要外网） ──
if (-not $SkipImages -and -not $FrontendOnly) {
    Step "2/6" "构建运行时镜像（含 pip 依赖 / chromium / torch）"
    docker build -f deploy/Dockerfile.runtime -t agenticos-runtime:latest .
    if ($LASTEXITCODE -ne 0) { throw "镜像构建失败" }

    Step "3/6" "导出镜像 tar（约 8GB，压缩后约 3GB）"
    New-Item -ItemType Directory -Force "$pkgDir\images" | Out-Null
    docker save agenticos-runtime:latest -o "$pkgDir\images\agenticos-runtime.tar"
    # 只带 nginx（前端）。MySQL/Redis 用外部既有服务，Redis Stack 不再需要
    # （记忆向量检索已改为进程内余弦，不依赖 RediSearch）。
    docker pull nginx:1.27-alpine
    docker save nginx:1.27-alpine -o "$pkgDir\images\nginx.tar"
}

# ── 4. 代码与静态资源 ──
Step "4/6" "拷贝代码、静态资源与部署编排"
New-Item -ItemType Directory -Force "$pkgDir\backend" | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\frontend\dist" | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\data" | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\deploy" | Out-Null

# backend 源码（排除缓存/测试/本地库）
Copy-Item -Recurse "backend\app" "$pkgDir\backend\" -Force
Copy-Item "backend\alembic" "$pkgDir\backend\" -Recurse -Force
Copy-Item "backend\alembic.ini","backend\main.py","backend\pyproject.toml","backend\uv.lock" "$pkgDir\backend\" -Force
Get-ChildItem -Path "$pkgDir\backend" -Recurse -Directory -Filter "__pycache__" |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

# 前端产物
if (Test-Path "frontend\dist\index.html") {
    Copy-Item "frontend\dist\*" "$pkgDir\frontend\dist\" -Recurse -Force
}

# 静态资源（只带模板/主题/图标等，不带运行时产物）
foreach ($sub in @("charts", "design-systems", "design-themes", "layouts", "skills",
                   "website-templates", "icons", "ui-audit", "knowledge")) {
    $src = Join-Path "data" $sub
    if (Test-Path $src) { Copy-Item $src "$pkgDir\data\" -Recurse -Force }
}

# 部署编排 + 文档（离线流程所需的文件必须齐全：
# install.sh / OFFLINE-DEPLOY.md / docker-compose.offline.yml /
# .env.offline.example / add-deps.sh 缺一个，内网按手册操作就会卡住）
Copy-Item "deploy\docker-compose.runtime.yml","deploy\docker-compose.offline.yml" "$pkgDir\deploy\" -Force
Copy-Item "deploy\Dockerfile.runtime","deploy\Dockerfile.offline","deploy\.env.example","deploy\.env.offline.example" "$pkgDir\deploy\" -Force
Copy-Item "deploy\DEPLOY.md","deploy\OFFLINE-DEPLOY.md","deploy\add-deps.sh","deploy\install.sh" "$pkgDir\deploy\" -Force
Copy-Item "deploy\nginx" "$pkgDir\deploy\nginx" -Recurse -Force
Copy-Item "docs\deploy\内网部署依赖清单.md" "$pkgDir\" -Force -ErrorAction SilentlyContinue

# ── 5. 离线嵌入模型（内网无 HF 镜像可下，必须随包带） ──
Step "5/6" "导出本地嵌入模型（bge-small-zh-v1.5）"
$hfCache = "data\hf-cache"
if (-not (Test-Path $hfCache)) {
    Write-Host "  警告：本地没有 HF 缓存，将依赖内网自行准备模型（见 OFFLINE-DEPLOY.md 第 4 节）" -ForegroundColor Yellow
} else {
    New-Item -ItemType Directory -Force "$pkgDir\data\hf-cache" | Out-Null
    Copy-Item "$hfCache\*" "$pkgDir\data\hf-cache\" -Recurse -Force
}

# ── 6. 校验清单 ──
Step "6/6" "生成校验清单"
$manifest = @()
Get-ChildItem $pkgDir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring((Resolve-Path $pkgDir).Path.Length + 1).Replace('\', '/')
    $manifest += "{0}  {1}  {2}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Length, $rel
}
$manifest | Set-Content "$pkgDir\MANIFEST.sha256" -Encoding utf8

$totalMB = [math]::Round(((Get-ChildItem $pkgDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 0)
Write-Host ""
Write-Host "  包目录: $pkgDir ($totalMB MB)" -ForegroundColor Green
Write-Host "  下一步: 打成单文件 tar 拷贝到内网" -ForegroundColor Green
Write-Host "    tar -cf $pkgName.tar -C . $pkgName" -ForegroundColor Yellow
