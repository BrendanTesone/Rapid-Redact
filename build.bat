@echo off
setlocal

set APP_NAME=Rapid-Redact

echo ========================================
echo Rapid Redact - Build Only
echo ========================================
echo.

REM ── Clean previous outputs ──────────────
echo [1/2] Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo Done.
echo.

REM ── Build with PyInstaller ─────────────────
echo [2/2] Building executable with PyInstaller...
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

echo.
echo ========================================
echo Build complete: dist\%APP_NAME%.exe
echo ========================================
echo.
pause
