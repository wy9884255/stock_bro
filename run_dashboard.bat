@echo off
setlocal

set "TRADE_DATE=%~1"
if "%TRADE_DATE%"=="" set "TRADE_DATE=2026-05-11"

set "PORT=%~2"
if "%PORT%"=="" set "PORT=8765"

cd /d "%~dp0"

echo Building dashboard for %TRADE_DATE%...
python -m stock_bro.cli build-dashboard --date %TRADE_DATE%
if errorlevel 1 (
    echo Failed to build dashboard.
    exit /b 1
)

echo.
echo Dashboard URL:
echo http://127.0.0.1:%PORT%/dashboard.html
echo.
echo Press Ctrl+C to stop the server.
echo.

python -m http.server %PORT% --directory web
