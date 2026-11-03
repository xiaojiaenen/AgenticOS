@echo off
setlocal
REM 停止桥宿主
powershell -NoProfile -Command ^
  "$c = Get-CimInstance Win32_Process -Filter \"Name='rundll32.exe'\" | Where-Object { $_.CommandLine -like '*bridge.dll*' }; if ($c) { $c | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[STOP] pid=' + $_.ProcessId) } } else { Write-Host '[SKIP] 未运行' }"
endlocal
