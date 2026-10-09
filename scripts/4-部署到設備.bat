@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "PYTHONIOENCODING=utf-8"
title 部署到 Android 設備

set "ROOT=%~dp0.."
pushd "%ROOT%" 2>nul || (echo   [錯誤] 無法進入專案根目錄 & pause & exit /b 1)

echo.
echo ==================================================================
echo    4 - 部署 UrlList 到 Android 設備
echo ==================================================================
echo.

set "PKG=com.tw99.no23.an"
rem ★ 2026-10-10 實測修正：UrlList 位於 patch OBB，不在 main OBB。
rem   （main OBB 的 1528431122 是 assets/Zero/Lua/lua.ab）
set "ENCODED=patch.138.com.tw99.no23.an.obb"
set "DEVICE_OBB=/sdcard/Android/obb/%PKG%/%ENCODED%"
set "DATA_OFF=1519062275"

rem ---- 找 adb ----
set "ADB="
for %%p in (
    "C:\Program Files\Netease\MuMu\nx_main\adb.exe"
    "C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe"
    "C:\Program Files (x86)\Netease\MuMu\nx_main\adb.exe"
    "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
) do (
    if not defined ADB if exist %%p set "ADB=%%~p"
)
if not defined ADB (
    where adb >nul 2>&1 && set "ADB=adb"
)
if not defined ADB (
    echo   [錯誤] 找不到 adb.exe
    echo          請安裝 Android SDK platform-tools，或把 adb.exe 放進 PATH。
    echo          若你用 MuMu 模擬器，adb 通常在：
    echo              C:\Program Files\Netease\MuMu\nx_main\adb.exe
    pause & popd & exit /b 1
)
echo   使用 adb: !ADB!

rem ---- 產生檔案 ----
if not exist "output\UrlList_Android.txt" (
    echo.
    echo   [提示] 尚未產生 UrlList，先產生一次...
    python\python.exe gen_urllist.py
    if errorlevel 1 (pause & popd & exit /b 1)
)

for %%f in ("output\UrlList_Android.txt") do set "SZ=%%~zf"
echo   檔案大小: !SZ! bytes
if not "!SZ!"=="598" (
    echo.
    echo   [錯誤] 大小必須是 598 bytes，目前是 !SZ!。
    echo          OBB 內是固定槽位，大小不符會破壞資源。
    echo          請縮短 config\server.json 的 host，或改用較短的 IP。
    pause & popd & exit /b 1
)

rem ---- 列出裝置 ----
echo.
echo   目前連接的裝置：
"!ADB!" devices -l
echo.
set "DEV="
set /p "DEV=  請輸入裝置序號（直接 Enter 用第一台）："

if "!DEV!"=="" (
    for /f "skip=1 tokens=1,2" %%a in ('"!ADB!" devices') do (
        if not defined DEV if "%%b"=="device" set "DEV=%%a"
    )
)
if "!DEV!"=="" (
    echo   [錯誤] 沒有可用的裝置。請先啟動模擬器，或接上手機並開啟 USB 偵錯。
    pause & popd & exit /b 1
)
echo   目標裝置: !DEV!

rem ---- 檢查 OBB ----
echo.
echo   檢查裝置上的 OBB...
"!ADB!" -s !DEV! shell "ls -l %DEVICE_OBB%" 2>&1
"!ADB!" -s !DEV! shell "ls %DEVICE_OBB%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [錯誤] 裝置上找不到 OBB：
    echo          %DEVICE_OBB%
    echo          請先完整安裝並啟動過一次遊戲，讓它下載/放置 OBB。
    pause & popd & exit /b 1
)

rem ---- 試 root ----
echo.
echo   嘗試 adb root（模擬器通常可用；真機多半不行）...
"!ADB!" -s !DEV! root >nul 2>&1
timeout /t 2 /nobreak >nul
"!ADB!" -s !DEV! wait-for-device >nul 2>&1

rem ---- 推送並就地寫入 ----
echo.
echo   推送 UrlList 到裝置暫存區...
"!ADB!" -s !DEV! push "output\UrlList_Android.txt" /data/local/tmp/UrlList_new.txt

echo.
echo   就地寫入 OBB（offset !DATA_OFF!，598 bytes）...
"!ADB!" -s !DEV! shell "dd if=/data/local/tmp/UrlList_new.txt of=%DEVICE_OBB% bs=1 seek=!DATA_OFF! count=598 conv=notrunc" 2>&1
if errorlevel 1 (
    echo.
    echo   [錯誤] 寫入失敗。
    echo          真機沒有 root 時無法改 OBB。替代做法（見 docs\新設備部署.md）：
    echo           1^) 把 OBB 複製到電腦
    echo           2^) 用 tools 裡的 write_urllist.py 就地改寫
    echo           3^) 推回裝置
    pause & popd & exit /b 1
)

echo.
echo   驗證寫入結果（前 120 字元）...
"!ADB!" -s !DEV! shell "dd if=%DEVICE_OBB% bs=1 skip=!DATA_OFF! count=120 2>/dev/null"
echo.

echo ==================================================================
echo    部署完成
echo ==================================================================
echo.
echo   重要：必須清除遊戲快取，否則它會繼續讀舊的 UrlList！
echo.
set /p "CLR=   現在就執行 adb shell pm clear %PKG% 嗎？(Y/N) "
if /i "!CLR!"=="Y" (
    echo   清除中...
    "!ADB!" -s !DEV! shell "pm clear %PKG%"
    echo   完成。請重新啟動遊戲。
) else (
    echo   已略過。稍後請自行執行：
    echo       "!ADB!" -s !DEV! shell "pm clear %PKG%"
)
echo.
pause
popd
endlocal
