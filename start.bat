@echo off
title SafetyVision Launcher
color 0A
echo.
echo  =============================================
echo    SafetyVision  -  PT Bintang Toedjoe
echo    Helmet Detection System
echo  =============================================
echo.

REM ── Step 1: Start Python detector ──────────────────────────────────────────
echo [1/2] Starting Python detector (port 5000)...
start "Python Detector" cmd /k "cd /d "%~dp0" && python detector.py"

REM ── Wait for Python to initialize ──────────────────────────────────────────
echo       Waiting for detector to initialize...
timeout /t 4 /nobreak > nul

REM ── Step 2: Start Go web server ────────────────────────────────────────────
echo [2/2] Starting Go web server (port 8081)...
start "Go Web Server" cmd /k "cd /d "%~dp0server" && go run main.go"

echo.
echo  ✓ Services starting in separate windows.
echo.
echo  Detector  →  http://localhost:5000
echo  Dashboard →  http://localhost:8081
echo.
echo  Opening dashboard in browser...
timeout /t 3 /nobreak > nul
start http://localhost:8081

echo  Press any key to close this launcher.
pause > nul
