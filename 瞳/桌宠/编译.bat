@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ======================================================================
echo   瞳 · 桌宠  ——  編譯
echo ======================================================================
echo.

rem ---- 找 Windows 內建的 C# 編譯器 ----
set "CSC="
for %%p in (
    "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    "%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) do (
    if not defined CSC if exist %%p set "CSC=%%~p"
)
if not defined CSC (
    echo   [錯誤] 找不到 csc.exe（Windows 內建 C# 編譯器）
    echo          預期位置：%%WINDIR%%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
    pause
    exit /b 1
)
echo   編譯器：%CSC%
echo.

rem ---- 輸出 ----
set "OUT=build\瞳-桌宠.exe"
if not exist "build" mkdir "build"

echo   編譯中...
"%CSC%" /nologo /target:winexe /platform:anycpu /optimize+ ^
    /out:"%OUT%" ^
    /reference:System.dll ^
    /reference:System.Drawing.dll ^
    /reference:System.Windows.Forms.dll ^
    /reference:System.Core.dll ^
    /win32icon:src\app.ico ^
    /win32manifest:src\app.manifest ^
    /resource:assets\_embed\card_e01001_00.png,HitomiPet.assets.card_e01001_00.png ^
    /resource:assets\_embed\card_e01001_01.png,HitomiPet.assets.card_e01001_01.png ^
    /resource:assets\_embed\card_e01001_02.png,HitomiPet.assets.card_e01001_02.png ^
    /resource:assets\_embed\card_e01001_f01.png,HitomiPet.assets.card_e01001_f01.png ^
    /resource:assets\头像\headicon_10101.png,HitomiPet.assets.headicon_10101.png ^
    src\HitomiPet.cs 2>build\compile.log

if errorlevel 1 (
    echo.
    echo   [失敗] 編譯錯誤，詳見 build\compile.log
    echo   ----------------------------------------
    type build\compile.log
    echo   ----------------------------------------
    pause
    exit /b 1
)

if not exist "%OUT%" (
    echo.
    echo   [失敗] 沒有產出 exe。編譯器輸出：
    type build\compile.log
    pause
    exit /b 1
)

echo   [成功] %OUT%
echo.
echo ======================================================================
echo   完成
echo ======================================================================
echo.
echo   產出：%OUT%
for %%f in ("%OUT%") do echo   大小：%%~zf bytes
echo.
echo   注意：exe 需要與 assets\ 資料夾放在同一層才能顯示立繪。
echo         要打包成單一檔案，請執行「打包.bat」。
echo.
pause
endlocal
