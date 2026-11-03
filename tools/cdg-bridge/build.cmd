@echo off
setlocal enabledelayedexpansion
set SRC=%~dp0src
set OUT=%~dp0bin
if not exist "%OUT%" mkdir "%OUT%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 ( echo [ERR] vcvars64 failed & exit /b 1 )
echo [1/2] bridge.dll
cl /nologo /LD /EHsc /O2 /MT /std:c++17 /utf-8 /DUNICODE /D_UNICODE "%SRC%\bridge.cpp" /Fo"%OUT%\bridge.obj" /Fe"%OUT%\bridge.dll" /link /MACHINE:X64 /SUBSYSTEM:WINDOWS kernel32.lib user32.lib advapi32.lib
if errorlevel 1 exit /b 1
echo [2/2] probe.dll
cl /nologo /LD /EHsc /O2 /MT /std:c++17 /utf-8 /DUNICODE /D_UNICODE "%SRC%\probe.cpp" /Fo"%OUT%\probe.obj" /Fe"%OUT%\probe.dll" /link /MACHINE:X64 /SUBSYSTEM:WINDOWS kernel32.lib user32.lib
if errorlevel 1 exit /b 1
echo.
echo [OK] output: %OUT%
dir /b "%OUT%\*.dll"
endlocal
