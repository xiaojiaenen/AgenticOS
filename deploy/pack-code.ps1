# Intranet code bundle (ASCII only: Windows PowerShell 5.1 misreads UTF-8 without BOM)
$ErrorActionPreference = "Stop"
Set-Location "D:\code\AgenticOS"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$pkgName = "agenticos-intranet-$stamp"
$pkgDir = Join-Path "G:\Downloads" $pkgName

Write-Host "[1/6] check frontend dist" -ForegroundColor Cyan
if (-not (Test-Path "frontend\dist\index.html")) { throw "frontend dist missing; run npm run build first" }
Write-Host "  OK frontend/dist/index.html"

Write-Host "[2/6] create package dirs" -ForegroundColor Cyan
New-Item -ItemType Directory -Force $pkgDir | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\backend" | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\frontend\dist" | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\data" | Out-Null
New-Item -ItemType Directory -Force "$pkgDir\deploy" | Out-Null

Write-Host "[3/6] copy backend sources" -ForegroundColor Cyan
Copy-Item -Recurse "backend\app" "$pkgDir\backend\" -Force
Copy-Item "backend\alembic" "$pkgDir\backend\" -Recurse -Force
Copy-Item "backend\alembic.ini","backend\main.py","backend\pyproject.toml","backend\uv.lock" "$pkgDir\backend\" -Force
Get-ChildItem -Path "$pkgDir\backend" -Recurse -Directory -Filter "__pycache__" |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

# office runtime: Word/Excel generation needs node_modules which cannot be installed offline
if (Test-Path "backend\office-runtime\node_modules") {
    Write-Host "  copying office-runtime (with node_modules)"
    Copy-Item "backend\office-runtime" "$pkgDir\backend\" -Recurse -Force
} else {
    Write-Host "  WARN office-runtime/node_modules missing; office agent cannot build Word/Excel" -ForegroundColor Yellow
}

Write-Host "[4/6] copy frontend dist and static assets" -ForegroundColor Cyan
Copy-Item "frontend\dist\*" "$pkgDir\frontend\dist\" -Recurse -Force
foreach ($sub in @("charts", "design-systems", "design-themes", "layouts", "skills",
                   "website-templates", "icons", "ui-audit", "knowledge")) {
    $src = Join-Path "data" $sub
    if (Test-Path $src) { Copy-Item $src "$pkgDir\data\" -Recurse -Force }
}

Write-Host "[5/6] copy deploy files" -ForegroundColor Cyan
Copy-Item "deploy\docker-compose.runtime.yml","deploy\docker-compose.offline.yml" "$pkgDir\deploy\" -Force
Copy-Item "deploy\Dockerfile.runtime","deploy\Dockerfile.offline","deploy\.env.example","deploy\.env.offline.example" "$pkgDir\deploy\" -Force
Copy-Item "deploy\DEPLOY.md","deploy\OFFLINE-DEPLOY.md","deploy\OFFLINE-DEPS.md","deploy\add-deps.sh","deploy\sync-deps.sh","deploy\install.sh" "$pkgDir\deploy\" -Force
Copy-Item "deploy\nginx" "$pkgDir\deploy\nginx" -Recurse -Force
foreach ($extra in @("diagnose-ldap.sh", "diagnose-threads.sh")) {
    if (Test-Path (Join-Path "deploy" $extra)) { Copy-Item (Join-Path "deploy" $extra) "$pkgDir\deploy\" -Force }
}

Write-Host "[6/6] write manifest" -ForegroundColor Cyan
$manifest = @()
$rootPath = (Resolve-Path $pkgDir).Path
Get-ChildItem $pkgDir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($rootPath.Length + 1).Replace('\', '/')
    $manifest += "{0}  {1}  {2}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Length, $rel
}
$manifest | Set-Content "$pkgDir\MANIFEST.sha256" -Encoding utf8

$totalMB = [math]::Round(((Get-ChildItem $pkgDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 0)
Write-Host ""
Write-Host ("  package: " + $pkgDir + "  (" + $totalMB + " MB)") -ForegroundColor Green
Write-Host ("  files: " + $manifest.Count) -ForegroundColor Green
