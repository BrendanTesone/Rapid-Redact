@echo off
REM Rapid Redact - Build Installer

echo ========================================
echo Rapid Redact - Installer Build
echo ========================================
echo.

REM Try to find Inno Setup compiler
set ISCC_PATH=
where iscc.exe >nul 2>nul
if not errorlevel 1 (
    set ISCC_PATH=iscc.exe
    goto :found_inno
)

REM Check user's AppData location (Inno Setup 7 default for current user)
if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\iscc.exe" (
    set ISCC_PATH="%LOCALAPPDATA%\Programs\Inno Setup 7\iscc.exe"
    goto :found_inno
)

REM Check common Inno Setup 7 locations
if exist "C:\Program Files (x86)\Inno Setup 7\iscc.exe" (
    set ISCC_PATH="C:\Program Files (x86)\Inno Setup 7\iscc.exe"
    goto :found_inno
)

if exist "C:\Program Files\Inno Setup 7\iscc.exe" (
    set ISCC_PATH="C:\Program Files\Inno Setup 7\iscc.exe"
    goto :found_inno
)

REM Check Inno Setup 6 locations as fallback
if exist "C:\Program Files (x86)\Inno Setup 6\iscc.exe" (
    set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\iscc.exe"
    goto :found_inno
)

if exist "C:\Program Files\Inno Setup 6\iscc.exe" (
    set ISCC_PATH="C:\Program Files\Inno Setup 6\iscc.exe"
    goto :found_inno
)

REM Not found
echo ERROR: Inno Setup compiler not found!
echo.
echo Searched locations:
echo   - PATH environment variable
echo   - %LOCALAPPDATA%\Programs\Inno Setup 7\
echo   - C:\Program Files (x86)\Inno Setup 7\
echo   - C:\Program Files\Inno Setup 7\
echo.
echo Please ensure Inno Setup is installed.
echo Download from: https://jrsoftware.org/isdl.php
echo.
pause
exit /b 1

:found_inno
echo Found Inno Setup: %ISCC_PATH%
echo.

REM Step 1: Check if output exists
if not exist dist\Rapid-Redact\Rapid-Redact.exe (
    echo ERROR: dist\Rapid-Redact\Rapid-Redact.exe not found!
    echo Please run build.bat or build_auto.bat first.
    echo.
    pause
    exit /b 1
)

REM Step 2: Create installer directory
if not exist installer_output mkdir installer_output

REM Step 3: Create installer
echo [1/2] Creating installer with Inno Setup...
echo.
%ISCC_PATH% installer.iss

if errorlevel 1 (
    echo.
    echo INSTALLER BUILD FAILED!
    pause
    exit /b 1
)

echo.
echo [2/2] Installer complete!
echo.
echo ========================================
echo Installer: installer_output\Rapid-Redact-Setup-0.1.0.exe
echo ========================================
echo.
pause
