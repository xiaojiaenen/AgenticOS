$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = "agenticos-deploy-$timestamp"
$outputZip = "agenticos-deploy-$timestamp.zip"

Write-Host "[1/4] Clean and rebuild frontend..." -ForegroundColor Cyan
Remove-Item -Recurse -Force frontend\dist -ErrorAction SilentlyContinue
Set-Location frontend
npm install
npm run build
Set-Location ..

if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "[ERROR] Frontend build failed" -ForegroundColor Red
    exit 1
}

Write-Host "[2/4] Prepare deploy files..." -ForegroundColor Cyan

# 清理临时目录
Remove-Item -Recurse -Force $outputDir -ErrorAction SilentlyContinue

# 创建目录结构
New-Item -ItemType Directory -Force "$outputDir\deploy\nginx" | Out-Null
New-Item -ItemType Directory -Force "$outputDir\backend\app" | Out-Null
New-Item -ItemType Directory -Force "$outputDir\frontend\dist" | Out-Null

# 复制 deploy
Copy-Item -Recurse deploy\docker-compose.yml "$outputDir\deploy\"
Copy-Item -Recurse deploy\Dockerfile.backend "$outputDir\deploy\"
Copy-Item -Recurse deploy\Dockerfile.frontend "$outputDir\deploy\"
Copy-Item -Recurse deploy\nginx\nginx.conf "$outputDir\deploy\nginx\"
Copy-Item -Recurse deploy\.env.example "$outputDir\deploy\"

# 复制 backend
Copy-Item -Recurse backend\pyproject.toml "$outputDir\backend\"
Copy-Item -Recurse backend\main.py "$outputDir\backend\"
Copy-Item -Recurse backend\app\* -Exclude "__pycache__","*.pyc","tests" "$outputDir\backend\app\"

# 复制 frontend dist
Copy-Item -Recurse frontend\dist\* "$outputDir\frontend\dist\"

# 复制 data 静态资源（排除运行时产物）
New-Item -ItemType Directory -Force "$outputDir\data" | Out-Null
Copy-Item -Recurse data\charts "$outputDir\data\"
Copy-Item -Recurse data\design-systems "$outputDir\data\"
Copy-Item -Recurse data\design-themes "$outputDir\data\"
Copy-Item -Recurse data\layouts "$outputDir\data\"
Copy-Item -Recurse data\skills "$outputDir\data\"
Copy-Item -Recurse data\website-templates "$outputDir\data\"

Write-Host "[3/4] Packaging to zip..." -ForegroundColor Cyan
Remove-Item -Force $outputZip -ErrorAction SilentlyContinue
Compress-Archive -Path $outputDir -DestinationPath $outputZip -Force

Write-Host "[4/4] Cleanup and done" -ForegroundColor Green
Remove-Item -Recurse -Force $outputDir

$sizeKB = [math]::Round((Get-Item $outputZip).Length / 1024, 1)
Write-Host ""
Write-Host "  File: $outputZip ($sizeKB KB)"
Write-Host ""
Write-Host "  # Copy to intranet, then:"
Write-Host "  unzip $outputZip -d /opt/agenticos"
Write-Host "  cd /opt/agenticos/$outputDir/deploy"
Write-Host "  cp .env.example .env"
Write-Host "  docker compose up -d --build"
