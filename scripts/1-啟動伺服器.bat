@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "PYTHONIOENCODING=utf-8"
title 核心：利希特 - 離線伺服器

set "ROOT=%~dp0.."
pushd "%ROOT%" 2>nul || (echo   [錯誤] 無法進入專案根目錄 & pause & exit /b 1)

echo.
echo ==================================================================
echo    核心：利希特  離線伺服器  啟動中
echo ==================================================================
echo.

if not exist "python\python.exe" (
    echo   [錯誤] 找不到 python\python.exe
    echo          本專案應為「自帶執行環境」的完整包，請確認沒有漏掉 python 資料夾。
    pause & popd & exit /b 1
)
if not exist "node\node.exe" (
    echo   [警告] 找不到 node\node.exe，CDN 伺服器將無法啟動。
)

rem ---- 設定檔自動復原（給 clone 下來或誤刪的使用者）----
if not exist "config\server.json" (
    echo   [提示] 找不到 config\server.json，正在建立預設設定檔...
    python\python.exe make_default_config.py
    echo.
)

echo   [1/3] 檢查環境設定...
python\python.exe config.py
if errorlevel 1 (
    echo.
    echo   [警告] 環境檢查未全部通過（見上方 [!!] 項目）。
    echo          最常見原因：config\server.json 的 obb_main / obb_patch 路徑不對。
    echo.
    set /p "GO=   仍要繼續啟動嗎？(Y/N) "
    if /i not "!GO!"=="Y" (popd & exit /b 1)
)

echo   [2/3] 讀取連接埠設定...
for /f "usebackq delims=" %%a in (`python\python.exe -c "import config as c; print(c.LOGIN_PORT); print(c.CDN_PORT); print(c.PUBLIC_HOST)"`) do (
    if not defined LPORT set "LPORT=%%a"
    if not defined CPORT if defined LPORT set "CPORT=%%a"
    if not defined PHOST if defined CPORT set "PHOST=%%a"
)
echo          對外主機 = !PHOST!
echo          登入/遊戲埠 = !LPORT!
echo          CDN 埠 = !CPORT!

netstat -ano | findstr /r /c:":!LPORT! .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo   [警告] 埠 !LPORT! 已經被佔用！可能是伺服器已經在跑。
    set /p "GO2=   仍要繼續嗎？(Y/N) "
    if /i not "!GO2!"=="Y" (popd & exit /b 1)
)

echo   [3/3] 啟動服務...
start "遊戲服 (Python) - 請勿關閉" cmd /k "cd /d "%ROOT%\server" && "..\python\python.exe" mock_game_server.py"
timeout /t 2 /nobreak >nul
start "CDN 資源服 (Node) - 請勿關閉" cmd /k "cd /d "%ROOT%\cdn" && "..\node\node.exe" server2.js"

echo.
echo ==================================================================
echo    啟動完成
echo ==================================================================
echo.
echo    兩個新視窗會保持開啟（那是伺服器本體，不要關）：
echo       * 遊戲服 (Python)  ->  TCP !LPORT!   + HTTP 登入服
echo       * CDN 資源服 (Node) ->  HTTP !CPORT!
echo.
echo    客戶端要連的位址 = !PHOST!
echo.
echo    檢查是否真的起來了（看有沒有 LISTENING）：
echo       netstat -ano ^| findstr ":!LPORT! :!CPORT!"
echo.
echo    停止伺服器：scripts\6-停止伺服器.bat
echo    看即時日誌：runtime\mock-server.log  /  runtime\cdn-requests.log
echo.
pause
popd
endlocal
