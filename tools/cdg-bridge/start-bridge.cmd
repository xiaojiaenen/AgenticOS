@echo off
setlocal
REM ===========================================================================
REM  start-bridge.cmd —— 启动常驻桥宿主
REM    rundll32.exe 加载 bridge.dll，进程常驻，管道就绪后你的程序即可接入
REM ===========================================================================

set HERE=%~dp0
set DLL=%HERE%bin\bridge.dll
set PIPE=cdgbridge

if not exist "%DLL%" (
  echo [ERR] 找不到 %DLL%
  echo       先运行 build.cmd 编译
  exit /b 1
)

REM 已在运行则不重复启动
powershell -NoProfile -Command ^
  "$c = Get-CimInstance Win32_Process -Filter \"Name='rundll32.exe'\" | Where-Object { $_.CommandLine -like '*bridge.dll*' }; if ($c) { Write-Host '[SKIP] 已在运行 pid='$c.ProcessId; exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo.
  echo 桥已在运行，直接用即可
  exit /b 0
)

echo [START] rundll32.exe "%DLL%",Start %PIPE%
start "" /b rundll32.exe "%DLL%",Start %PIPE%

REM 等管道就绪
powershell -NoProfile -Command ^
  "$ok=$false; 1..40 | ForEach-Object { try { $f=[IO.File]::Open('\\\\.\\pipe\\%PIPE%','Open','ReadWrite'); $f.Close(); $ok=$true; break } catch { Start-Sleep -Milliseconds 100 } }; if($ok){Write-Host '[OK] 管道就绪'}else{Write-Host '[ERR] 管道未就绪'; exit 1}"

echo.
echo 用法示例：
echo   python -c "import cdgfs; print(cdgfs.ping())"
endlocal
