@echo off
setlocal enabledelayedexpansion

REM ── Get today's date in format: Month_Day_Year (e.g., July_24_2026) ──
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do (
    set DATE_RAW=%%a %%b %%c
)
REM Parse date - format depends on locale, this handles MM/DD/YYYY
for /f "tokens=1-3 delims=/-. " %%a in ("%DATE%") do (
    set MONTH=%%a
    set DAY=%%b
    set YEAR=%%c
)

REM Convert month number to name
if "%MONTH%"=="01" set MONTH_NAME=January
if "%MONTH%"=="02" set MONTH_NAME=February
if "%MONTH%"=="03" set MONTH_NAME=March
if "%MONTH%"=="04" set MONTH_NAME=April
if "%MONTH%"=="05" set MONTH_NAME=May
if "%MONTH%"=="06" set MONTH_NAME=June
if "%MONTH%"=="07" set MONTH_NAME=July
if "%MONTH%"=="08" set MONTH_NAME=August
if "%MONTH%"=="09" set MONTH_NAME=September
if "%MONTH%"=="10" set MONTH_NAME=October
if "%MONTH%"=="11" set MONTH_NAME=November
if "%MONTH%"=="12" set MONTH_NAME=December

set DATE_STRING=%MONTH_NAME%_%DAY%_%YEAR%
set APP_NAME=Rapid-Redact_%DATE_STRING%

echo ========================================
echo Rapid-Redact - ONEFILE Build
echo ========================================
echo.
echo Building: %APP_NAME%.exe
echo This creates a single EXE file (~220 MB)
echo.

REM ── Clean previous outputs ──────────────
echo [1/3] Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo Done.
echo.

REM ── Build with PyInstaller ─────────────────
echo [2/3] Building single executable with PyInstaller...
uv run python build_wrapper.py onefileBuild.spec
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

if not exist "dist\%APP_NAME%.exe" (
    echo.
    echo ERROR: dist\%APP_NAME%.exe not found after build!
    pause
    exit /b 1
)

echo Done.
echo.

REM ── Create ZIP file ─────────────────
echo [3/3] Creating ZIP archive...
cd dist
powershell -command "Compress-Archive -Path '%APP_NAME%.exe' -DestinationPath '%APP_NAME%.zip' -Force"
if errorlevel 1 (
    echo.
    echo WARNING: ZIP creation failed! But EXE is ready.
    cd ..
    goto :complete
)
cd ..
echo Done.
echo.

:complete
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Output files:
echo   - dist\%APP_NAME%.exe  (~220 MB)
echo   - dist\%APP_NAME%.zip
echo.
echo NOTE: First run will be slower as it extracts to temp folder.
echo.
pause
