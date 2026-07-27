@echo off
title Case PM - Install Java for MPP Import
cd /d "%~dp0"

echo ================================================
echo   Case PM - Install Java for MPP Import
echo ================================================
echo.
echo This downloads a portable Temurin Java 17 runtime into:
echo   vendor\java
echo.
echo MS Project .mpp import needs Java on the server PC.
echo.

set "PY="
if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo ERROR: Python is not installed.
    pause
    exit /b 1
)

"%PY%" scripts\ensure_java_runtime.py
if errorlevel 1 (
    echo.
    echo Java setup did not complete.
    echo If download failed, install Temurin 17 JRE from https://adoptium.net/
    pause
    exit /b 1
)

echo.
echo Java is ready for MPP import.
echo Restart RUN-AS-SERVER.bat, then try importing your .mpp file again.
echo.
pause
