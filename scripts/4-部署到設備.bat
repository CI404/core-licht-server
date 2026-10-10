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

rem ★★ 2026-10-10 最終實測修正（重要）★★
rem   遊戲實際讀取的 UrlList【不在 OBB】，而是在遊戲資料目錄：
rem       /sdcard/Android/data/<pkg>/files/res/UrlList_Android.txt
rem       /sdcard/Android/data/<pkg>/files/res/SHASD_local.txt
rem   兩份都要寫。OBB 裡的那份只是來源，改了沒用。
rem
rem   （歷史記錄：main OBB 的 1528431122 是 lua.ab；
rem     patch OBB 的 1519062275 有 UrlList，但遊戲不讀那份）
set "RES_DIR=/sdcard/Android/data/%PKG%/files/res"
set "DEVICE_URL=%RES_DIR%/UrlList_Android.txt"
set "DEVICE_SHASD=%RES_DIR%/SHASD_local.txt"

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

rem ---- 檢查遊戲資料目錄 ----
echo.
echo   檢查裝置上的遊戲資料目錄...
"!ADB!" -s !DEV! shell "ls -l %RES_DIR%/" 2>&1
"!ADB!" -s !DEV! shell "ls %RES_DIR%/" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [錯誤] 裝置上找不到：
    echo          %RES_DIR%
    echo          請先完整安裝並「啟動過一次」遊戲，讓它建立此目錄。
    pause & popd & exit /b 1
)

rem ---- 備份現有檔案（只備份一次）----
echo.
echo   備份裝置現有設定...
"!ADB!" -s !DEV! shell "[ -f %DEVICE_URL%.bak ] || cp %DEVICE_URL% %DEVICE_URL%.bak" 2>&1
"!ADB!" -s !DEV! shell "[ -f %DEVICE_SHASD%.bak ] || cp %DEVICE_SHASD% %DEVICE_SHASD%.bak" 2>&1

rem ---- 推送並覆蓋兩個位置 ----
echo.
echo   推送 UrlList 到裝置暫存區...
"!ADB!" -s !DEV! push "output\UrlList_Android.txt" /data/local/tmp/UrlList_new.txt

echo.
echo   寫入兩個位置（遊戲兩份都會讀）...
"!ADB!" -s !DEV! shell "cp /data/local/tmp/UrlList_new.txt %DEVICE_URL%" 2>&1
"!ADB!" -s !DEV! shell "cp /data/local/tmp/UrlList_new.txt %DEVICE_SHASD%" 2>&1
if errorlevel 1 (
    echo.
    echo   [錯誤] 寫入失敗，請確認裝置已連接且遊戲安裝過。
    pause & popd & exit /b 1
)

echo.
echo   驗證寫入結果（前 150 字元）...
"!ADB!" -s !DEV! shell "cat %DEVICE_URL%" 2>&1 | more +0
echo.

echo ==================================================================
echo    部署完成
echo ==================================================================
echo.
echo   接下來【重啟遊戲】即可（不需要 pm clear）。
echo.
echo   注意：本工具已將 server 值保留為 tw_debug_888（開發者模式）。
echo         這個值決定遊戲是否走 SDK 登入彈窗：
echo           tw_debug_888   - 關閉 SDK，直接開開發者登入界面  ← 正確
echo           tw_release_*   - 啟用 SDK，會跳出官方/FB/Google 登入彈窗
echo.
echo   若要還原成原本的設定：
echo       adb shell "cp %DEVICE_URL%.bak %DEVICE_URL%"
echo       adb shell "cp %DEVICE_SHASD%.bak %DEVICE_SHASD%"
echo.
pause
popd
endlocal
