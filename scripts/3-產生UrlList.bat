@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "PYTHONIOENCODING=utf-8"
title 產生 UrlList_Android.txt

set "ROOT=%~dp0.."
pushd "%ROOT%" 2>nul || (echo   [錯誤] 無法進入專案根目錄 & pause & exit /b 1)

echo.
echo ==================================================================
echo    3 - 產生 UrlList_Android.txt
echo ==================================================================
echo.
echo   這個檔案告訴遊戲「去哪裡抓 CDN 資源」。
echo   會依照 config\server.json 的 host 與 cdn_port 產生。
echo.

if not exist "python\python.exe" (
    echo   [錯誤] 找不到 python\python.exe
    pause & popd & exit /b 1
)

set "ARG1=%~1"
set "ARG2=%~2"

if "!ARG1!"=="" (
    python\python.exe gen_urllist.py
) else (
    if "!ARG2!"=="" (
        python\python.exe gen_urllist.py "!ARG1!"
    ) else (
        python\python.exe gen_urllist.py "!ARG1!" "!ARG2!"
    )
)

echo.
echo ------------------------------------------------------------------
echo   說明
echo ------------------------------------------------------------------
echo   * 產出檔：output\UrlList_Android.txt   （固定 598 bytes）
echo   * 下一步：scripts\4-部署到設備.bat
echo.
echo   若你想針對不同主機各產生一份，也可以直接下參數：
echo        scripts\3-產生UrlList.bat 192.168.1.100
echo        scripts\3-產生UrlList.bat 192.168.1.100 8080
echo.
pause
popd
endlocal
