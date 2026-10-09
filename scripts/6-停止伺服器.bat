@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "PYTHONIOENCODING=utf-8"
title 停止離線伺服器

set "ROOT=%~dp0.."
pushd "%ROOT%" 2>nul || (echo   [錯誤] 無法進入專案根目錄 & pause & exit /b 1)

echo.
echo ==================================================================
echo    停止離線伺服器
echo ==================================================================
echo.

set "LPORT="
set "CPORT="
if exist "python\python.exe" (
    for /f "usebackq delims=" %%a in (`python\python.exe -c "import config as c; print(c.LOGIN_PORT); print(c.CDN_PORT)"`) do (
        if not defined LPORT set "LPORT=%%a"
        if not defined CPORT if defined LPORT set "CPORT=%%a"
    )
)
if not defined LPORT set "LPORT=9001"
if not defined CPORT set "CPORT=8080"

echo   目標埠：遊戲服 !LPORT!  /  CDN !CPORT!
echo.

set "KILLED=0"
for %%P in (!LPORT! !CPORT!) do (
    for /f "tokens=5" %%i in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
        if not "%%i"=="0" (
            echo   停止 埠 %%P  ^(PID %%i^) ...
            taskkill /PID %%i /F >nul 2>&1
            if not errorlevel 1 set "KILLED=1"
        )
    )
)

if "!KILLED!"=="0" (
    echo   沒有任何服務在這些埠上執行（可能本來就沒開）。
) else (
    echo.
    echo   已停止。
)

echo.
echo   殘留檢查：
netstat -ano | findstr /r /c:":!LPORT! .*LISTENING" >nul 2>&1
if errorlevel 1 (echo     埠 !LPORT! 已釋放) else (echo     [警告] 埠 !LPORT! 仍在監聽)
netstat -ano | findstr /r /c:":!CPORT! .*LISTENING" >nul 2>&1
if errorlevel 1 (echo     埠 !CPORT! 已釋放) else (echo     [警告] 埠 !CPORT! 仍在監聽)

echo.
pause
popd
endlocal
