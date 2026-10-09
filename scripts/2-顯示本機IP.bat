@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "PYTHONIOENCODING=utf-8"

set "ROOT=%~dp0.."
pushd "%ROOT%" 2>nul || (echo   [錯誤] 無法進入專案根目錄 & pause & exit /b 1)

echo.
echo ==================================================================
echo    2 - 顯示本機 IP 位址
echo ==================================================================
echo.

set "FOUND=0"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    if not "!IP!"=="" (
        echo    !IP!
        set "FOUND=1"
    )
)

if "!FOUND!"=="0" (
    echo    [警告] ipconfig 找不到 IPv4，改用 PowerShell 查詢...
    powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | ForEach-Object { '    ' + $_.IPAddress + '   (' + $_.InterfaceAlias + ')' }"
)

echo.
echo ------------------------------------------------------------------
echo   要選哪一個？
echo ------------------------------------------------------------------
echo    * MuMu / 雷電 模擬器 ......... 10.0.2.2      （不要改）
echo    * 真機（與電腦同一個 Wi-Fi）... 上面那個 192.168.x.x 或 10.x.x.x
echo.
echo   把選好的值填進：  config\server.json   的  "host"  欄位
echo.
set /p "PICK=   （可選）直接輸入 IP，幫你寫進 config\server.json： "

if not "!PICK!"=="" (
    echo !PICK! | findstr /r /c:"^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
    if errorlevel 1 (
        echo   [錯誤] 不是合法的 IPv4 位址，未做任何修改。
    ) else (
        python\python.exe -c "import json,io,sys; p=r'config/server.json'; d=json.load(io.open(p,encoding='utf-8')); d['host']=sys.argv[1]; io.open(p,'w',encoding='utf-8').write(json.dumps(d,ensure_ascii=False,indent=2)); print('   [完成] host 已設為 '+sys.argv[1])" "!PICK!"
    )
)

echo.
echo   提醒：改完 host 之後，必須重新產生 UrlList：
echo        scripts\3-產生UrlList.bat
echo        scripts\4-部署到設備.bat
echo.
pause
popd
endlocal
