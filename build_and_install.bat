@echo off
setlocal

set SEMVER=0.1.0
set APP_NAME=Rapid-Redact
set INSTALLER_FILE=%APP_NAME%-Setup-%SEMVER%.exe

echo ========================================
echo Rapid Redact - Build and Install
echo ========================================
echo.

REM ── Clean previous outputs ──────────────
echo [0/3] Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer_output rmdir /s /q installer_output
echo Done.
echo.

REM ── Step 1: PyInstaller ─────────────────
echo [1/3] Building executable with PyInstaller...
uv run python build_wrapper.py main.spec
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

if not exist dist\%APP_NAME%\%APP_NAME%.exe (
    echo.
    echo ERROR: dist\%APP_NAME%\%APP_NAME%.exe not found after build!
    pause
    exit /b 1
)
echo Done.
echo.

REM ── Step 2: Find Inno Setup ─────────────
set ISCC_PATH=
where iscc.exe >nul 2>nul
if not errorlevel 1 set ISCC_PATH=iscc.exe & goto :found_inno
if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\iscc.exe" set ISCC_PATH="%LOCALAPPDATA%\Programs\Inno Setup 7\iscc.exe" & goto :found_inno
if exist "C:\Program Files (x86)\Inno Setup 7\iscc.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 7\iscc.exe" & goto :found_inno
if exist "C:\Program Files\Inno Setup 7\iscc.exe" set ISCC_PATH="C:\Program Files\Inno Setup 7\iscc.exe" & goto :found_inno
if exist "C:\Program Files (x86)\Inno Setup 6\iscc.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\iscc.exe" & goto :found_inno
if exist "C:\Program Files\Inno Setup 6\iscc.exe" set ISCC_PATH="C:\Program Files\Inno Setup 6\iscc.exe" & goto :found_inno
echo ERROR: Inno Setup compiler not found! Download from https://jrsoftware.org/isdl.php
pause
exit /b 1

:found_inno
echo [2/3] Creating installer with Inno Setup (%ISCC_PATH%)...
if not exist installer_output mkdir installer_output
%ISCC_PATH% /DMyAppVersion=%SEMVER% installer.iss
if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup build failed!
    pause
    exit /b 1
)
echo Done.
echo.

REM ── Step 3: Install ─────────────────────
echo [3/3] Installing %INSTALLER_FILE%...
installer_output\%INSTALLER_FILE% /VERYSILENT /NORESTART
if errorlevel 1 (
    echo.
    echo ERROR: Installer exited with error code %ERRORLEVEL%!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Install complete: 
echo ========================================
echo.
pause
