@echo off
cd /d "%~dp0"

echo ================================================
echo   Case PM - Pull Latest Updates from GitHub
echo ================================================
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git is not installed or not in PATH.
    echo Install Git from https://git-scm.com/download/win
    pause
    exit /b 1
)

echo Fetching latest changes from GitHub...
git fetch origin
if errorlevel 1 (
    echo ERROR: git fetch failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo Current branch:
git branch --show-current
echo.

set BRANCH=cursor/documents-checkout-ab10
echo Switching to %BRANCH% and pulling updates...
git checkout %BRANCH%
if errorlevel 1 (
    echo ERROR: Could not switch to %BRANCH%
    pause
    exit /b 1
)

git pull origin %BRANCH%
if errorlevel 1 (
    echo ERROR: git pull failed.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   Update complete!
echo ================================================
echo.
echo Latest commit:
git log -1 --oneline
echo.
echo Next steps:
echo   1. Close Case PM if it is running
echo   2. Double-click run.bat to restart
echo   3. Press Ctrl+F5 in your browser to hard refresh
echo.
pause
